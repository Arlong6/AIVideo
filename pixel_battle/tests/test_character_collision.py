"""P4: Characters cannot overlap — physical collision after physics tick."""
from pixel_battle.engine.battle import Battle, MIN_CHAR_DISTANCE
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import ARENA_LEFT, ARENA_RIGHT


def _battle():
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    bat.tick_ms(2500)  # past intro
    return bat, a, b


def test_overlapping_chars_pushed_apart():
    """When two chars are closer than MIN_CHAR_DISTANCE, collision resolver pushes them apart."""
    bat, a, b = _battle()
    a.pos_x = 200
    b.pos_x = 220  # only 20px apart
    bat._resolve_character_collision()
    new_distance = abs(a.pos_x - b.pos_x)
    assert new_distance >= MIN_CHAR_DISTANCE


def test_chars_at_min_distance_unchanged():
    """When chars are at exactly MIN_CHAR_DISTANCE, no push."""
    bat, a, b = _battle()
    a.pos_x = 200
    b.pos_x = 200 + MIN_CHAR_DISTANCE
    before_a, before_b = a.pos_x, b.pos_x
    bat._resolve_character_collision()
    assert a.pos_x == before_a
    assert b.pos_x == before_b


def test_chars_far_apart_unchanged():
    """When chars are well separated, collision does nothing."""
    bat, a, b = _battle()
    a.pos_x = 100
    b.pos_x = 400
    before_a, before_b = a.pos_x, b.pos_x
    bat._resolve_character_collision()
    assert a.pos_x == before_a
    assert b.pos_x == before_b


def test_pushed_positions_stay_in_arena():
    """Even if char is at arena edge and other is on top, collision doesn't push outside."""
    bat, a, b = _battle()
    a.pos_x = ARENA_LEFT
    b.pos_x = ARENA_LEFT + 10  # very overlapping, both near left wall
    bat._resolve_character_collision()
    assert a.pos_x >= ARENA_LEFT
    assert b.pos_x <= ARENA_RIGHT


def test_tick_ms_runs_collision_after_physics():
    """tick_ms invokes _resolve_character_collision so overlap is corrected each frame."""
    bat, a, b = _battle()
    # Force overlap and let tick_ms run
    a.pos_x = 250
    b.pos_x = 260
    bat.tick_ms(16)
    assert abs(a.pos_x - b.pos_x) >= MIN_CHAR_DISTANCE
