"""_start_attack_with_kind lets the RL policy pick the skill category."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle(seed: int = 42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)  # past intro
    return bat


def test_basic_kind_picks_basic_skill():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    bat._start_attack_with_kind(a, b, "basic")
    assert a.action_state == "attacking"
    assert a.attack_used_kind.skill_type is SkillType.BASIC


def test_cooldown_kind_picks_cd_skill_when_available():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    a.skill_cd_ready_at = {}  # all CD skills available
    bat._start_attack_with_kind(a, b, "cooldown")
    assert a.action_state == "attacking"
    assert a.attack_used_kind.skill_type is SkillType.COOLDOWN


def test_cooldown_kind_falls_through_when_all_on_cooldown():
    """If no CD skill is available, the action is a no-op (no attack started)."""
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    # Mark all CD skills on cooldown
    for skill in a.skills_of_type(SkillType.COOLDOWN):
        a.skill_cd_ready_at[skill.id] = 999_999
    bat._start_attack_with_kind(a, b, "cooldown")
    # No attack should have started
    assert a.action_state != "attacking" or a.attack_used_kind is None or \
           a.attack_used_kind.skill_type is not SkillType.COOLDOWN


def test_unknown_kind_is_noop():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    bat._start_attack_with_kind(a, b, "bogus")
    assert a.action_state != "attacking"
