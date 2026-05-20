"""PPO self-play training for PixelBattleEnv.

Defaults to 1M total timesteps with a checkpoint every 100K. Starts
opponent_policy as random; after the first 50K steps, swaps opponent to
the live model itself (in-place self-play).

Usage:
    python -m pixel_battle.rl.train --total_timesteps 1000000
"""
from __future__ import annotations
import argparse
import random
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback

from pixel_battle.rl.env import SinglePerspectiveEnv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT_DIR = ROOT / "data" / "rl_checkpoints"


class SelfPlaySwapCallback(BaseCallback):
    """After `swap_after` steps, replace random opponent with live model."""

    def __init__(self, env: SinglePerspectiveEnv,
                  swap_after: int = 50_000, verbose: int = 0):
        super().__init__(verbose)
        self.env = env
        self.swap_after = swap_after
        self.swapped = False

    def _on_step(self) -> bool:
        if not self.swapped and self.num_timesteps >= self.swap_after:
            def policy(obs):
                act, _ = self.model.predict(obs, deterministic=False)
                return int(act)
            self.env.set_opponent_policy(policy)
            self.swapped = True
            if self.verbose:
                print(f"[SelfPlaySwap] swapped at step {self.num_timesteps}")
        return True


def main(total_timesteps: int = 1_000_000,
          ckpt_dir: Path = DEFAULT_CKPT_DIR,
          seed: int = 42):
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Initial opponent: random
    raw_env = SinglePerspectiveEnv(
        seed=seed,
        opponent_policy=lambda obs: random.randint(0, 8),
    )

    model = PPO("MlpPolicy", raw_env, verbose=1,
                 n_steps=2048, batch_size=256,
                 gae_lambda=0.95, gamma=0.99,
                 learning_rate=3e-4, clip_range=0.2, ent_coef=0.01,
                 seed=seed)

    ckpt_cb = CheckpointCallback(save_freq=100_000,
                                  save_path=str(ckpt_dir),
                                  name_prefix="ppo")
    swap_cb = SelfPlaySwapCallback(raw_env, swap_after=50_000, verbose=1)

    model.learn(total_timesteps=total_timesteps,
                 callback=[ckpt_cb, swap_cb])
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
