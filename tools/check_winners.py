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


def simulate(path: Path) -> dict:
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.script.loader import load_fight_file
    import yaml as _yaml

    meta = _yaml.safe_load(path.read_text(encoding="utf-8"))
    d = load_fight_file(str(path))
    env = PixelBattleEnv(left_id=meta["left"], right_id=meta["right"],
                         seed=meta.get("seed", 7))
    env.reset()
    b = env.battle
    for side in ("left", "right"):
        f = getattr(b, side)
        hp = meta.get(f"{side}_start_hp")
        mp = meta.get(f"{side}_start_mp")
        if hp is not None:
            f.hp = hp
            if hasattr(f, "hp_max"):
                f.hp_max = max(getattr(f, "hp_max", hp), hp)
        if mp is not None:
            f.mp = min(getattr(f, "mp_max", mp), mp)

    limit = int(meta.get("duration_ms", 53000) / 16) + 200
    for _ in range(limit):
        if b.left.is_ko() or b.right.is_ko():
            break
        la, ra = d.decide(b)
        env.step((la, ra))

    # Same rule as play._render_fight: KO first, then higher HP on timeout.
    if b.right.is_ko() and not b.left.is_ko():
        w = "left"
    elif b.left.is_ko() and not b.right.is_ko():
        w = "right"
    elif b.left.hp > b.right.hp:
        w = "left"
    elif b.right.hp > b.left.hp:
        w = "right"
    else:
        w = None
    return {"winner": w, "left_hp": round(b.left.hp, 1),
            "right_hp": round(b.right.hp, 1),
            "ko": b.left.is_ko() or b.right.is_ko()}


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
