"""PPO training for PixelBattleEnv against a stationary 'turtle' opponent.

Defaults to 1M total timesteps with a checkpoint every 100K.

Curriculum design (learned the hard way over many retrains):
  - vs a *random* opponent the policy collapses to passive stalling:
    random rarely KOs you, so timing out is safe.
  - vs an *always-rushing* opponent it learns counter-punching only — the
    opponent always closes, so the agent never learns to initiate.
  - true *self-play* collapses to a passive draw: both copies go passive.
  - even a *minority* of rushing episodes poisons it: the agent learns to
    back away from an approaching opponent, and in mirror play both copies
    then retreat from each other to the walls.

The fix: train ONLY against a stationary turtle. A turtle gives the agent
zero reward — no approach shaping payoff, no damage, no KO — unless it
walks the whole way in and attacks. Retreating or stalling guarantees a
-75 timeout. So the single learnable policy is "approach, then attack",
keyed on distance. Two copies of that policy approach each other and
trade to a KO. The opponent never moves, so the agent also never learns
the harmful "retreat from a mover" reflex.

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


def scripted_turtle(obs) -> int:
    """A stationary opponent: hold ground, attack only at point-blank.

    obs[12] is the normalized horizontal gap ((opp.pos_x - me.pos_x)/480).
    Actions are relative (2 = forward, 1 = back) so this works on either
    side. The turtle never walks, so the agent has to do all the closing —
    every episode drills "approach then attack" and nothing else.
    """
    dist = abs(float(obs[12])) * 480.0
    if dist < 85.0:
        return random.choice(_ATTACKS)
    return 0


def main(total_timesteps: int = 1_000_000,
          ckpt_dir: Path = DEFAULT_CKPT_DIR,
          seed: int = 42):
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    raw_env = SinglePerspectiveEnv(
        seed=seed,
        opponent_policy=scripted_turtle,
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
