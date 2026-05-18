"""P4: Cast pushback creates space when CD/special attacks fire."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle_in_range(seed=42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # in range
    return bat, a, b


def test_cd_skill_attack_pushes_attacker_backward():
    """When a CD skill is chosen, attacker.vel_x becomes negative-toward-defender."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0  # gate out specials
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1  # facing right (defender is right)
    a.vel_x = 0.0
    b.vel_x = 0.0
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found, "Couldn't force CD skill choice"
    # facing=1 means defender is right → attacker pushback should be leftward (negative vel_x)
    assert a.vel_x < 0, f"Expected attacker pushed back, got vel_x={a.vel_x}"


def test_cd_skill_attack_pushes_defender_slightly():
    """Defender gets a small push away from attacker."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found
    # Defender should drift rightward (away from attacker who is left)
    assert b.vel_x > 0, f"Expected defender drifted away, got vel_x={b.vel_x}"


def test_basic_attack_does_not_pushback():
    """Basic skill: no cast pushback."""
    bat, a, b = _battle_in_range(seed=1)
    a.mp = 0
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.last_attack_ms = -10000
    a.facing = 1
    a.vel_x = 0.0
    b.vel_x = 0.0
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
    assert a.vel_x == 0.0
    assert b.vel_x == 0.0
