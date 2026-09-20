"""Report each fight's winner by pure simulation — no video encoding.

Rendering a fight takes minutes; the winner only depends on the simulation, so
this runs the same env/timeline headlessly and reports the outcome in seconds.
Use it to check batch variety (all-left-wins kills the "who wins?" hook) before
committing to a re-render.

Usage:
  python3 tools/check_winners.py                     # every b*.yaml
  python3 tools/check_winners.py path/to/one.yaml    # specific files
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))


def simulate(path: Path) -> dict:
    """Winner by simulation — advanced the way the RENDERER advances the fight.

    This was a plain env.step() loop, and it was quietly wrong. The renderer
    ticks the engine at `ENGINE_MS * dt_scale` during slow-mo while still
    applying one scripted decision per frame, so the choreography lands more
    damage than a constant-dt loop predicts. With the old 40-HP buffer on the
    caster the gap never changed an outcome; once the buffer was cut for a
    comeback arc, this file said "right wins" for a fight the renderer gave to
    left, with the ultimate never firing at all. See tools/sim_render.py.
    """
    from sim_render import simulate as _sim
    r = _sim(path)
    return {"winner": r["winner"], "left_hp": r["left_hp"],
            "right_hp": r["right_hp"], "ko": r["ko"]}


def main() -> int:
    args = sys.argv[1:]
    files = ([Path(a) for a in args] if args
             else sorted((ROOT / "pixel_battle/data/scripts").glob("b*.yaml")))
    rows = []
    for f in files:
        try:
            r = simulate(f)
        except Exception as e:                      # one bad file must not hide the rest
            print(f"{f.name:30} ERROR {type(e).__name__}: {e}")
            rows.append((f.name, "ERROR"))
            continue
        print(f"{f.name:30} winner={str(r['winner']):5} "
              f"L={r['left_hp']:6} R={r['right_hp']:6} ko={r['ko']}")
        rows.append((f.name, r["winner"]))

    tally = {}
    for _, w in rows:
        tally[w] = tally.get(w, 0) + 1
    print(f"\n{len(rows)} fights: " + ", ".join(f"{k}={v}" for k, v in sorted(
        tally.items(), key=lambda kv: str(kv[0]))))
    lefts = tally.get("left", 0)
    if rows and lefts == len(rows):
        print("WARNING: every fight is won by the LEFT side — the "
              "'who wins?' hook is predictable across the batch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
