"""Engine-layer hitstop — a short freeze on every hit."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.engine.battle import (
    HITSTOP_MS, HITSTOP_MS_BASIC_CRIT, HITSTOP_MS_HEAVY, HITSTOP_MS_HEAVY_CRIT,
    _hitstop_for, _hit_causes_hitstop,
)
from pixel_battle.engine.skill import SkillType
from pixel_battle.rl.env import PixelBattleEnv


def test_hitstop_for_crit_is_heavier():
    # basic non-crit < basic crit; non-basic non-crit < non-basic crit
    assert _hitstop_for(False, SkillType.BASIC) == HITSTOP_MS
    assert _hitstop_for(True, SkillType.BASIC) == HITSTOP_MS_BASIC_CRIT
    assert _hitstop_for(False, SkillType.COOLDOWN) == HITSTOP_MS_HEAVY
    assert _hitstop_for(True, SkillType.COOLDOWN) == HITSTOP_MS_HEAVY_CRIT
    assert HITSTOP_MS_HEAVY_CRIT > HITSTOP_MS_HEAVY > HITSTOP_MS > 0


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


def test_basic_hit_causes_hitstop():
    # Every hit now triggers at least a brief hitstop so the defender flinch is readable.
    assert _hit_causes_hitstop(False, SkillType.BASIC) is True


def test_hitstop_fires_on_crit_basic():
    assert _hit_causes_hitstop(True, SkillType.BASIC) is True


def test_hitstop_fires_on_skill_hits():
    assert _hit_causes_hitstop(False, SkillType.COOLDOWN) is True
    assert _hit_causes_hitstop(False, SkillType.SPECIAL) is True
    assert _hit_causes_hitstop(False, SkillType.ULTIMATE) is True


def test_special_hit_sets_hitstop_via_resolve():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    atk, dfn = env.left, env.right
    atk.pos_x, dfn.pos_x = 240.0, 300.0
    atk.accuracy = 1.0
    special = atk.skills_of_type(SkillType.SPECIAL)[0]
    atk.attack_used_kind = special
    atk.mp = 100
    b._hitstop_remaining = 0
    b._resolve_attack_hit(atk, dfn)
    assert b._hitstop_remaining > 0          # a special hit always freezes


def test_basic_non_crit_sets_hitstop_via_resolve():
    """Basic non-crit hit must now set _hitstop_remaining > 0."""
    env = PixelBattleEnv(seed=42)
    b = env.battle
    atk, dfn = env.left, env.right
    atk.pos_x, dfn.pos_x = 240.0, 300.0
    atk.accuracy = 1.0
    basic = atk.skills_of_type(SkillType.BASIC)[0]
    atk.attack_used_kind = basic
    b._hitstop_remaining = 0
    # Drive rng so crit won't fire: set crit-check seed to always fail
    # The simplest way: override the rng to always return 0.5 for crit roll.
    import unittest.mock as _mock
    with _mock.patch.object(b.rng, "roll_check", side_effect=lambda p: p >= 1.0):
        b._resolve_attack_hit(atk, dfn)
    assert b._hitstop_remaining > 0, (
        "Basic non-crit hit must set hitstop so defender flinch is always readable"
    )
