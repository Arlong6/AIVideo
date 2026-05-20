"""PixelBattleEnv exposes a paired Gymnasium env for self-play."""
import numpy as np
import pytest

from pixel_battle.rl.env import PixelBattleEnv


def test_env_reset_returns_paired_obs_with_correct_shape():
    env = PixelBattleEnv(seed=42)
    (obs_left, obs_right), info = env.reset()
    assert obs_left.shape == (17,)
    assert obs_right.shape == (17,)
    assert obs_left.dtype == np.float32
    assert obs_right.dtype == np.float32
    assert isinstance(info, dict)


def test_env_step_advances_battle_time():
    env = PixelBattleEnv(seed=42)
    env.reset()
    # Step past intro
    for _ in range(200):
        env.step((0, 0))
    assert env.battle.elapsed_ms > 2000


def test_env_step_returns_paired_reward_tuple():
    env = PixelBattleEnv(seed=42)
    env.reset()
    obs, rewards, terminated, truncated, info = env.step((0, 0))
    assert len(rewards) == 2
    assert isinstance(rewards[0], float)
    assert isinstance(rewards[1], float)


def test_env_movement_actions_apply_velocity():
    env = PixelBattleEnv(seed=42)
    env.reset()
    # Step past intro so we're in FIGHTING
    for _ in range(200):
        env.step((0, 0))
    # Action 2 = forward (toward opp), 1 = back (away from opp).
    # Both characters get action 2 → both should move toward each other.
    env.step((2, 2))
    # Left's opp (right) is to its right → forward = +x
    assert env.left.vel_x > 0, f"left should move toward opp, vel_x={env.left.vel_x}"
    # Right's opp (left) is to its left → forward = -x
    assert env.right.vel_x < 0, f"right should move toward opp, vel_x={env.right.vel_x}"


def test_env_basic_attack_action_triggers_attacking():
    env = PixelBattleEnv(seed=42)
    env.reset()
    for _ in range(200):
        env.step((0, 0))
    # Place in melee range first
    env.left.pos_x = 200
    env.right.pos_x = 260
    env.left.last_attack_ms = -10000
    env.step((4, 0))  # basic attack
    assert env.left.action_state == "attacking"


def test_env_terminates_on_ko():
    env = PixelBattleEnv(seed=42)
    env.reset()
    for _ in range(200):
        env.step((0, 0))
    # KO the right player manually
    env.right.hp = 0
    obs, rewards, terminated, truncated, info = env.step((0, 0))
    assert terminated is True
    # Left dealt the KO → bonus reward
    assert rewards[0] > 10


def test_env_action_space_is_discrete_nine():
    env = PixelBattleEnv(seed=42)
    assert env.action_space.n == 9


def test_env_observation_space_is_17_dim_box():
    env = PixelBattleEnv(seed=42)
    assert env.observation_space.shape == (17,)


from pixel_battle.rl.env import SinglePerspectiveEnv


def test_single_perspective_env_steps_with_random_opponent():
    import random
    env = SinglePerspectiveEnv(seed=42,
                                opponent_policy=lambda obs: random.randint(0, 8))
    obs, info = env.reset()
    assert obs.shape == (17,)
    obs, r, term, trunc, info = env.step(0)
    assert isinstance(r, float)
    assert obs.shape == (17,)
