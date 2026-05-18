import pytest
from pixel_battle.engine.character import Character
from pixel_battle.engine.physics import (
    ARENA_LEFT, ARENA_RIGHT, GROUND_Y, WALK_SPEED,
    JUMP_VELOCITY, GRAVITY, MELEE_RANGE,
    apply_gravity, clamp_x,
)


def test_character_resets_to_ground():
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200, facing=1)
    assert c.pos_x == 200
    assert c.pos_y == GROUND_Y
    assert c.on_ground is True
    assert c.facing == 1


def test_character_reset_facing_left():
    c = Character.load("glass_slab")
    c.reset_physics(initial_x=350, facing=-1)
    assert c.facing == -1
    assert c.vel_x == 0.0
    assert c.vel_y == 0.0
    assert c.action_state == "idle"
    assert c.attack_phase == "none"


def test_gravity_constant():
    assert GRAVITY > 0


def test_gravity_increases_fall_speed():
    vel = 0.0
    vel = apply_gravity(vel)
    assert vel == GRAVITY
    vel = apply_gravity(vel)
    assert vel > GRAVITY


def test_gravity_clamps_to_max_fall():
    from pixel_battle.engine.physics import MAX_FALL_SPEED
    vel = 100.0  # already above max
    vel = apply_gravity(vel)
    assert vel == MAX_FALL_SPEED


def test_arena_bounds_sane():
    assert ARENA_LEFT < ARENA_RIGHT
    assert ARENA_LEFT > 0
    assert ARENA_RIGHT < 480


def test_clamp_x_keeps_in_bounds():
    assert clamp_x(ARENA_LEFT - 50) == ARENA_LEFT
    assert clamp_x(ARENA_RIGHT + 50) == ARENA_RIGHT
    assert clamp_x(200) == 200


def test_melee_range_is_distance_threshold():
    # Characters at 250 distance — should NOT be in range
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    a.reset_physics(initial_x=100, facing=1)
    b.reset_physics(initial_x=350, facing=-1)
    distance = abs(a.pos_x - b.pos_x)
    assert distance > MELEE_RANGE
    # Move closer
    a.pos_x = 280
    assert abs(a.pos_x - b.pos_x) < MELEE_RANGE


def test_reset_clears_hp_and_mp():
    c = Character.load("brick_phone")
    c.take_damage(50)
    c.gain_mp(80)
    c.reset_physics(initial_x=200, facing=1)
    assert c.hp == 100
    assert c.mp == 0


def test_walk_speed_positive():
    assert WALK_SPEED > 0


def test_jump_velocity_negative():
    # Negative means upward in screen-down coordinate system
    assert JUMP_VELOCITY < 0
