"""Score a sound effect for listening fatigue, and pick replacements safely.

WHY THIS IS NOT A "IS IT SYNTHESIZED" DETECTOR
----------------------------------------------
That was the first design, and it failed calibration in the most useful way
possible. Measuring spectral flatness, harmonic concentration and decay-tail
noise against the two reference populations gave an inverted result:

    synthesized (pixel_battle/assets/sfx)  flatness 0.04-0.71, tail -10..-46 dBFS
    real CC0 recordings                    flatness 0.001-0.02, tail -100..-240 dBFS

Two reasons. The synthesized set here is built from FILTERED NOISE (`_lp_noise`,
`_bp_snap` in gen_hit_sfx.py), and noise is the flattest spectrum there is — the
"synthesis means tonal" assumption is simply false for this generator. And
professionally edited game assets are trimmed to exact digital silence, so the
decay tail points the wrong way too: it is the synthesis that carries a noise
floor. Tuning the thresholds until the answer looked right would have produced a
gate that proves nothing, so the approach was dropped rather than fudged.

WHAT ACTUALLY MATTERS
---------------------
The complaint is listening discomfort, and the ear does not care where a sound
came from. So this measures the spectrum, and measuring found the real fault —
which was the opposite of harshness. A shipped short breaks down as:

    <60Hz  35.3%   60-120Hz 47.0%   120-300 4.3%   300-2k 11.4%   2-8k 2.0%

82% of all energy below 120Hz and a hollow midrange. Sustained sub-bass at
volume fatigues as ear pressure rather than sharpness, which is why nothing
about it looked wrong at first. Three things stacked it: the synthesized hits
are near-pure low thumps (hit.wav is 99.8% under 300Hz), no bus had a high-pass,
and the hit bus added a further +3dB under 120Hz.

  lf          Below 300Hz. Weight. Also what broke this mix.
  mid         300Hz-2kHz. Body — the band the ear uses to locate an impact, and
              the one a phone speaker can actually reproduce.
  hf2_8       2-8kHz. Snap, and where ordinary listening fatigue is generated.
  vhf         Above 8kHz. Sizzle; grating in a sound that fires thirty times.
  centroid    Spectral centre of mass in Hz — a brightness proxy.
  crest       Peak-to-RMS in dB. Very low means squashed flat, exhausting over
              repetition.

Budgets are set for BALANCE, not to imitate what ships today — see the comment
on the constants. The shipped set scores 5/20 against them, which is the point.

Usage:
  python3 pixel_battle/scripts/audit_sfx.py DIR_OR_FILE...    # score candidates
  python3 pixel_battle/scripts/audit_sfx.py --baseline        # score the current set
  python3 pixel_battle/scripts/audit_sfx.py --json DIR
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SYNTH_DIR = ROOT / "pixel_battle/assets/sfx"
REAL_DIR = ROOT / "pixel_battle/assets/sfx_real"

AUDIO_EXT = (".wav", ".ogg", ".mp3", ".flac", ".aiff", ".aif")

# Budgets, second pass. The first pass took the 20 shipped effects as the
# reference and allowed a candidate to be "no brighter than what already ships".
# That was wrong, and rebuilding the mix proved it: high-passing the buses and
# adding a +3dB presence bump at 2kHz moved 2-8kHz energy DOWN, from 2.0% to
# 0.6%. EQ cannot add what the source does not contain — hit.wav is 99.8% below
# 300Hz, so boosting 2kHz amplifies silence. The shipped set is not a healthy
# reference to imitate; it is the thing being fixed.
#
# So a candidate is now judged on BALANCE, in both directions. Too dark and it
# vanishes on a phone speaker and piles onto the low-end pressure that started
# this investigation. Too bright and it generates the ordinary kind of listening
# fatigue. An impact needs low end for weight, midrange for the ear to place it,
# and only a little top for the snap.
MIN_MID = 0.15            # 300Hz-2kHz — the body. Below this it reads as a thud.
MAX_HF_2_8 = 0.35         # 2-8kHz — the snap. Above this it starts to sting.
MAX_VHF = 0.10            # above 8kHz — sizzle, grating over 30 repeats
MAX_LF = 0.60             # below 300Hz — weight, but this is what broke the mix
MAX_CENTROID = 2600.0     # Hz
MIN_CREST_DB = 6.0        # below this it has been flattened into a wall


SF_NATIVE = (".wav", ".ogg", ".flac", ".aiff", ".aif")


def _load(path: Path) -> tuple[np.ndarray, int]:
    """Mono float64. soundfile reads the formats it knows; everything else —
    mp3, mp4, m4a — goes out to ffmpeg, so a finished short can be measured
    alongside the raw effects that went into it."""
    if path.suffix.lower() not in SF_NATIVE:
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
             "-ac", "1", "-ar", "48000", "-"], capture_output=True)
        if r.returncode != 0 or not r.stdout:
            raise RuntimeError((r.stderr.decode()[:200]) or "no audio stream")
        return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64), 48000
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1).astype(np.float64), sr


def _avg_spectrum(x: np.ndarray, n: int = 1 << 14) -> np.ndarray:
    """Power spectrum averaged over the WHOLE file, not just its head.

    The first version analysed only x[:n] — about a third of a second. For a
    120ms hit that is the entire sound, but for the 199-second BGM it measured
    the intro and nothing else, which is exactly the kind of quiet wrong answer
    this tool exists to prevent. Frames are averaged Welch-style, skipping near
    silent ones so a long tail of nothing cannot drag the brightness down.
    """
    if len(x) < n:
        seg = np.pad(x, (0, n - len(x)))
        return np.abs(np.fft.rfft(seg * np.hanning(n))) ** 2
    hop = n // 2
    win = np.hanning(n)
    frames = [x[i:i + n] * win for i in range(0, len(x) - n + 1, hop)]
    # Cap the work on long files; 400 frames spans a 3-minute track densely.
    if len(frames) > 400:
        idx = np.linspace(0, len(frames) - 1, 400).astype(int)
        frames = [frames[i] for i in idx]
    spec = np.array([np.abs(np.fft.rfft(f)) ** 2 for f in frames])
    energy = spec.sum(axis=1)
    live = spec[energy > energy.max() * 0.02] if energy.max() > 0 else spec
    return (live if len(live) else spec).mean(axis=0)


def measure(path: Path) -> dict:
    x, sr = _load(path)
    if not len(x) or float(np.max(np.abs(x))) <= 0:
        return {"file": path.name, "error": "silent or unreadable"}
    x = x / float(np.max(np.abs(x)))          # loudness must not sway the verdict

    n = 1 << 14
    e = _avg_spectrum(x, n)
    f = np.fft.rfftfreq(n, 1 / sr)
    tot = float(e.sum()) + 1e-12

    hf = float(e[(f >= 2000) & (f < 8000)].sum() / tot)
    vhf = float(e[f >= 8000].sum() / tot)
    lf = float(e[f < 300].sum() / tot)
    centroid = float((f * e).sum() / tot)
    rms = float(np.sqrt(np.mean(x ** 2)))
    crest = 20 * np.log10(1.0 / (rms + 1e-12))

    mid = float(e[(f >= 300) & (f < 2000)].sum() / tot)

    reasons = []
    if mid < MIN_MID:
        reasons.append(f"midrange {mid:.0%} < {MIN_MID:.0%} (no body)")
    if lf > MAX_LF:
        reasons.append(f"<300Hz {lf:.0%} > {MAX_LF:.0%} (all weight, no detail)")
    if hf > MAX_HF_2_8:
        reasons.append(f"2-8kHz {hf:.0%} > {MAX_HF_2_8:.0%}")
    if vhf > MAX_VHF:
        reasons.append(f">8kHz {vhf:.0%} > {MAX_VHF:.0%}")
    if centroid > MAX_CENTROID:
        reasons.append(f"centroid {centroid:.0f}Hz > {MAX_CENTROID:.0f}Hz")
    if crest < MIN_CREST_DB:
        reasons.append(f"crest {crest:.1f}dB < {MIN_CREST_DB}dB")

    return {"file": path.name, "hf2_8": round(hf, 3), "vhf": round(vhf, 3),
            "lf": round(lf, 3), "mid": round(mid, 3),
            "centroid": round(centroid), "crest": round(crest, 1),
            "sr": sr, "dur": round(len(x) / sr, 3),
            "ok": not reasons, "why": "; ".join(reasons)}


def _files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.suffix.lower() in AUDIO_EXT)


def _report(rows: list[dict], header: str) -> int:
    print(header)
    print(f"  {'':5} {'file':30} {'<300':>6} {'mid':>6} {'2-8k':>6} {'>8k':>6} "
          f"{'centr':>6} {'crest':>6}  why")
    bad = 0
    for r in rows:
        if "error" in r:
            print(f"  {'?':5} {r['file']:30} {r['error']}")
            bad += 1
            continue
        bad += not r["ok"]
        print(f"  {'ok' if r['ok'] else 'FAIL':5} {r['file']:30} "
              f"{r['lf']:6.3f} {r['mid']:6.3f} {r['hf2_8']:6.3f} {r['vhf']:6.3f} "
              f"{r['centroid']:6.0f} {r['crest']:6.1f}  {r['why']}")
    if rows:
        live = [r for r in rows if "error" not in r]
        if live:
            print(f"\n  mean <300Hz {np.mean([r['lf'] for r in live]):.3f}   "
                  f"mid {np.mean([r['mid'] for r in live]):.3f}   "
                  f"2-8kHz {np.mean([r['hf2_8'] for r in live]):.3f}   "
                  f"centroid {np.mean([r['centroid'] for r in live]):.0f}Hz   "
                  f"{len(live) - bad}/{len(live)} within budget")
    return bad


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--baseline" in sys.argv:
        rows = [measure(p) for p in _files(SYNTH_DIR)]
        _report(rows, "=== currently shipping (the profile to match or improve on) ===")
        return 0

    targets = [Path(a) for a in args] or [REAL_DIR]
    rows = [measure(p) for t in targets for p in _files(t)]
    if "--json" in sys.argv:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    return 1 if _report(rows, "=== candidates ===") else 0


if __name__ == "__main__":
    raise SystemExit(main())
