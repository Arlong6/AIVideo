"""P5: Windup stun gates defender AI while attacker casts."""
from pixel_battle.engine.character import Character


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
