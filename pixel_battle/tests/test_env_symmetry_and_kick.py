"""Tests for env symmetry (relative actions) + kick action."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pytest

from pixel_battle.rl.env import PixelBattleEnv, STEP_PENALTY


def test_action_space_is_9():
    env = PixelBattleEnv(seed=1)
    assert env.action_space.n == 9


def test_action_forward_moves_toward_opp_from_left_side():
    env = PixelBattleEnv(seed=1)
    # Brick (left) is at low x, glass (right) at high x → opp to my right → forward = +x
    env._apply_action(env.left, env.right, 2)  # forward
    assert env.left.vel_x > 0


def test_action_forward_moves_toward_opp_from_right_side():
    env = PixelBattleEnv(seed=1)
    # Glass (right) is at high x, opp (brick) is to my left → forward = -x
    env._apply_action(env.right, env.left, 2)  # forward
    assert env.right.vel_x < 0


def test_action_back_moves_away_from_opp_from_left_side():
    env = PixelBattleEnv(seed=1)
    env._apply_action(env.left, env.right, 1)  # back
    assert env.left.vel_x < 0


def test_action_back_moves_away_from_opp_from_right_side():
    env = PixelBattleEnv(seed=1)
    env._apply_action(env.right, env.left, 1)  # back
    assert env.right.vel_x > 0


def test_kick_action_starts_attack_with_basic_skill():
    env = PixelBattleEnv(seed=1)
    env.left.last_attack_ms = -10_000
    # Place opponent within ATTACK_GATE_RANGE so the kick isn't gated out
    env.right.pos_x = env.left.pos_x + 80
    env._apply_action(env.left, env.right, 8)  # kick
    assert env.left.action_state == "attacking"
    assert env.left.attack_anim_hint == "kick"


def test_attack_gated_out_when_out_of_range():
    """An attack issued from beyond ATTACK_GATE_RANGE is a no-op."""
    env = PixelBattleEnv(seed=1)
    env.left.last_attack_ms = -10_000
    env.left.mp = env.left.mp_max
    env.right.pos_x = env.left.pos_x + 300  # far out of range
    env._apply_action(env.left, env.right, 4)  # basic attack
    assert env.left.action_state != "attacking"  # gated out -> no-op


def test_reset_applies_reduced_start_hp():
    from pixel_battle.rl.env import START_HP
    env = PixelBattleEnv(seed=1)
    assert env.left.hp == START_HP
    assert env.right.hp == START_HP
    assert env.left.hp_max == START_HP


def test_closing_distance_gives_positive_shaping():
    """Approach shaping rewards reducing the gap between fighters."""
    env = PixelBattleEnv(seed=1)
    # Place far apart, then both step 'forward' (toward each other)
    env.left.pos_x = 100
    env.right.pos_x = 400
    env._prev_dist = abs(env.left.pos_x - env.right.pos_x)
    (_obs), rewards, _, _, _ = env.step((2, 2))  # both move toward
    # Distance shrank → both rewards include positive approach shaping.
    # No damage exchanged this early, so reward is dominated by approach - step.
    assert rewards[0] > -STEP_PENALTY
    assert rewards[1] > -STEP_PENALTY
