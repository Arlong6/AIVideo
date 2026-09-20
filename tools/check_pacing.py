"""Report each fight's hit distribution by pure simulation — no video encoding.

A fight can pick a correct winner and still be unwatchable. b12_shade_deadeye
lands ten hits in its first 6.5 seconds and then nothing at all until the KO at
~44s: two ranged fighters holding distance, neither closing. That is 38 seconds
of dead air, and no amount of overlay work in post rescues it — the fix belongs
in the fight script.

check_winners.py already proves the simulation alone answers questions that
would otherwise cost a 3.5-minute render. This asks the pacing question the same
way, so a whole batch can be audited in seconds before committing to a re-render.

Times here are ENGINE ms, not video ms: slow-mo and hitstop stretch the recorded
video (b01's KO is at engine 45404 but video 47850). That divergence is small
next to the gaps this tool is looking for, and using engine time is what lets it
skip rendering entirely. Do not reuse these numbers to cue overlays.

Usage:
  python3 tools/check_pacing.py                      # every b*.yaml
  python3 tools/check_pacing.py b12 b18              # prefix match
  python3 tools/check_pacing.py --max-gap 5.0        # stricter threshold
  python3 tools/check_pacing.py --json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# A viewer forgives a couple of seconds between blows; six is a stall. Chosen
# against the measured spread: b01 (healthy) peaks at 3.2s, b12 (broken) at 37.8s.
DEFAULT_MAX_GAP = 6.0

# Events that read on screen as "something landed".
IMPACT_TYPES = {"hit", "crit", "ko"}


def simulate(path: Path) -> dict:
    """Run the fight headlessly and return its impact timeline in engine ms."""
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

    impacts = [ev.t_ms / 1000.0 for ev in b.events
               if ev.type.value in IMPACT_TYPES]
    end_s = (b.events[-1].t_ms / 1000.0) if b.events else 0.0
    return {"impacts": impacts, "end_s": end_s}


def analyse(sim: dict, max_gap: float) -> dict:
    """Turn a timeline into the numbers that decide whether it is watchable."""
    hits, end_s = sim["impacts"], sim["end_s"]
    if not hits:
        return {"n": 0, "max_gap": end_s, "gap_at": 0.0, "end_s": end_s,
                "ok": False, "why": "no impacts at all"}

    # The lead-in and the tail count: silence before the first blow and after
    # the last one is just as dead as silence in the middle.
    marks = [0.0] + hits + [end_s]
    gaps = [(marks[i + 1] - marks[i], marks[i]) for i in range(len(marks) - 1)]
    worst, at = max(gaps, key=lambda g: g[0])
    ok = worst <= max_gap
    return {"n": len(hits), "max_gap": round(worst, 1), "gap_at": round(at, 1),
            "end_s": round(end_s, 1), "ok": ok,
            "why": "" if ok else f"{worst:.1f}s with nothing landing, from {at:.1f}s"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    max_gap = DEFAULT_MAX_GAP
    if "--max-gap" in sys.argv:
        max_gap = float(sys.argv[sys.argv.index("--max-gap") + 1])

    scripts = sorted((ROOT / "pixel_battle/data/scripts").glob("b*.yaml"))
    if args:
        scripts = [p for p in scripts if any(p.name.startswith(a) for a in args)]
    if not scripts:
        print("no matching fight scripts", file=sys.stderr)
        return 2

    rows, bad = [], 0
    for p in scripts:
        try:
            r = analyse(simulate(p), max_gap)
        except Exception as e:              # one bad file must not hide the rest
            print(f"{p.stem:26} ERROR {type(e).__name__}: {e}")
            rows.append({"stem": p.stem, "error": f"{type(e).__name__}: {e}"})
            bad += 1
            continue
        r["stem"] = p.stem
        rows.append(r)
        if not r["ok"]:
            bad += 1
        if not as_json:
            flag = "  OK  " if r["ok"] else " STALL"
            print(f"{flag} {p.stem:26} impacts={r['n']:3}  "
                  f"max_gap={r['max_gap']:5.1f}s @ {r['gap_at']:5.1f}s  "
                  f"len={r['end_s']:5.1f}s  {r['why']}")

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"\n{len(rows) - bad}/{len(rows)} within {max_gap:.0f}s max gap")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
