"""Engine-layer hitstop — a short freeze on every hit."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.engine.battle import HITSTOP_MS, HITSTOP_MS_HEAVY, _hitstop_for
from pixel_battle.rl.env import PixelBattleEnv


def test_hitstop_for_crit_is_heavier():
    assert _hitstop_for(False) == HITSTOP_MS
    assert _hitstop_for(True) == HITSTOP_MS_HEAVY
    assert HITSTOP_MS_HEAVY > HITSTOP_MS > 0


def test_tick_freezes_and_does_not_advance_clock():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    b._hitstop_remaining = HITSTOP_MS          # force a freeze
    before = b.elapsed_ms
    b.tick_ms(16)
    assert b.elapsed_ms == before               # clock paused during hitstop
    assert b._hitstop_remaining == HITSTOP_MS - 16


def test_tick_resumes_after_hitstop_drains():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    b._hitstop_remaining = 10
    b.tick_ms(16)                               # drains 10 -> -6, still a frozen call
    assert b._hitstop_remaining <= 0
    before = b.elapsed_ms
    b.tick_ms(16)                               # no longer frozen -> clock advances
    assert b.elapsed_ms > before


def test_a_landed_hit_sets_hitstop():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    atk, dfn = env.left, env.right
    atk.pos_x, dfn.pos_x = 240.0, 300.0         # 60 px apart — inside melee range
    atk.accuracy = 1.0                           # guarantee the accuracy roll passes
    b._hitstop_remaining = 0
    b._resolve_attack_hit(atk, dfn)
    assert b._hitstop_remaining >= HITSTOP_MS    # HITSTOP_MS, or _HEAVY on a crit
