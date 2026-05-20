"""Tests for env symmetry (relative actions) + kick action."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pytest

from pixel_battle.rl.env import PixelBattleEnv


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
    env._apply_action(env.left, env.right, 8)  # kick
    assert env.left.action_state == "attacking"
    assert env.left.attack_anim_hint == "kick"


def test_out_of_range_attack_gets_reward_penalty():
    env = PixelBattleEnv(seed=1)
    # Move chars far apart
    env.left.pos_x = 50
    env.right.pos_x = 430
    env.left.last_attack_ms = -10_000
    env.right.last_attack_ms = -10_000
    (_obs), rewards, _, _, _ = env.step((4, 0))  # left attacks (basic) — out of range
    # left's reward should include the OOR penalty
    # We can't isolate exactly, but we can compare against a non-attack baseline
    env2 = PixelBattleEnv(seed=1)
    env2.left.pos_x = 50
    env2.right.pos_x = 430
    env2.left.last_attack_ms = -10_000
    env2.right.last_attack_ms = -10_000
    (_obs2), rewards2, _, _, _ = env2.step((0, 0))  # both idle
    # left's reward in attack case should be lower by RANGE_PENALTY (0.05)
    assert rewards[0] < rewards2[0] - 0.03  # buffer below the 0.05 penalty


def test_in_range_attack_no_penalty():
    env = PixelBattleEnv(seed=1)
    env.left.pos_x = 200
    env.right.pos_x = 240  # well within melee range (which is ~50px)
    env.left.last_attack_ms = -10_000
    (_obs), rewards, _, _, _ = env.step((4, 0))
    env2 = PixelBattleEnv(seed=1)
    env2.left.pos_x = 200
    env2.right.pos_x = 240
    env2.left.last_attack_ms = -10_000
    (_obs2), rewards2, _, _, _ = env2.step((0, 0))
    # left attacked in range → no OOR penalty (might even gain reward if hit)
    assert rewards[0] >= rewards2[0] - 0.01
