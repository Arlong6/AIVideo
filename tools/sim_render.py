"""Simulate a fight the way the RENDERER advances it, without drawing anything.

Why this exists
---------------
check_winners, check_pacing and check_arc all ran a plain `env.step()` loop,
which is NOT how the fight actually plays out on screen. The render loop in
`pixel_battle/rl/play.py` has a slow-mo branch: whenever `_slowmo_remaining_ms`
is positive it ticks the engine at `ENGINE_MS * dt_scale` — about 2ms instead of
16.67ms — while still applying one scripted decision per frame. That gives the
choreography up to eight times as many decisions per engine-millisecond, and
correspondingly more damage lands.

The old ATK_REMAIN of 40 had enough slack to hide that gap. Dropping it to 16 for
the comeback arc did not: the pure sim said the caster reached its ultimate with
16 HP, the renderer killed it first, and b18 came out 47.1s long with the wrong
winner. The pure sim had been quietly wrong the whole time — it only started
mattering when the margin got thin.

Modelled from play.py, the slow-mo rules are:
  hit            45ms at dt_scale 0.12                     (play.py:1578-1579)
  pre-KO hit     200ms at 0.3, on a hit or crit that kills (play.py:1581-1583, 1610-1612)
  ultimate       150ms at 0.3                              (play.py:1957-1958)
`_slowmo_remaining_ms` is decremented by a full ENGINE_MS per frame regardless of
the scale, exactly as the renderer does.

This still is not the renderer — it does not run the KO sequence or the ultimate
sequence controller, both of which impose their own dt_scale. Treat it as much
closer, not exact: a change to the HP budget should still be confirmed by one
real render before a batch goes out.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pixel_battle.rl.render_sim import ENGINE_MS, RenderPacer  # noqa: E402

IMPACT_TYPES = {"hit", "crit", "ko"}


def simulate(path: Path, render_accurate: bool = True) -> dict:
    """Run one fight headlessly. Returns winner, HP curve and the event log."""
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.script.loader import load_fight_file
    import yaml as _yaml

    meta = _yaml.safe_load(Path(path).read_text(encoding="utf-8"))
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
    pacer = RenderPacer(env) if render_accurate else None
    curve, nxt = [], 0

    # Frame budget, not engine-time budget: under slow-mo the engine advances
    # less per frame, so a fight needs more frames than duration/TICK to reach
    # its ultimate. The renderer caps at 60 seconds of video.
    for _ in range(int(60 * 60)):
        if b.left.is_ko() or b.right.is_ko():
            break
        if b.elapsed_ms >= nxt:
            curve.append((b.elapsed_ms / 1000.0,
                          b.left.hp / l0 * 100, b.right.hp / r0 * 100))
            nxt += 2000
        la, ra = d.decide(b)
        if pacer is not None:
            pacer.step(la, ra)
        else:
            env.step((la, ra))

    curve.append((b.elapsed_ms / 1000.0, b.left.hp / l0 * 100, b.right.hp / r0 * 100))

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

    return {
        "winner": w,
        "left_hp": round(b.left.hp, 1),
        "right_hp": round(b.right.hp, 1),
        "ko": b.left.is_ko() or b.right.is_ko(),
        "ult_fired": any(e.type.value == "ultimate_start" for e in b.events),
        "events": list(b.events),
        "impacts": [e.t_ms / 1000.0 for e in b.events if e.type.value in IMPACT_TYPES],
        "curve": curve,
        "caster": "right" if meta.get("right_start_mp") else "left",
        "end_ms": b.elapsed_ms,
    }
