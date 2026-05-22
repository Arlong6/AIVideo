"""Engine-layer hitstop — a short freeze on every hit."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.engine.battle import HITSTOP_MS, HITSTOP_MS_HEAVY, _hitstop_for, _hit_causes_hitstop
from pixel_battle.engine.skill import SkillType
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


def test_hitstop_skips_plain_basic_hits():
    # A non-crit basic hit must NOT trigger hitstop — basic spam should not stutter.
    assert _hit_causes_hitstop(False, SkillType.BASIC) is False


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
