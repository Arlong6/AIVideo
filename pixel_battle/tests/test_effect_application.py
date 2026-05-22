"""Skills apply status effects — opponent effects on hit, self effects on cast."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.engine.battle import STAGGER_MS
from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.engine.effects import StatusEffect, ROOT, TENACITY, SkillApplies
from pixel_battle.engine.skill import SkillType


def test_cc_skill_roots_defender_on_hit():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    atk, dfn = env.left, env.right
    atk.pos_x, dfn.pos_x = 240.0, 300.0
    atk.accuracy = 1.0
    # Force the attacker's skill to one that applies root.
    skill = atk.skills_of_type(SkillType.BASIC)[0]
    skill.applies = SkillApplies(effect=ROOT, duration_ms=1200,
                                 magnitude=1.0, target="opponent")
    atk.attack_used_kind = skill
    b._resolve_attack_hit(atk, dfn)
    assert dfn.has_effect(ROOT)
    assert dfn.effect_of(ROOT).remaining_ms == 1200


def test_tenacity_reduces_applied_stagger():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    atk, dfn = env.left, env.right
    atk.pos_x, dfn.pos_x = 240.0, 300.0
    atk.accuracy = 1.0
    dfn.effects.append(StatusEffect(kind=TENACITY, remaining_ms=5000,
                                    magnitude=0.5))
    b._resolve_attack_hit(atk, dfn)
    # Stagger applied to a tenacious defender is halved.
    # brick_phone's basic stagger_ms == 0, so engine uses STAGGER_MS (300).
    # tenacity magnitude 0.5 → int(300 * 0.5) == 150.
    assert dfn._stagger_remaining_ms == int(STAGGER_MS * 0.5)


def test_self_buff_applies_to_caster_on_cast():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    caster = env.left
    caster.mp = 100
    # Give the caster's special a self-buff applies, then start it.
    sp = caster.skills_of_type(SkillType.SPECIAL)
    assert sp, "character must have a special"
    sp[0].applies = SkillApplies(effect=TENACITY, duration_ms=4000,
                                 magnitude=0.5, target="self")
    b._start_attack_with_kind(caster, env.right, "special")
    assert caster.has_effect(TENACITY)
