"""Render, verify and package a block of fights end to end, unattended.

The steps after "render" are the ones that get forgotten when a batch is run by
hand at midnight: the cover must be regenerated from the NEW render (an old
cover shows a frame from a render that no longer exists), captions must be
rewritten so the queue picks them up, and every short has to prove it holds the
frames its header claims before anything is scheduled. Doing them in one script
means a block either ships whole or reports exactly which step it stopped at.

It is meant to run detached (tools/run_detached.py): thirty fights is ~2.5h.

Steps:
  1. build_shorts_batch STEMS      render + build; refuses truncated raws/shorts
  2. build_covers_batch            covers for anything without one (--force for all)
  3. gen_captions --write          captions for the whole plan
  4. frame-count audit             every short in STEMS: frames/30 within 1s of duration
  5. publish_tiktok --status       queue view, so the log ends with the state

Usage:
  python3 tools/ship_block.py b22 b23 ... b51
  python3 tools/ship_block.py b22 ... --force-covers
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(label: str, cmd: list[str], tail: int = 6) -> bool:
    print(f"\n=== {label} ===", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip().splitlines()
    print("\n".join(out[-tail:]), flush=True)
    if r.returncode != 0:
        print(f"!!! {label} exited {r.returncode} — stopping here", flush=True)
    return r.returncode == 0


def _frames_ok(path: Path, fps: int = 30) -> tuple[bool, str]:
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True).stdout.strip()
    n = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                        "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1",
                        str(path)], capture_output=True, text=True).stdout.strip()
    try:
        d, f = float(dur), int(n)
    except ValueError:
        return False, f"unreadable ({dur!r}, {n!r})"
    ok = abs(f / fps - d) <= 1.0
    return ok, f"{d:.1f}s {f} frames"


def main() -> int:
    stems = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not stems:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    force = "--force-covers" in sys.argv

    if not run("1/5 render + build", [PY, "tools/build_shorts_batch.py", *stems], tail=4):
        return 1
    cover_cmd = [PY, "tools/build_covers_batch.py"] + (["--force"] if force else [])
    if not run("2/5 covers", cover_cmd, tail=2):
        return 1
    if not run("3/5 captions", [PY, "tools/gen_captions.py", "--write",
                                "pixel_battle/output/captions"], tail=2):
        return 1

    print("\n=== 4/5 frame-count + winner audit ===", flush=True)
    manifest = {e["script"][:3]: e for e in
                json.loads((ROOT / "pixel_battle/output/shorts/manifest.json").read_text())}
    # The render records who actually won. It must be the designated caster:
    # the cover names the winner's finisher and the caption is written around
    # that side. A simulation-vs-render gap on a thin HP margin flipped b18 once
    # (47s video, wrong winner) — this is the check that would have caught it.
    sys.path.insert(0, str(ROOT / "tools"))
    from gen_batch import BATCH
    designated = {r[0][:3]: r[4] for r in BATCH}
    bad = []
    for st in stems:
        e = manifest.get(st[:3])
        if not e or "short" not in e:
            bad.append(st)
            print(f"  {st:24} MISSING from manifest", flush=True)
            continue
        ok, why = _frames_ok(ROOT / e["short"])
        win_ok = e.get("winner") == designated.get(st[:3])
        if not win_ok:
            why += f"  WINNER {e.get('winner')} != designated {designated.get(st[:3])}"
        print(f"  {Path(e['short']).stem:24} {'ok ' if (ok and win_ok) else 'BAD'} {why}", flush=True)
        if not (ok and win_ok):
            bad.append(st)
    if bad:
        print(f"!!! {len(bad)} short(s) failed the audit: {bad}", flush=True)
        return 1

    run("5/5 queue", [PY, "tools/publish_tiktok.py", "--status"], tail=3)
    print("\nSHIP DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
