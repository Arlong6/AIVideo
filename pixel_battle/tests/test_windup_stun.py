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
