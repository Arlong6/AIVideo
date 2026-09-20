"""Fetch, screen, normalize and install the real-recording sound effect set.

THIS FILE IS THE RECORD. gen_batch.py exists because the arguments that built
b01-b21 lived only in shell history and could not be reproduced; the same
mistake with licensed third-party audio would be worse, because "where did this
file come from and may we use it" is a question that has to stay answerable.
Every effect below carries its source URL and licence.

All sources are CC0 on OpenGameArt, chosen because they are static file links
that need no login, no API key and no OAuth round-trip — Pixabay's API ignores
media_type and returns images (verified), and Freesound needs OAuth2 for
downloads.

WHY A SLOT-DEPENDENT BUDGET
---------------------------
audit_sfx.py enforces a balanced spectrum, and the reason is listening fatigue.
But fatigue comes from REPETITION: `hit` fires about 36 times in a 53-second
fight, while `ko` fires exactly once. Holding a one-shot finisher to the same
low-end ceiling as a sound that plays every 1.5 seconds throws away the weight
that makes a finisher land, and buys nothing — one bass-heavy impact per video
is not what fatigues an ear.

So slots are tagged `repeat` or `oneshot`, and only `repeat` has to pass the
strict gate. Every `oneshot` is still high-passed by the mixer (45-50Hz on all
buses) so the truly sub-audible rumble never reaches the master.

Usage:
  python3 pixel_battle/scripts/install_sfx_real.py --dry-run   # show the plan
  python3 pixel_battle/scripts/install_sfx_real.py             # fetch + install
"""
from __future__ import annotations

import subprocess
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "pixel_battle/assets/sfx_real"
CACHE = ROOT / ".cache/sfx_sources"
OGA = "https://opengameart.org/sites/default/files/"
UA = "Mozilla/5.0 (Macintosh) pixel-battle-sfx"

# Packs that arrive as archives. (zip name, OpenGameArt page, licence)
PACKS = {
    "thwack-1.0.zip": ("https://opengameart.org/content/thwack-sounds", "CC0"),
    "swishes.zip": ("https://opengameart.org/content/swishes-sound-pack", "CC0"),
    "rpg_sound_pack.zip": ("https://opengameart.org/content/rpg-sound-pack", "CC0"),
    "weapons-apparel.zip":
        ("https://opengameart.org/content/fantasy-weapons-and-apparel-sfx-library", "CC0"),
}
# Loose files, fetched by name from the same host.
LOOSE = {
    "thud2.wav": ("https://opengameart.org/content/metal-impact-sounds", "CC0"),
    "clink1_0.wav": ("https://opengameart.org/content/metal-impact-sounds", "CC0"),
    "bong1.wav": ("https://opengameart.org/content/metal-impact-sounds", "CC0"),
    "uff.wav": ("https://opengameart.org/content/various-sound-effects-0", "CC0"),
    "break_stone.wav": ("https://opengameart.org/content/various-sound-effects-0", "CC0"),
    "dull_explosion.wav": ("https://opengameart.org/content/various-sound-effects-0", "CC0"),
    "snd_gunshot1.wav": ("https://opengameart.org/content/various-sound-effects-0", "CC0"),
    "crush.wav": ("https://opengameart.org/content/various-sound-effects-0", "CC0"),
    "22 Pistol.wav": ("https://opengameart.org/content/gunshots", "CC0"),
}

# slot -> (source file in the pool, policy, max_ms, note)
#   repeat  : fires many times per fight, must pass audit_sfx's balance gate
#   oneshot : fires once, allowed the low-end weight a finisher needs
PLAN = {
    "hit":         ("thwack-1.0__thwack-02.wav", "repeat", 400,
                    "fist/blunt — the most repeated sound in the whole batch"),
    "crit":        ("thwack-1.0__thwack-06.wav", "repeat", 450,
                    "same family as hit, more snap so a crit reads as different"),
    "sword_hit":   ("clink1_0.wav", "repeat", 400, "metal clash"),
    "arrow_hit":   ("thud2.wav", "repeat", 400, "wooden thunk"),
    "magic_hit":   ("rpg_sound_pack__spell.wav", "repeat", 500, "arcane burst"),
    "sword_swing": ("swishes__swish-11.wav", "repeat", 350, "melee whoosh"),
    "bow_shot":    ("swishes__swish-13.wav", "repeat", 350, "string release + flight"),
    # snd_warp_in measured 39% in 2-8kHz once the onset anchoring stopped
    # truncating it — over the repeat budget, and it fires on every staff attack.
    "magic_cast":  ("rpg_sound_pack__shade15.wav", "repeat", 700, "spell shimmer"),
    # Four champions carry guns (jinx/deadeye/outlaw/forge), and this fires on
    # every shot they take — so it is a `repeat`, not the one-shot it was first
    # filed as. The original pick (snd_gunshot1) measured 82% below 300Hz and was
    # replaced with a real pistol recording that has midrange to place it.
    "gun_shot":    ("22 Pistol.wav", "repeat", 500, "pistol crack per shot"),
    "ko":          ("break_stone.wav", "oneshot", 1500, "the finisher landing"),
    "ult_blast":   ("dull_explosion.wav", "oneshot", 2000, "ultimate payoff"),
    "ult_flash":   ("bong1.wav", "oneshot", 900, "ultimate activation stab"),
    "ult_riser":   ("rpg_sound_pack__spell.wav", "oneshot", 2500, "tension riser"),
    "ultimate":    ("dull_explosion.wav", "oneshot", 2000, "legacy alias of ult_blast"),
    # crush.wav was 98% below 300Hz with 2% midrange — pure rumble, which is
    # too far even under the relaxed one-shot budget. A creature roar is also
    # simply the better sound for summoning a creature.
    "summon":      ("rpg_sound_pack__giant3.wav", "oneshot", 1200, "summoned creature roar"),
    "charge":      ("rpg_sound_pack__shade7.wav", "oneshot", 1500, "windup"),
}


def _fetch(name: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(OGA + urllib.parse.quote(name),
                                 headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        dest.write_bytes(r.read())


def build_pool(verbose: bool = True) -> Path:
    pool = CACHE / "pool"
    pool.mkdir(parents=True, exist_ok=True)
    for name in LOOSE:
        dest = pool / name
        if not dest.exists():
            _fetch(name, dest)
            if verbose:
                print(f"  fetched {name}")
    for zname in PACKS:
        zp = CACHE / zname
        if not zp.exists():
            _fetch(zname, zp)
            if verbose:
                print(f"  fetched {zname}")
        with zipfile.ZipFile(zp) as f:
            for m in f.namelist():
                if m.lower().endswith((".wav", ".ogg", ".flac")) and not m.startswith("__"):
                    tgt = pool / (Path(zname).stem + "__" + Path(m).name)
                    if not tgt.exists():
                        tgt.write_bytes(f.read(m))
    return pool


def normalize(src: Path, dst: Path, max_ms: int) -> dict:
    """48kHz mono, silence trimmed, de-clicked, peak-normalized, length-capped.

    Peak, not loudnorm: LUFS normalization measures over a window far longer
    than a 200ms transient and mangles it. Fades matter more than they look —
    a waveform that starts or stops mid-cycle clicks, and a click is broadband
    energy exactly where the ear is most sensitive, which is half of what makes
    a sound effect tiring over dozens of repeats.
    """
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-f", "f32le",
                        "-ac", "1", "-ar", "48000", "-"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(f"decode failed: {src.name}")
    x = np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)
    sr = 48000

    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak <= 0:
        raise RuntimeError(f"silent: {src.name}")

    # Anchor the window on the LOUDEST transient, not on the head of the file.
    #
    # The first version trimmed anything under -50dBFS from the front and then
    # capped the length. That silently destroyed "22 Pistol.wav": the recording
    # opens with 1.25 seconds of low room rumble, which sits above a -50dBFS
    # floor, so nothing was trimmed — and the 500ms cap then kept the rumble and
    # threw away the shot. The installed file measured 99% below 300Hz with 0.7%
    # midrange, and only the audit gate caught it.
    #
    # So: find the peak, walk back to where the signal was last quiet, and start
    # a few ms before that. The mixer places samples at an exact millisecond, so
    # the effect has to begin ON its attack or every cue lands late.
    env = np.abs(x)
    pk = int(np.argmax(env))
    quiet = peak * (10 ** (-35 / 20))
    pre = np.nonzero(env[:pk] < quiet)[0]
    start = int(pre[-1]) if len(pre) else 0
    start = max(0, start - int(sr * 0.005))          # 5ms of run-up
    tail = np.nonzero(env > peak * (10 ** (-50 / 20)))[0]
    end = int(tail[-1]) + 1 if len(tail) else len(x)
    x = x[start:max(end, start + 1)]

    x = x[:int(sr * max_ms / 1000)]
    n_in, n_out = int(sr * 0.005), int(sr * 0.020)
    if len(x) > n_in + n_out:
        x[:n_in] *= np.linspace(0, 1, n_in)
        x[-n_out:] *= np.linspace(1, 0, n_out)

    x = x / float(np.max(np.abs(x))) * (10 ** (-3 / 20))   # peak -3 dBFS

    import soundfile as sf
    dst.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(dst), x.astype(np.float32), sr, subtype="PCM_16")
    return {"dur": round(len(x) / sr, 3)}


def write_credits(installed: list[dict]) -> None:
    lines = [
        "# Sound effect sources",
        "",
        "Every file in this directory, where it came from and under what licence.",
        "Generated by `pixel_battle/scripts/install_sfx_real.py` — edit that, not this.",
        "",
        "All sources are CC0 (public domain dedication): no attribution is legally",
        "required, no permission needed, commercial use fine. Recorded here anyway,",
        "because a licence you cannot trace is a licence you cannot defend.",
        "",
        "| slot | policy | source file | from | licence |",
        "|---|---|---|---|---|",
    ]
    for r in installed:
        page, lic = r["page"], r["licence"]
        lines.append(f"| `{r['slot']}` | {r['policy']} | `{r['src']}` | "
                     f"[{page.rsplit('/', 1)[-1]}]({page}) | {lic} |")
    lines += [
        "",
        "## Policy",
        "",
        "`repeat` effects fire many times per fight and must pass the balance gate in",
        "`pixel_battle/scripts/audit_sfx.py`. `oneshot` effects fire once and are",
        "allowed the low-end weight a finisher needs; listening fatigue comes from",
        "repetition, and one heavy impact per video is not what causes it.",
        "",
    ]
    (OUT_DIR / "CREDITS.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    dry = "--dry-run" in sys.argv
    if dry:
        print(f"{'slot':14} {'policy':8} {'source':42} note")
        for slot, (src, policy, cap, note) in PLAN.items():
            print(f"{slot:14} {policy:8} {src[:42]:42} {note}")
        return 0

    print("building source pool...")
    pool = build_pool()

    installed = []
    for slot, (src, policy, cap, note) in PLAN.items():
        sp = pool / src
        if not sp.exists():
            print(f"  MISSING {slot}: {src}")
            continue
        info = normalize(sp, OUT_DIR / f"{slot}.wav", cap)
        page, lic = LOOSE.get(src, (None, None))
        if page is None:
            zname = src.split("__")[0] + ".zip"
            page, lic = PACKS.get(zname, ("(unknown)", "(unknown)"))
        installed.append({"slot": slot, "src": src, "policy": policy,
                          "page": page, "licence": lic, **info})
        print(f"  {slot:14} <- {src[:40]:40} {info['dur']:.2f}s")

    write_credits(installed)
    print(f"\ninstalled {len(installed)} effects to {OUT_DIR.relative_to(ROOT)}")
    print("next: python3 pixel_battle/scripts/audit_sfx.py   # screen what landed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
