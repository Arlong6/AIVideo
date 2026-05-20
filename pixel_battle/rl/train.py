"""PPO self-play training for PixelBattleEnv.

Defaults to 1M total timesteps with a checkpoint every 100K. The opponent
starts as a scripted aggressive fighter (approach + attack); after the
first 500K steps it swaps to the live model for self-play refinement.

The scripted opponent is the key curriculum choice: against a *random*
opponent, standing passive is safe (random rarely KOs you), so the agent
learns to stall. Against an aggressive opponent, passivity means getting
KO'd (-50), which forces the agent to learn to fight back.

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


def scripted_aggressive(obs) -> int:
    """A competent rushdown opponent: close the gap, then attack.

    obs[12] is the normalized horizontal gap to the opponent
    ((opp.pos_x - me.pos_x) / 480). Actions are relative, so 2 = forward
    toward the opponent regardless of which side this policy controls.
    """
    dist = abs(float(obs[12])) * 480.0
    if dist > 90.0:
        return 2  # forward toward opponent
    r = random.random()
    if r < 0.42:
        return 4  # basic
    if r < 0.62:
        return 7  # special
    if r < 0.78:
        return 5  # cooldown skill
    if r < 0.90:
        return 8  # kick
    return 2      # stay in close


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

    # Initial opponent: scripted aggressive fighter (curriculum — see docstring)
    raw_env = SinglePerspectiveEnv(
        seed=seed,
        opponent_policy=scripted_aggressive,
    )

    model = PPO("MlpPolicy", raw_env, verbose=1,
                 n_steps=2048, batch_size=256,
                 gae_lambda=0.95, gamma=0.99,
                 learning_rate=3e-4, clip_range=0.2, ent_coef=0.03,
                 seed=seed)

    ckpt_cb = CheckpointCallback(save_freq=100_000,
                                  save_path=str(ckpt_dir),
                                  name_prefix="ppo")
    # Curriculum: face the scripted aggressive opponent for the first 500K
    # steps (learn solid offense + defense), then swap to self-play.
    swap_cb = SelfPlaySwapCallback(raw_env, swap_after=500_000, verbose=1)

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
