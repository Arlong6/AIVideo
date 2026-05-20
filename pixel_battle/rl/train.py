"""PPO training for PixelBattleEnv against a mixed-style scripted opponent.

Defaults to 1M total timesteps with a checkpoint every 100K.

Curriculum design (learned the hard way over several retrains):
  - Training vs a *random* opponent collapses to a passive policy: random
    rarely KOs you, so stalling to the 60s timeout is safe.
  - Training vs an *always-aggressive* opponent teaches counter-punching
    only — the opponent always closes the gap, so the agent never learns
    to initiate. Two such policies just wait each other out.
  - True *self-play* (opponent = live model) collapses back to a passive
    draw equilibrium: both copies turn passive together.

The fix: a scripted opponent that randomizes its style per episode
(`rush` / `turtle` / `mixed`). To beat a turtle the agent must initiate
the approach; to beat a rusher it must defend and counter. A policy that
beats all three styles is a complete fighter, and two copies of it
produce real, decisive fights in the renderer. No self-play phase.

Usage:
    python -m pixel_battle.rl.train --total_timesteps 1000000
"""
from __future__ import annotations
import argparse
import random
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback

from pixel_battle.rl.env import SinglePerspectiveEnv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT_DIR = ROOT / "data" / "rl_checkpoints"

# Attack action ids (env.PixelBattleEnv action space): basic/cd/special/kick
_ATTACKS = (4, 7, 5, 8)


class ScriptedOpponent:
    """A stateful scripted opponent that re-rolls its style each episode.

    obs[12] is the normalized horizontal gap to the opponent
    ((opp.pos_x - me.pos_x) / 480). Actions are relative (2 = forward
    toward opponent, 1 = back) so this works on either side.

    Styles:
      - rush:   always close the gap, then attack — trains the agent's
                defense and counter-attacking.
      - turtle: hold ground, only attack when the agent comes very close —
                forces the agent to initiate the approach to score a KO.
      - mixed:  approaches about half the time; general-purpose.
    """

    _STYLES = ("rush", "turtle", "mixed")

    def __init__(self):
        self._style = "mixed"
        self._prev_dist = 0.0

    def __call__(self, obs) -> int:
        dist = abs(float(obs[12])) * 480.0
        # New-episode detection: the gap jumps back to ~spawn distance.
        if dist > 320.0 and self._prev_dist <= 320.0:
            self._style = random.choice(self._STYLES)
        self._prev_dist = dist

        if self._style == "rush":
            if dist > 90.0:
                return 2
            return random.choice(_ATTACKS)

        if self._style == "turtle":
            if dist < 80.0:
                return random.choice(_ATTACKS)
            if dist < 115.0:
                return 0          # let the agent come in
            return random.choice((0, 0, 1))  # hold ground, sometimes edge back

        # mixed
        if dist > 100.0:
            return 2 if random.random() < 0.55 else 0
        return random.choice(_ATTACKS + (2, 1))


def main(total_timesteps: int = 1_000_000,
          ckpt_dir: Path = DEFAULT_CKPT_DIR,
          seed: int = 42):
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    raw_env = SinglePerspectiveEnv(
        seed=seed,
        opponent_policy=ScriptedOpponent(),
    )

    model = PPO("MlpPolicy", raw_env, verbose=1,
                 n_steps=2048, batch_size=256,
                 gae_lambda=0.95, gamma=0.99,
                 learning_rate=3e-4, clip_range=0.2, ent_coef=0.03,
                 seed=seed)

    ckpt_cb = CheckpointCallback(save_freq=100_000,
                                  save_path=str(ckpt_dir),
                                  name_prefix="ppo")

    model.learn(total_timesteps=total_timesteps, callback=[ckpt_cb])
    model.save(ckpt_dir / "ppo_final.zip")
    print(f"✅ Training done. Final model: {ckpt_dir / 'ppo_final.zip'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--total_timesteps", type=int, default=1_000_000)
    p.add_argument("--ckpt_dir", type=Path, default=DEFAULT_CKPT_DIR)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    main(total_timesteps=args.total_timesteps,
          ckpt_dir=args.ckpt_dir, seed=args.seed)
