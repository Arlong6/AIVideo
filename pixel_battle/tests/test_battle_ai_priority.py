"""AI skill-choice priority: ultimate > CD-skill (off-cd) > special (affordable) > basic."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle_in_range(seed=42):
    """Make battle where attacker is in melee range of defender."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # within MELEE_RANGE (110)
    return bat, a, b


def test_cd_skill_chosen_when_off_cooldown():
    """When CD skill is off cooldown, AI picks it (with high probability) over basic."""
    bat, a, b = _battle_in_range(seed=42)
    # Drain MP so specials are unavailable
    a.mp = 0
    chosen = []
    for _ in range(20):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.last_attack_ms = -10000
        a.skill_cd_ready_at = {}  # always off CD
        bat._start_attack(a, b)
        chosen.append(a.attack_used_kind.id)
    assert "screw_dart" in chosen, f"Expected screw_dart in {chosen}"


def test_cd_skill_skipped_when_on_cooldown():
    """When CD skill is on cooldown, AI falls back to basic (MP=0)."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0
    a.skill_cd_ready_at["screw_dart"] = 999_999  # far future
    a.last_attack_ms = -10000
    bat._start_attack(a, b)
    assert a.attack_used_kind.id == "headbutt"


def test_special_chosen_when_affordable_and_no_cd():
    """No CD skills off-cd, but specials affordable → AI may pick special."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 50
    a.skill_cd_ready_at["screw_dart"] = 999_999  # gate out CD
    chosen = []
    for _ in range(20):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.last_attack_ms = -10000
        bat._start_attack(a, b)
        chosen.append(a.attack_used_kind.skill_type)
    # Should see at least one SPECIAL across 20 rolls (40% prob each)
    assert SkillType.SPECIAL in chosen, f"Expected SPECIAL in {chosen}"


def test_basic_chosen_when_nothing_else_available():
    bat, a, b = _battle_in_range(seed=1)
    a.mp = 0
    a.skill_cd_ready_at["screw_dart"] = 999_999
    a.last_attack_ms = -10000
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
