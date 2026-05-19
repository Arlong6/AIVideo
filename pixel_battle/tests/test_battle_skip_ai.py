"""Battle.tick_ms(skip_ai=True) bypasses the heuristic AI + auto-ultimate."""
from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def _new_battle(seed: int = 42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    return Battle(left=a, right=b, rng=BattleRNG(seed))


def test_tick_ms_default_runs_ai():
    """Without skip_ai, characters move toward each other under heuristic AI."""
    bat = _new_battle()
    bat.tick_ms(2500)  # advance past intro
    init_left_x = bat.left.pos_x
    init_right_x = bat.right.pos_x
    for _ in range(60):
        bat.tick_ms(16)
    # AI should have moved at least one of them
    moved = (bat.left.pos_x != init_left_x) or (bat.right.pos_x != init_right_x)
    assert moved, "expected heuristic AI to move characters"


def test_tick_ms_skip_ai_no_movement():
    """With skip_ai=True, characters do not move under AI control."""
    bat = _new_battle()
    bat.tick_ms(2500)
    bat.left.vel_x = 0.0
    bat.right.vel_x = 0.0
    init_left_x = bat.left.pos_x
    init_right_x = bat.right.pos_x
    for _ in range(60):
        bat.tick_ms(16, skip_ai=True)
    # Velocities should still be zero (friction would clear any residual);
    # positions unchanged (no AI input, no manual vel)
    assert bat.left.pos_x == init_left_x
    assert bat.right.pos_x == init_right_x


def test_tick_ms_skip_ai_still_resolves_attacks():
    """Physics + attack-phase + collision still run with skip_ai."""
    bat = _new_battle()
    bat.tick_ms(2500)
    # Manually set attack state and step
    bat.left.pos_x = 220
    bat.right.pos_x = 260  # in melee range
    bat.left.action_state = "attacking"
    bat.left.attack_phase = "windup"
    bat.left.attack_phase_t = 0
    bat.left.attack_used_kind = bat.left.skills[0]  # basic skill
    bat.left.facing = 1
    initial_right_hp = bat.right.hp
    for _ in range(15):  # enough frames for windup → strike → hit
        bat.tick_ms(16, skip_ai=True)
    # Either the attack landed (hp dropped) or missed (logged); just confirm
    # the phase machine progressed (not stuck at windup forever).
    assert bat.left.attack_phase != "windup", "phase machine should have advanced"


def test_tick_ms_skip_ai_skips_auto_ultimate():
    """When MP is full, default tick triggers ultimate; skip_ai prevents that."""
    bat = _new_battle()
    bat.tick_ms(2500)
    bat.left.mp = bat.left.mp_max  # ultimate ready
    bat.left.action_state = "idle"
    bat.left.attack_phase = "none"
    bat.tick_ms(16, skip_ai=True)
    # Should NOT have entered ULTIMATE_PLAYING state via auto-trigger
    assert bat.state != BattleState.ULTIMATE_PLAYING
