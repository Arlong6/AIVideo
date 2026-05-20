"""Gymnasium env wrapping pixel_battle.engine.battle.Battle for PPO self-play.

Paired API: reset/step return (obs_left, obs_right) and reward tuples. We adapt
this to single-agent PPO via a wrapper in train.py.
"""
from __future__ import annotations
from typing import Tuple

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


TICK_MS = 16
EPISODE_TIMEOUT_MS = 60_000
INTRO_END_MS = 2500


class PixelBattleEnv(gym.Env):
    """Self-play env. step((left_act, right_act)) -> (obs_pair, reward_pair, ...)

    Observation per agent (17 dims, normalized to ~[-1, 1]):
       [own_x, own_y, own_vx, own_vy, own_hp, own_mp,
        opp_x, opp_y, opp_vx, opp_vy, opp_hp, opp_mp,
        dx, dy, on_ground, attack_phase_t, time_remaining]

    Action (Discrete 8):
       0=idle, 1=left, 2=right, 3=jump, 4=basic, 5=cd, 6=ultimate, 7=special
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42):
        super().__init__()
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(17,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(8)
        self._init_seed = seed
        self.reset(seed=seed)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is None:
            seed = self._init_seed
        self._rng = BattleRNG(seed)
        self.left = Character.load("brick_phone")
        self.right = Character.load("glass_slab")
        self.battle = Battle(left=self.left, right=self.right, rng=self._rng)
        # Tick through intro so both characters are in FIGHTING state
        while self.battle.state == BattleState.STARTING:
            self.battle.tick_ms(TICK_MS, skip_ai=True)
            if self.battle.elapsed_ms > INTRO_END_MS:
                break
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp
        return self._obs_pair(), {}

    def step(self, actions: Tuple[int, int]):
        left_action, right_action = actions
        self._apply_action(self.left, self.right, int(left_action))
        self._apply_action(self.right, self.left, int(right_action))
        self.battle.tick_ms(TICK_MS, skip_ai=True)

        dmg_to_right = max(0, self._prev_right_hp - self.right.hp)
        dmg_to_left = max(0, self._prev_left_hp - self.left.hp)
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp

        # Per-frame engagement reward (small)
        dist = abs(self.left.pos_x - self.right.pos_x)
        engage = 0.05 if dist < 200 else 0.0

        reward_left = dmg_to_right * 1.0 - dmg_to_left * 1.0 - 0.01 + engage
        reward_right = dmg_to_left * 1.0 - dmg_to_right * 1.0 - 0.01 + engage

        terminated = self.battle.state == BattleState.KO
        truncated = (self.battle.elapsed_ms - INTRO_END_MS) >= EPISODE_TIMEOUT_MS

        if terminated:
            if self.right.is_ko() and not self.left.is_ko():
                reward_left += 50.0
                reward_right -= 50.0
            elif self.left.is_ko() and not self.right.is_ko():
                reward_left -= 50.0
                reward_right += 50.0

        return (self._obs_pair(),
                (float(reward_left), float(reward_right)),
                terminated, truncated, {})

    def _obs_for(self, me: Character, opp: Character) -> np.ndarray:
        return np.array([
            me.pos_x / 480 - 1.0, me.pos_y / 854 - 1.0,
            float(np.clip(me.vel_x / 10, -1, 1)),
            float(np.clip(me.vel_y / 20, -1, 1)),
            me.hp / 100.0, me.mp / 100.0,
            opp.pos_x / 480 - 1.0, opp.pos_y / 854 - 1.0,
            float(np.clip(opp.vel_x / 10, -1, 1)),
            float(np.clip(opp.vel_y / 20, -1, 1)),
            opp.hp / 100.0, opp.mp / 100.0,
            float(np.clip((opp.pos_x - me.pos_x) / 480, -1, 1)),
            float(np.clip((opp.pos_y - me.pos_y) / 854, -1, 1)),
            float(me.on_ground),
            float(np.clip(me.attack_phase_t / 200, 0, 1)),
            float(np.clip(
                (EPISODE_TIMEOUT_MS - (self.battle.elapsed_ms - INTRO_END_MS))
                / EPISODE_TIMEOUT_MS,
                0, 1,
            )),
        ], dtype=np.float32)

    def _obs_pair(self):
        return (self._obs_for(self.left, self.right),
                self._obs_for(self.right, self.left))

    def _apply_action(self, me: Character, opp: Character, action: int):
        if me.action_state in ("attacking", "hit_stagger", "ko"):
            return
        if action == 1:                          # left
            me.vel_x = -3.0
            me.facing = -1 if opp.pos_x > me.pos_x else me.facing
        elif action == 2:                        # right
            me.vel_x = 3.0
            me.facing = 1 if opp.pos_x > me.pos_x else me.facing
        elif action == 3 and me.on_ground:       # jump
            me.vel_y = -8.0
            me.on_ground = False
        elif action == 4:                        # basic attack
            self.battle._start_attack_with_kind(me, opp, "basic")
        elif action == 5:                        # cd skill
            self.battle._start_attack_with_kind(me, opp, "cooldown")
        elif action == 6 and me.ultimate_ready():
            self.battle._trigger_ultimate(me, opp)
        elif action == 7:                        # special skill
            self.battle._start_attack_with_kind(me, opp, "special")


class SinglePerspectiveEnv(gym.Env):
    """Wrap PixelBattleEnv so step(left_action) controls only 'left'.

    Right is controlled by `opponent_policy` (a callable taking obs -> int).
    Use a fresh random policy for the first training rollouts, then swap to
    the current PPO model itself for symmetric self-play.
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42, opponent_policy=None):
        super().__init__()
        self._inner = PixelBattleEnv(seed=seed)
        self.observation_space = self._inner.observation_space
        self.action_space = self._inner.action_space
        self._opponent_policy = opponent_policy or (lambda obs: 0)

    def set_opponent_policy(self, policy):
        """policy(obs: np.ndarray) -> int (discrete action)."""
        self._opponent_policy = policy

    def reset(self, seed=None, options=None):
        (obs_left, obs_right), info = self._inner.reset(seed=seed)
        self._last_right_obs = obs_right
        return obs_left, info

    def step(self, left_action):
        right_action = int(self._opponent_policy(self._last_right_obs))
        (obs_left, obs_right), rewards, terminated, truncated, info = \
            self._inner.step((int(left_action), right_action))
        self._last_right_obs = obs_right
        return obs_left, float(rewards[0]), terminated, truncated, info
