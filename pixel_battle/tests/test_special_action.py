"""Tests for Discrete(9) action space + SPECIAL attack initiator."""
from pixel_battle.rl.env import PixelBattleEnv


def test_action_space_is_9():
    env = PixelBattleEnv(seed=1)
    assert env.action_space.n == 9


def test_special_action_starts_attack_when_affordable():
    env = PixelBattleEnv(seed=1)
    # Give enough MP for any SPECIAL skill
    env.left.mp = env.left.mp_max
    # Make sure attack-interval gate is open
    env.left.last_attack_ms = -10_000
    # Place opponent within ATTACK_GATE_RANGE so the attack isn't gated out
    env.right.pos_x = env.left.pos_x + 80
    env._apply_action(env.left, env.right, 7)
    assert env.left.action_state == "attacking"
    assert env.left.attack_used_kind is not None
    assert env.left.attack_used_kind.skill_type.value == "special"


def test_special_action_noop_when_no_mp():
    env = PixelBattleEnv(seed=1)
    env.left.mp = 0
    env.left.last_attack_ms = -10_000
    pre_state = env.left.action_state
    env._apply_action(env.left, env.right, 7)
    assert env.left.action_state == pre_state
