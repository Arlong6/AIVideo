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
from pixel_battle.engine.physics import MELEE_RANGE, SPECIAL_RANGE


TICK_MS = 16
EPISODE_TIMEOUT_MS = 60_000
INTRO_END_MS = 2500

# Combat tuning (RL-scoped — the engine keeps HP_MAX=100). Lower starting HP
# makes fights reach KO fast: brutal, dense, Shorts-length (~20-30s) matches.
START_HP = 30

# Reward shaping
DMG_DEALT_W = 1.5            # weight on damage dealt to opponent
DMG_TAKEN_W = 1.0            # weight on damage received
STEP_PENALTY = 0.02          # per-step time pressure
APPROACH_WEIGHT = 6.0        # potential-based gap-closing shaping
ENGAGE_BONUS = 0.015         # per-step reward for being at fighting distance
ENGAGE_RADIUS = 120          # px; how close counts as "engaged"
KO_WIN_BONUS = 60.0          # terminal reward for landing the KO
KO_LOSS_PENALTY = 50.0       # terminal penalty for being KO'd
# Reward design notes:
# - APPROACH_WEIGHT shaping (potential-based, telescopes) pulls the fighters
#   together from the spawn distance; ENGAGE_BONUS then keeps them in the
#   fight zone so the policy actually trades blows instead of orbiting.
# - ENGAGE_BONUS is deliberately small: max ~+56 over a 60s timeout, which
#   STEP_PENALTY (~-75 over the same span) outweighs — so stalling nets
#   negative and a KO win (+60) is strictly the better play. The earlier
#   +0.05 engage bonus was farmable (timeout > KO) and produced a passive
#   hugging policy.
# - No out-of-range attack penalty: it suppressed aggression into a passive
#   draw equilibrium. A whiffed attack already burns an attack-interval of
#   cooldown, which under STEP_PENALTY is implicit pressure enough.


class PixelBattleEnv(gym.Env):
    """Self-play env. step((left_act, right_act)) -> (obs_pair, reward_pair, ...)

    Observation per agent (17 dims, normalized to ~[-1, 1]):
       [own_x, own_y, own_vx, own_vy, own_hp, own_mp,
        opp_x, opp_y, opp_vx, opp_vy, opp_hp, opp_mp,
        dx, dy, on_ground, attack_phase_t, time_remaining]

    Action (Discrete 9):
       0=idle, 1=back (away from opp), 2=forward (toward opp), 3=jump,
       4=basic, 5=cd, 6=ultimate, 7=special, 8=kick
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42,
                 left_id: str = "brick_phone", right_id: str = "glass_slab"):
        super().__init__()
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(17,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(9)
        self._init_seed = seed
        # Which characters fight. The trained policy is character-agnostic
        # (it keys on distance + obs and picks skill *categories*), so any
        # matchup works without retraining; training itself uses the default.
        self.left_id = left_id
        self.right_id = right_id
        self.reset(seed=seed)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is None:
            seed = self._init_seed
        self._rng = BattleRNG(seed)
        self.left = Character.load(self.left_id)
        self.right = Character.load(self.right_id)
        self.battle = Battle(left=self.left, right=self.right, rng=self._rng)
        # RL-scoped HP reduction — see START_HP note above. Applied *after*
        # Battle() because Battle.__init__ -> reset_physics() resets hp to
        # the engine's HP_MAX; we override it here.
        for c in (self.left, self.right):
            c.hp = START_HP
            c.hp_max = START_HP
        # Tick through intro so both characters are in FIGHTING state
        while self.battle.state == BattleState.STARTING:
            self.battle.tick_ms(TICK_MS, skip_ai=True)
            if self.battle.elapsed_ms > INTRO_END_MS:
                break
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp
        self._prev_dist = abs(self.left.pos_x - self.right.pos_x)
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

        # Potential-based approach shaping — rewards closing the gap. It
        # telescopes (sum over an episode = APPROACH_WEIGHT*(start-end)/480),
        # so it cannot be farmed by hugging (stationary => 0) or oscillating.
        cur_dist = abs(self.left.pos_x - self.right.pos_x)
        approach = APPROACH_WEIGHT * (self._prev_dist - cur_dist) / 480.0
        self._prev_dist = cur_dist

        # Small dense bonus for staying at fighting distance (see notes above).
        engage = ENGAGE_BONUS if cur_dist < ENGAGE_RADIUS else 0.0

        reward_left = (dmg_to_right * DMG_DEALT_W - dmg_to_left * DMG_TAKEN_W
                       - STEP_PENALTY + approach + engage)
        reward_right = (dmg_to_left * DMG_DEALT_W - dmg_to_right * DMG_TAKEN_W
                        - STEP_PENALTY + approach + engage)

        terminated = self.battle.state == BattleState.KO
        truncated = (self.battle.elapsed_ms - INTRO_END_MS) >= EPISODE_TIMEOUT_MS

        if terminated:
            if self.right.is_ko() and not self.left.is_ko():
                reward_left += KO_WIN_BONUS
                reward_right -= KO_LOSS_PENALTY
            elif self.left.is_ko() and not self.right.is_ko():
                reward_left -= KO_LOSS_PENALTY
                reward_right += KO_WIN_BONUS

        return (self._obs_pair(),
                (float(reward_left), float(reward_right)),
                terminated, truncated, {})

    def _obs_for(self, me: Character, opp: Character) -> np.ndarray:
        me_hp_max = getattr(me, "hp_max", 100) or 100
        opp_hp_max = getattr(opp, "hp_max", 100) or 100
        return np.array([
            me.pos_x / 480 - 1.0, me.pos_y / 854 - 1.0,
            float(np.clip(me.vel_x / 10, -1, 1)),
            float(np.clip(me.vel_y / 20, -1, 1)),
            me.hp / me_hp_max, me.mp / 100.0,
            opp.pos_x / 480 - 1.0, opp.pos_y / 854 - 1.0,
            float(np.clip(opp.vel_x / 10, -1, 1)),
            float(np.clip(opp.vel_y / 20, -1, 1)),
            opp.hp / opp_hp_max, opp.mp / 100.0,
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
        # Direction toward opponent (+1 if opp to my right, -1 if to my left)
        fwd = 1 if opp.pos_x > me.pos_x else -1
        # Per-skill attack gate: an attack issued out of the skill's reach is
        # a no-op (no doomed whiff animation). Melee actions (basic, kick)
        # gate at MELEE_RANGE; special and cd actions at SPECIAL_RANGE.
        # (Ultimate is ungated — it always connects.)
        dist = abs(me.pos_x - opp.pos_x)
        if action == 1:                          # back (away from opp)
            me.vel_x = -3.0 * fwd
            me.facing = fwd                       # still face opp while backpedaling
        elif action == 2:                        # forward (toward opp)
            me.vel_x = 3.0 * fwd
            me.facing = fwd
        elif action == 3 and me.on_ground:       # jump
            me.vel_y = -8.0
            me.on_ground = False
        elif action == 4 and dist <= MELEE_RANGE:      # basic attack
            self.battle._start_attack_with_kind(me, opp, "basic")
        elif action == 5 and dist <= SPECIAL_RANGE:    # cd skill
            self.battle._start_attack_with_kind(me, opp, "cooldown")
        elif action == 6 and me.ultimate_ready():
            # cinematic_pause=False — no multi-second freeze in the RL render
            self.battle._trigger_ultimate(me, opp, cinematic_pause=False)
        elif action == 7 and dist <= SPECIAL_RANGE:    # special skill
            self.battle._start_attack_with_kind(me, opp, "special")
        elif action == 8 and dist <= MELEE_RANGE:      # kick
            self.battle._start_attack_with_kind(me, opp, "kick")


class SinglePerspectiveEnv(gym.Env):
    """Wrap PixelBattleEnv so step(left_action) controls only 'left'.

    Right is controlled by `opponent_policy` (a callable taking obs -> int).
    Use a fresh random policy for the first training rollouts, then swap to
    the current PPO model itself for symmetric self-play.
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42, opponent_policy=None,
                 left_id: str = "brick_phone", right_id: str = "glass_slab"):
        super().__init__()
        self._inner = PixelBattleEnv(seed=seed, left_id=left_id, right_id=right_id)
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
