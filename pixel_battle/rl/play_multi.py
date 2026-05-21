"""Render N self-play matches, keeping only those that end in KO.

Output: pixel_battle/output/rl_play_multi/match_001.mp4, match_002.mp4, ...
(numbered by KO order, not seed order)
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from pixel_battle.rl.play import (  # noqa: E402
    run_one_match, DEFAULT_CKPT, ROOT,
)


OUT_DIR = ROOT / "pixel_battle" / "output" / "rl_play_multi"

# Drop KO matches below this hits-per-second floor — they read as
# low-action (fighters circling/retreating). Tuned in Task 11.
MIN_ACTION_RATE = 0.8


def _should_keep(result: dict) -> bool:
    """Keep a match only if it ended in KO and was action-dense."""
    return (result.get("finished_by_ko", False)
            and result.get("action_score", 0.0) >= MIN_ACTION_RATE)


def main(checkpoint: Path = DEFAULT_CKPT,
          num_matches: int = 10,
          seed_start: int = 1000,
          max_seconds: float = 60.0,
          max_seeds_to_try: int = 100):
    pygame.init()
    pygame.display.set_mode((1, 1))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    model = PPO.load(str(checkpoint))

    ko_count = 0
    seed = seed_start
    attempts = 0
    while ko_count < num_matches and attempts < max_seeds_to_try:
        attempts += 1
        tmp_name = f"_seed_{seed}"
        result = run_one_match(
            model, seed=seed, out_dir=OUT_DIR,
            max_seconds=max_seconds, match_name=tmp_name,
        )
        if _should_keep(result):
            ko_count += 1
            final_name = OUT_DIR / f"match_{ko_count:03d}.mp4"
            result["mp4_path"].rename(final_name)
            for p in (result["raw_path"], result["audio_path"]):
                if p.exists():
                    p.unlink()
            print(f"✅ KO #{ko_count}: seed={seed} winner={result['winner']} "
                  f"dur={result['duration_s']:.1f}s -> {final_name.name}")
        else:
            for p in (result["mp4_path"], result["raw_path"], result["audio_path"]):
                if p.exists():
                    p.unlink()
            reason = "no KO" if not result["finished_by_ko"] else \
                f"low action {result['action_score']:.2f}/s"
            print(f"⏭️  Skipped seed={seed} ({reason})")
        seed += 1
    print(f"\nDone. {ko_count} KO matches written to {OUT_DIR}/")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--num_matches", type=int, default=10)
    p.add_argument("--seed_start", type=int, default=1000)
    p.add_argument("--max_seconds", type=float, default=60.0)
    p.add_argument("--max_seeds_to_try", type=int, default=100)
    args = p.parse_args()
    main(**vars(args))
