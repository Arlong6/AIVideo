"""Generate a VS cover for every short listed in output/shorts/manifest.json.

The covers are what gets uploaded alongside each video (TikTok cover /
Shorts thumbnail), so they must be regenerated whenever the batch is
re-rendered — a cover cut from an older render shows the wrong frame.

Writes pixel_battle/output/covers/<stem>.png (1080x1920) and, with
--wide, <stem>_wide.png (1280x720) for 16:9 reposting.

Usage:
  python3 tools/build_covers_batch.py [--wide] [--force]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "pixel_battle/output/shorts/manifest.json"
OUT_DIR = ROOT / "pixel_battle/output/covers"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wide", action="store_true",
                    help="also write a 1280x720 center-cropped cover")
    ap.add_argument("--force", action="store_true",
                    help="regenerate covers that already exist")
    a = ap.parse_args()

    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    ok, skipped, failed = 0, 0, []
    for e in entries:
        if "error" in e or "short" not in e:
            failed.append((e.get("script", "?"), "no short in manifest"))
            continue
        stem = Path(e["short"]).stem
        video = ROOT / e["short"]
        if not video.exists():
            failed.append((stem, f"missing video: {e['short']}"))
            continue

        cover = OUT_DIR / f"{stem}.png"
        if cover.exists() and not a.force:
            print(f"    {stem}: exists, skipped")
            skipped += 1
            continue

        # Name the finishing ult after whoever actually wins — half the batch is
        # won by the right-hand fighter, whose ult is the one on screen.
        finisher = e["left"] if e.get("winner") == "left" else e["right"]
        cmd = [sys.executable, "-m", "pixel_battle.scripts.gen_thumbnail",
               str(video), e["left"], e["right"], str(cover),
               "--finisher", finisher]
        if a.wide:
            cmd += ["--wide", str(OUT_DIR / f"{stem}_wide.png")]

        print(f"=== {stem} ===", flush=True)
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        if r.returncode != 0 or not cover.exists():
            failed.append((stem, (r.stderr or r.stdout).strip()[-300:]))
            print(f"    FAILED: {failed[-1][1]}")
            continue
        ok += 1
        print(f"    -> {cover.relative_to(ROOT)}")

    print(f"\ncovers: {ok} built, {skipped} skipped, {len(failed)} failed")
    for stem, why in failed:
        print(f"  FAILED {stem}: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
