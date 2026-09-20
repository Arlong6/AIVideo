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
The complaint is ear-ringing, and ringing does not care where a sound came from.
A harsh recording hurts; a warm synth does not. So this measures harshness, and
the numbers immediately showed that swapping naively would have made things
worse — the existing synthesized effects are dark (4% of energy in 2-8kHz, 67%
below 300Hz), while the first batch of real CC0 impacts sampled was far brighter
(53% in 2-8kHz). Replacing one with the other unscreened would have moved the
channel toward fatigue, not away from it.

  hf2_8       Fraction of energy in 2-8kHz. This is where the ear is most
              sensitive and where listening fatigue is generated. The single
              most important number here.
  vhf         Above 8kHz. Sizzle. Tolerable in small amounts, grating in a
              sound that fires thirty times per video.
  lf          Below 300Hz. Body and weight. A hit with none of this reads as
              thin and the ear compensates by focusing on the harsh part.
  centroid    Spectral centre of mass in Hz — a single-number brightness proxy.
  crest       Peak-to-RMS in dB. Very low means it has been squashed flat, which
              is exhausting over repetition.

Budgets below are derived from the existing set, which arlong has watched many
hours of. They keep a candidate no brighter than what the channel already ships.

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

# Measured over the 20 shipped effects: mean hf2_8 0.042, worst 0.392
# (sword_hit); mean centroid 684Hz, worst 1866Hz. A replacement is allowed to be
# as bright as the brightest thing already in rotation, and no brighter.
MAX_HF_2_8 = 0.40         # fraction of energy in 2-8kHz
MAX_VHF = 0.12            # fraction above 8kHz
MAX_CENTROID = 2000.0     # Hz
MIN_CREST_DB = 6.0        # below this it has been flattened into a wall


def _load(path: Path) -> tuple[np.ndarray, int]:
    """Mono float64. soundfile covers wav/ogg/flac; mp3 goes out to ffmpeg."""
    if path.suffix.lower() == ".mp3":
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
             "-ac", "1", "-ar", "48000", "-"], capture_output=True)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode()[:200])
        return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64), 48000
    import soundfile as sf
    x, sr = sf.read(str(path), dtype="float32", always_2d=True)
    return x.mean(axis=1).astype(np.float64), sr


def measure(path: Path) -> dict:
    x, sr = _load(path)
    if not len(x) or float(np.max(np.abs(x))) <= 0:
        return {"file": path.name, "error": "silent or unreadable"}
    x = x / float(np.max(np.abs(x)))          # loudness must not sway the verdict

    n = 1 << 14
    seg = x[:n] if len(x) >= n else np.pad(x, (0, n - len(x)))
    e = np.abs(np.fft.rfft(seg * np.hanning(n))) ** 2
    f = np.fft.rfftfreq(n, 1 / sr)
    tot = float(e.sum()) + 1e-12

    hf = float(e[(f >= 2000) & (f < 8000)].sum() / tot)
    vhf = float(e[f >= 8000].sum() / tot)
    lf = float(e[f < 300].sum() / tot)
    centroid = float((f * e).sum() / tot)
    rms = float(np.sqrt(np.mean(x ** 2)))
    crest = 20 * np.log10(1.0 / (rms + 1e-12))

    reasons = []
    if hf > MAX_HF_2_8:
        reasons.append(f"2-8kHz {hf:.0%} > {MAX_HF_2_8:.0%}")
    if vhf > MAX_VHF:
        reasons.append(f">8kHz {vhf:.0%} > {MAX_VHF:.0%}")
    if centroid > MAX_CENTROID:
        reasons.append(f"centroid {centroid:.0f}Hz > {MAX_CENTROID:.0f}Hz")
    if crest < MIN_CREST_DB:
        reasons.append(f"crest {crest:.1f}dB < {MIN_CREST_DB}dB")

    return {"file": path.name, "hf2_8": round(hf, 3), "vhf": round(vhf, 3),
            "lf": round(lf, 3), "centroid": round(centroid), "crest": round(crest, 1),
            "sr": sr, "dur": round(len(x) / sr, 3),
            "ok": not reasons, "why": "; ".join(reasons)}


def _files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.suffix.lower() in AUDIO_EXT)


def _report(rows: list[dict], header: str) -> int:
    print(header)
    print(f"  {'':5} {'file':30} {'2-8kHz':>7} {'>8kHz':>6} {'<300Hz':>7} "
          f"{'centr':>6} {'crest':>6}  why")
    bad = 0
    for r in rows:
        if "error" in r:
            print(f"  {'?':5} {r['file']:30} {r['error']}")
            bad += 1
            continue
        bad += not r["ok"]
        print(f"  {'ok' if r['ok'] else 'HARSH':5} {r['file']:30} "
              f"{r['hf2_8']:7.3f} {r['vhf']:6.3f} {r['lf']:7.3f} "
              f"{r['centroid']:6.0f} {r['crest']:6.1f}  {r['why']}")
    if rows:
        live = [r for r in rows if "error" not in r]
        if live:
            print(f"\n  mean 2-8kHz {np.mean([r['hf2_8'] for r in live]):.3f}   "
                  f"mean centroid {np.mean([r['centroid'] for r in live]):.0f}Hz   "
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
