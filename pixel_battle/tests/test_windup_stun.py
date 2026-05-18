"""P5: Windup stun gates defender AI while attacker casts."""
from pixel_battle.engine.character import Character
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.rng import BattleRNG


def test_character_has_windup_stun_field_defaulting_to_zero():
    """New field defaults to 0 so existing code paths are unaffected."""
    c = Character.load("brick_phone")
    assert c.windup_stun_until_ms == 0


def test_reset_physics_clears_windup_stun():
    """reset_physics zeroes the stun timer (e.g., between rounds)."""
    c = Character.load("brick_phone")
    c.windup_stun_until_ms = 12345
    c.reset_physics(initial_x=100.0, facing=1)
    assert c.windup_stun_until_ms == 0


def test_ai_skips_when_within_windup_stun():
    """While elapsed_ms < windup_stun_until_ms, AI takes no action — pos_x unchanged."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(1000)  # past intro; elapsed_ms == 1000

    # Position out of range so the only thing AI could possibly do is walk toward opp
    a.pos_x = 100.0
    b.pos_x = 380.0
    a.vel_x = 0.0
    a.action_state = "idle"
    a.windup_stun_until_ms = bat.elapsed_ms + 200  # stun active

    bat._ai_choose_action(a, b, dt_ms=16)
    assert a.vel_x == 0.0, "AI should not have set walk velocity during stun"


def test_ai_resumes_after_stun_expires():
    """Once elapsed_ms >= windup_stun_until_ms, AI re-engages (walks toward opp)."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(1000)

    a.pos_x = 100.0
    b.pos_x = 380.0
    a.vel_x = 0.0
    a.action_state = "idle"
    a.windup_stun_until_ms = bat.elapsed_ms - 1  # already expired

    bat._ai_choose_action(a, b, dt_ms=16)
    # AI should walk right toward opp at b.pos_x=380 — vel_x positive
    assert a.vel_x > 0, f"AI should walk toward opponent after stun, got vel_x={a.vel_x}"


from pixel_battle.engine.skill import SkillType


def test_start_attack_sets_defender_windup_stun_for_cd_skill():
    """When attacker casts a CD skill, opp.windup_stun_until_ms is bumped to elapsed_ms + 200."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # in range
    a.mp = 0
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1
    b.windup_stun_until_ms = 0
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        b.windup_stun_until_ms = 0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found, "Couldn't force a CD skill choice"
    assert b.windup_stun_until_ms == bat.elapsed_ms + 200, \
        f"Expected stun = elapsed_ms+200, got {b.windup_stun_until_ms} (elapsed={bat.elapsed_ms})"


def test_start_attack_does_not_stun_on_basic():
    """Basic skill does not trigger windup_stun on defender."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280
    a.mp = 0
    # Force CD skills out of reach
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.last_attack_ms = -10000
    a.facing = 1
    a.vel_x = 0.0
    b.vel_x = 0.0
    b.windup_stun_until_ms = 0
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
    assert b.windup_stun_until_ms == 0
