"""P2 fix: AI retreat must not lock both characters against walls."""
from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import ARENA_LEFT, ARENA_RIGHT, MELEE_RANGE


def _battle_post_intro(seed=1):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)  # past intro
    return bat, a, b


def test_retreat_timer_expires_after_800ms():
    """Once retreat_until_ms is set, after 800ms it must be cleared so AI can re-evaluate."""
    bat, a, b = _battle_post_intro(seed=1)
    # Force defensive retreat by low HP + high opp MP
    a.hp = 10
    b.mp = b.mp_max  # 100
    # Close range so retreat triggers
    a.pos_x = 240
    b.pos_x = 280
    bat._ai_choose_action(a, b, 16)
    assert a.retreat_until_ms > 0
    set_at = a.retreat_until_ms
    # Advance battle clock past the timer
    bat.elapsed_ms = set_at + 1
    a.action_state = "idle"  # let AI re-decide
    bat._ai_choose_action(a, b, 16)
    # After timer expiry, retreat_until_ms must be cleared
    assert a.retreat_until_ms == 0


def test_wall_stuck_char_skips_retreat():
    """Char already at wall must skip retreat and attack instead."""
    bat, a, b = _battle_post_intro(seed=1)
    a.hp = 10
    b.mp = b.mp_max
    # Pin a to the left wall, b near it
    a.pos_x = ARENA_LEFT + 5  # within 30px of wall
    b.pos_x = ARENA_LEFT + 60  # in melee range
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    # Because a is wall-stuck, must NOT be in retreat-walking; should attack or idle
    assert a.action_state != "walking" or a.vel_x >= 0  # vel_x >= 0 means not retreating left


def test_lower_hp_threshold_to_15():
    """Defensive retreat triggers only when HP < 15 (not 30 as before)."""
    bat, a, b = _battle_post_intro(seed=1)
    a.hp = 20  # between old (30) and new (15) thresholds
    b.mp = b.mp_max
    a.pos_x = 240
    b.pos_x = 280  # in range
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    # At HP=20, should NOT defensive-retreat
    assert a.retreat_until_ms == 0
    # And at HP=10 it should
    a.hp = 10
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    assert a.retreat_until_ms > 0


def test_reset_physics_clears_retreat_timer():
    a = Character.load("brick_phone")
    a.reset_physics(initial_x=100, facing=1)
    a.retreat_until_ms = 5000
    a.reset_physics(initial_x=100, facing=1)
    assert a.retreat_until_ms == 0
