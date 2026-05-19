# Pixel Battle — RL Stick-Fight (Reset of Visual Layer)

**Date**: 2026-05-20
**Status**: Approved
**Trigger**: After P1-P5 engine iterations + audio mixer overhaul + FLUX sprite swap + 30s scripted highlight reel, user concludes the visual style is wrong and the goal of "emergent visual interest" is best served by **letting RL agents learn to fight**, with **simple stick-figure visuals** so attention goes to behavior, not character art.

## Goal

Replace the sprite-driven pixel-art combatants with **procedurally-drawn stick figures** controlled by **PPO self-play** agents trained on the existing `engine/battle.py` physics. The output is a video showing two trained agents fighting — visual interest comes from emergent strategy, not character design.

Three deliverables, each independently watchable:

1. **Stick-figure renderer** — replaces sprite blits with line/circle drawing driven by physics state. Existing heuristic AI still drives behavior at this stage.
2. **Gym environment + random agent** — wrap `Battle` in a Gymnasium env. Verify random-action policy can run, episodes terminate cleanly.
3. **PPO self-play training + final video** — train one shared policy via stable-baselines3, render a fight using the trained policy.

## Four blocks

### A. Stick-figure renderer (`pixel_battle/rl/stick_renderer.py`)

**Purpose**: procedural draw using `pygame.draw.line` / `pygame.draw.circle`. No sprites loaded. Pose derived from `Character.action_state`, `attack_phase`, `vel_x`, `on_ground`.

Each character renders as 5 primitives:
- Head: filled circle, radius 12px, at `pos_x, pos_y - 80`
- Torso: vertical line, length 40px
- Arms: 2 line segments from shoulder; angle depends on `attack_phase` (windup → backward; strike → forward)
- Legs: 2 line segments from hip; angle depends on `vel_x` (walking → splayed) and `on_ground` (jumping → tucked)

Two characters distinguished by `color` field (left = red `(220, 60, 60)`, right = blue `(60, 130, 220)`).

Stub for Phase 1 — replaces `Renderer.draw_character` (or equivalent) but reuses `Renderer.background`, `Renderer.hud`, `Renderer.particles`, `Renderer.banners`, `Renderer.impact_fx`.

```python
def draw_stick_figure(surf, character, color):
    """Draw a stick figure based on character physics state."""
    cx, cy = int(character.pos_x), int(character.pos_y)

    # Head
    pygame.draw.circle(surf, color, (cx, cy - 80), 12, width=3)
    # Eyes (just two dots for personality)
    pygame.draw.circle(surf, color, (cx - 4, cy - 82), 1)
    pygame.draw.circle(surf, color, (cx + 4, cy - 82), 1)

    # Torso
    pygame.draw.line(surf, color, (cx, cy - 68), (cx, cy - 28), width=3)

    # Arms — angles depend on attack_phase + facing
    arm_angles = compute_arm_angles(character)  # returns (l_dx, l_dy, r_dx, r_dy)
    shoulder_y = cy - 60
    pygame.draw.line(surf, color, (cx, shoulder_y),
                     (cx + arm_angles[0], shoulder_y + arm_angles[1]), width=3)
    pygame.draw.line(surf, color, (cx, shoulder_y),
                     (cx + arm_angles[2], shoulder_y + arm_angles[3]), width=3)

    # Legs — splayed when walking, tucked when in air
    leg_offset = 12 if abs(character.vel_x) > 0.5 else 8
    leg_top_y = cy - 28
    if character.on_ground:
        pygame.draw.line(surf, color, (cx, leg_top_y),
                         (cx - leg_offset, cy), width=3)
        pygame.draw.line(surf, color, (cx, leg_top_y),
                         (cx + leg_offset, cy), width=3)
    else:
        pygame.draw.line(surf, color, (cx, leg_top_y),
                         (cx - 6, cy - 12), width=3)
        pygame.draw.line(surf, color, (cx, leg_top_y),
                         (cx + 6, cy - 12), width=3)
```

### B. Gym environment (`pixel_battle/rl/env.py`)

**Purpose**: Wrap `Battle` so PPO can step through fights. Episodes self-play (both agents are the policy under training).

```python
import numpy as np
import gymnasium as gym
from gymnasium import spaces

from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG

TICK_MS = 16
EPISODE_TIMEOUT_MS = 60_000

class PixelBattleEnv(gym.Env):
    """Self-play Gym env. Step accepts a (left_action, right_action) tuple.

    Observation per agent: 17-dim float32 vector (see Spec §A).
    Action: discrete 7 — {idle, left, right, jump, basic, cd_skill, ultimate}.

    For PPO multi-agent self-play we expose this as a paired env:
    `step(actions)` takes a 2-tuple, returns (obs_pair, reward_pair, done, truncated, info).
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42):
        super().__init__()
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(17,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(7)
        self._seed = seed
        self._rng = BattleRNG(seed)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = BattleRNG(seed)
        self.left = Character.load("brick_phone")
        self.right = Character.load("glass_slab")
        self.battle = Battle(left=self.left, right=self.right, rng=self._rng)
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp
        return self._obs_pair(), {}

    def step(self, actions):
        left_action, right_action = actions
        # Disable engine's heuristic AI; apply policy actions instead
        self._apply_action(self.left, self.right, left_action)
        self._apply_action(self.right, self.left, right_action)
        self.battle.tick_ms(TICK_MS, skip_ai=True)

        # Reward shaping
        dmg_to_right = max(0, self._prev_right_hp - self.right.hp)
        dmg_to_left = max(0, self._prev_left_hp - self.left.hp)
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp

        reward_left = dmg_to_right * 1.0 - dmg_to_left * 1.0 - 0.01
        reward_right = dmg_to_left * 1.0 - dmg_to_right * 1.0 - 0.01

        # Engagement reward — small bonus for getting closer
        dist = abs(self.left.pos_x - self.right.pos_x)
        if dist < 200:
            reward_left += 0.05
            reward_right += 0.05

        terminated = self.battle.state == BattleState.FINISHED
        truncated = self.battle.elapsed_ms >= EPISODE_TIMEOUT_MS

        if terminated:
            if self.right.is_ko():
                reward_left += 50.0
                reward_right -= 50.0
            elif self.left.is_ko():
                reward_left -= 50.0
                reward_right += 50.0

        return (self._obs_pair(),
                (reward_left, reward_right),
                terminated, truncated, {})

    def _obs_for(self, me, opp) -> np.ndarray:
        # Normalized to [-1, 1]; see Spec §A for exact normalization
        return np.array([
            me.pos_x / 480 - 1, me.pos_y / 854 - 1,
            np.clip(me.vel_x / 10, -1, 1),
            np.clip(me.vel_y / 20, -1, 1),
            me.hp / 100, me.mp / 100,
            opp.pos_x / 480 - 1, opp.pos_y / 854 - 1,
            np.clip(opp.vel_x / 10, -1, 1),
            np.clip(opp.vel_y / 20, -1, 1),
            opp.hp / 100, opp.mp / 100,
            np.clip((opp.pos_x - me.pos_x) / 480, -1, 1),
            np.clip((opp.pos_y - me.pos_y) / 854, -1, 1),
            float(me.on_ground),
            np.clip(me.attack_phase_t / 200, 0, 1),
            np.clip((EPISODE_TIMEOUT_MS - self.battle.elapsed_ms) / EPISODE_TIMEOUT_MS, 0, 1),
        ], dtype=np.float32)

    def _obs_pair(self):
        return (self._obs_for(self.left, self.right),
                self._obs_for(self.right, self.left))

    def _apply_action(self, me, opp, action):
        """Map discrete action to engine inputs."""
        if me.action_state in ("attacking", "hit_stagger", "ko"):
            return  # locked
        if action == 1:    # left
            me.vel_x = -3.0
        elif action == 2:  # right
            me.vel_x = 3.0
        elif action == 3 and me.on_ground:  # jump
            me.vel_y = -8.0
        elif action == 4:  # basic attack
            self.battle._start_attack_with_kind(me, opp, "basic")
        elif action == 5:  # cd skill
            self.battle._start_attack_with_kind(me, opp, "cooldown")
        elif action == 6 and me.ultimate_ready():
            self.battle._trigger_ultimate(me, opp)
```

Note `Battle.tick_ms(skip_ai=True)` and `Battle._start_attack_with_kind(...)` are NEW shims added to `engine/battle.py` so the existing heuristic AI is bypassed when called from the RL env. Internal logic (collision, MP, cooldown enforcement, physics) is unchanged.

`_start_attack_with_kind(char, opp, kind)` semantics:
- `kind="basic"` → picks the first BASIC skill (always available)
- `kind="cooldown"` → picks first off-cooldown COOLDOWN skill; if none available, no-op (action wasted)
- The method calls existing `_start_attack` internals after overriding skill selection (avoids the 70%/40% random gates in the heuristic `_choose_attack_skill`)

### C. PPO self-play training (`pixel_battle/rl/train.py`)

Uses `stable-baselines3 >= 2.0` with the `MultiAgentEnv → SubprocVecEnv` pattern, OR the simpler "shared policy + alternating opponent freeze" approach. For first cut: **shared policy, both sides query same network**, simpler.

```python
import argparse
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback
from stable_baselines3.common.vec_env import DummyVecEnv

from pixel_battle.rl.env import PixelBattleEnv

# We adapt the paired env to "single-agent step()" by alternating perspective
# at each step — simpler than full multi-agent, and matches PPO's API.
class SinglePerspectiveEnv(gym.Env):
    """Wrap PixelBattleEnv so step takes ONE action; controls 'left' player.
    Opponent ('right') is controlled by a recently-frozen snapshot of the policy.
    """
    # ... (implementation in plan; the gist: env.step(left_action) where
    #     right_action = opponent_policy.predict(obs_right)[0])

def main(total_timesteps: int = 1_000_000,
          ckpt_dir: str = "data/rl_checkpoints"):
    ckpt_dir = Path(ckpt_dir).resolve()
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    env = DummyVecEnv([lambda: SinglePerspectiveEnv()])
    model = PPO("MlpPolicy", env, verbose=1, n_steps=2048,
                 batch_size=256, gae_lambda=0.95, gamma=0.99,
                 learning_rate=3e-4, clip_range=0.2, ent_coef=0.01)
    callback = CheckpointCallback(save_freq=100_000,
                                   save_path=str(ckpt_dir),
                                   name_prefix="ppo")
    model.learn(total_timesteps=total_timesteps, callback=callback)
    model.save(ckpt_dir / "ppo_final.zip")
```

Training expected to converge to "approach + attack" within 200K-500K steps. Full convergence to good play 1M-3M steps.

### D. Play / render (`pixel_battle/rl/play.py`)

Loads a trained checkpoint, runs one episode using the policy for BOTH players (self-play visualization), pipes frames through `FrameRecorder` and `AudioMixer`.

```python
from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.rl.stick_renderer import draw_stick_figure
from pixel_battle.video.recorder import FrameRecorder
from pixel_battle.video.audio_mixer import AudioMixer
# ...

def main(checkpoint: str, output_path: str, max_seconds: float = 60.0):
    model = PPO.load(checkpoint)
    env = PixelBattleEnv()
    obs_left, obs_right = env.reset()[0]
    # ... step the env, draw stick figures each frame, emit audio events
    #     for HIT/CRIT/ULTIMATE_START/KO, write_frame, mux at end
```

## Architecture

```
pixel_battle/
├── engine/battle.py       # MODIFIED: add tick_ms(skip_ai=True) + _start_attack_with_kind()
├── engine/character.py    # unchanged
├── engine/physics.py      # unchanged
├── video/audio_mixer.py   # unchanged
├── video/compose.py       # unchanged (BGM + SFX still piped through AudioMixer)
├── video/recorder.py      # unchanged
└── rl/                    # NEW
    ├── __init__.py
    ├── stick_renderer.py
    ├── env.py
    ├── train.py
    └── play.py
data/
└── rl_checkpoints/        # NEW — gitignored
```

**Existing sprite assets stay on disk** (in `assets/sprites/`) but are unused by the RL pipeline. `assets/sprite_proto/` and `gen_keyframes.py` likewise stay — useful if user reverts.

## Error handling

- **Training divergence**: stable-baselines3 `CheckpointCallback` snapshots every 100K steps; `play.py` can load any checkpoint
- **Reward hacking**: small step penalty `-0.01` deters infinite stalls; engagement bonus `+0.05` deters camping; eval after every 100K steps measures KO rate
- **Action while locked**: `_apply_action` early-returns if `me.action_state in ("attacking", "hit_stagger", "ko")` — the env still steps the engine, the action is just dropped
- **MP/cooldown gate**: ult action ignored if `not me.ultimate_ready()`; cd-skill action falls back to basic if all CD skills on cooldown (delegated to engine logic)
- **Battle.tick_ms backward compat**: `skip_ai` defaults to `False` so existing tests + `ep01_brick_vs_glass.py` are unaffected

## Testing

### Unit tests (new)

- `tests/test_rl_env.py`:
  - `PixelBattleEnv.reset()` returns (obs_pair, info) with correct shapes (17-dim each)
  - `step((0, 0))` (both idle) advances `battle.elapsed_ms` by `TICK_MS`
  - `step` returns `done=True` when one character is KO'd
  - Reward sign matches HP delta direction (damage = positive for attacker, negative for victim)
  - `_apply_action(jump)` zeroes `vel_y` only if `on_ground`; ignored mid-air
- `tests/test_stick_renderer.py`:
  - `draw_stick_figure` writes pixels somewhere within a 100-pixel radius of `pos_x, pos_y`
  - Renders distinct color for left vs right player
  - Doesn't raise on any combination of `attack_phase` and `on_ground`
- `tests/test_battle_skip_ai.py`:
  - `Battle.tick_ms(dt, skip_ai=True)` skips `_ai_choose_action` calls but still applies physics + collision

### Smoke tests

- `python -m pixel_battle.rl.env` runs 100 random-action steps without crash
- `python -m pixel_battle.rl.train --total_timesteps 10000` completes a tiny training run
- `python -m pixel_battle.rl.play --checkpoint <path>` produces a wav + mp4

### Visual regression

- After Phase 1, render a fight with heuristic AI but stick-figure visuals — verify readable
- After Phase 4, render a fight with PPO policy — verify agents engage rather than wandering

## Implementation phases (the user sees a video after each)

1. **Phase 1 — Stick-figure renderer**
   - Add `pixel_battle/rl/stick_renderer.py`
   - Hook into `engine/renderer.py` via a flag (or new minimal renderer)
   - Run existing `ep01_brick_vs_glass.py` with sticks instead of sprites
   - **Deliverable**: 60s video with old AI behavior but stick visuals — user judges readability

2. **Phase 2 — Gym env + random agent**
   - Add `pixel_battle/rl/env.py`
   - Add `Battle.tick_ms(skip_ai=True)` + `_start_attack_with_kind` shims
   - Smoke test: 100 random-action steps; render a 30s random-agent fight
   - **Deliverable**: a "random RL" video — agents flail. User confirms baseline.

3. **Phase 3 — PPO training**
   - Add `pixel_battle/rl/train.py`
   - Train for 500K steps (initial budget); if eval reward is still rising, extend to 1M
   - Save checkpoints every 100K
   - **Deliverable**: trained `ppo_final.zip` + training reward curve

4. **Phase 4 — Render trained fight**
   - Add `pixel_battle/rl/play.py`
   - Render 30-60s self-play episode with trained policy + existing audio pipeline
   - **Deliverable**: final video

## Out of scope

- Multi-agent / asymmetric training (left and right with different policies/skills)
- Curriculum learning (e.g., start vs scripted weak opponent)
- Hyperparameter sweep beyond stable-baselines3 defaults
- GPU training (CPU is enough for this env at 1M steps)
- Imitation learning from heuristic AI
- League play / Elo ranking across checkpoints
- Reverting the sprite pipeline (`gen_keyframes.py`, `assets/sprites/`)
- Replacing AudioMixer or BGM (synthwave stays)

## Tuning knobs

- **Reward shaping**: damage 1:1, KO ±50, step -0.01, engagement +0.05 if dist < 200
- **Action space**: 7 discrete (idle/L/R/jump/basic/cd/ult)
- **PPO hyperparams**: lr=3e-4, n_steps=2048, batch_size=256, gae=0.95, gamma=0.99, ent_coef=0.01, clip=0.2
- **Episode length**: 60s max (3750 steps at TICK_MS=16)
- **Training budget**: 1M steps (Phase 3 default); checkpoint every 100K
- **Stick-figure dimensions**: head r=12, torso 40px, arm/leg 12-20px depending on pose
