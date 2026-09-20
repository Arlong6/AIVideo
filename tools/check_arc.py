"""Show how a fight's HP bars move over time — the drama, not the outcome.

check_winners.py answers "who wins" and check_pacing.py answers "is anything
happening". Neither catches the failure that actually loses viewers: a fight
where both bars descend in lockstep for 45 seconds. Measured on b18 before this
existed, the two sides never diverged by more than 8% — a viewer glancing at the
bars at any moment saw a dead heat, so there was nothing to stay for.

What this reports:
  swings   how many times the lead changes hands (0 = a metronome)
  max_gap  the biggest visible gap, i.e. how bad it ever looks for the loser
  frozen   the longest stretch either bar does not move at all. A bar stuck at
           93% for fifteen seconds reads as broken, and over-suppressing one
           side to manufacture a swing causes exactly that.
  end      each side's HP at the finisher — the winner should be LOW, or the
           ultimate is a formality rather than a comeback.

Usage:
  python3 tools/check_arc.py                 # every b*.yaml
  python3 tools/check_arc.py b18             # prefix match
  python3 tools/check_arc.py --curve b18     # print the full sampled curve
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SAMPLE_MS = 2000
LEAD_EPS = 5.0        # percentage points before a lead counts as visible
FROZEN_WARN = 8.0     # seconds a bar may sit still before it looks broken


def curve(path: Path) -> dict:
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
        hp, mp = meta.get(f"{side}_start_hp"), meta.get(f"{side}_start_mp")
        if hp is not None:
            f.hp = hp
            if hasattr(f, "hp_max"):
                f.hp_max = max(getattr(f, "hp_max", hp), hp)
        if mp is not None:
            f.mp = min(getattr(f, "mp_max", mp), mp)

    l0, r0 = b.left.hp, b.right.hp
    pts, nxt = [], 0
    for _ in range(int(meta.get("duration_ms", 53000) / 16) + 200):
        if b.left.is_ko() or b.right.is_ko():
            break
        if b.elapsed_ms >= nxt:
            pts.append((b.elapsed_ms / 1000.0,
                        b.left.hp / l0 * 100, b.right.hp / r0 * 100))
            nxt += SAMPLE_MS
        la, ra = d.decide(b)
        env.step((la, ra))
    pts.append((b.elapsed_ms / 1000.0, b.left.hp / l0 * 100, b.right.hp / r0 * 100))
    return {"pts": pts, "caster": "right" if meta.get("right_start_mp") else "left"}


def analyse(c: dict) -> dict:
    pts = c["pts"]
    leads = []
    for _, l, r in pts:
        leads.append("L" if l > r + LEAD_EPS else ("R" if r > l + LEAD_EPS else "="))
    seen = [x for x in leads if x != "="]
    swings = sum(1 for a, b in zip(seen, seen[1:]) if a != b)
    max_gap = max(abs(l - r) for _, l, r in pts)

    frozen = 0.0
    for idx in (1, 2):
        run_start = None
        for i in range(1, len(pts)):
            if abs(pts[i][idx] - pts[i - 1][idx]) < 0.5:
                run_start = pts[i - 1][0] if run_start is None else run_start
                frozen = max(frozen, pts[i][0] - run_start)
            else:
                run_start = None

    end_l, end_r = pts[-1][1], pts[-1][2]
    win_end = end_r if c["caster"] == "right" else end_l
    return {"swings": swings, "max_gap": round(max_gap, 1),
            "frozen": round(frozen, 1), "win_end": round(win_end, 1),
            "ok": swings >= 1 and frozen <= FROZEN_WARN and win_end <= 30}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    scripts = sorted((ROOT / "pixel_battle/data/scripts").glob("b*.yaml"))
    if args:
        scripts = [p for p in scripts if any(p.name.startswith(a) for a in args)]
    if not scripts:
        print("no matching fight scripts", file=sys.stderr)
        return 2

    show_curve = "--curve" in sys.argv
    bad = 0
    for p in scripts:
        try:
            c = curve(p)
            r = analyse(c)
        except Exception as e:
            print(f"{p.stem:26} ERROR {type(e).__name__}: {e}")
            bad += 1
            continue
        bad += not r["ok"]
        why = []
        if r["swings"] < 1:
            why.append("no lead change")
        if r["frozen"] > FROZEN_WARN:
            why.append(f"a bar sat still {r['frozen']:.0f}s")
        if r["win_end"] > 30:
            why.append(f"winner ends at {r['win_end']:.0f}% (no comeback)")
        print(f"  {'ok' if r['ok'] else 'FLAT':5} {p.stem:26} "
              f"swings={r['swings']}  max_gap={r['max_gap']:5.1f}%  "
              f"frozen={r['frozen']:4.1f}s  winner_end={r['win_end']:5.1f}%  "
              f"{'; '.join(why)}")
        if show_curve:
            print(f"      {'s':>4} {'left':>7} {'right':>7}")
            for t, l, rr in c["pts"]:
                print(f"      {t:4.0f} {l:6.0f}% {rr:6.0f}%")
    print(f"\n{len(scripts) - bad}/{len(scripts)} have a readable arc")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
