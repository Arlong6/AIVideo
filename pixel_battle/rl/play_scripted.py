# pixel_battle/rl/play_scripted.py
"""Render a fight from an authored YAML script (no RL policy).

Auto-detects legacy condition scripts and new timeline scripts; the loader
returns whichever driver fits the file."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.play import _render_fight, WIDTH, HEIGHT, RENDER_FPS, ROOT  # noqa: E402
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.script.loader import load_fight_file  # noqa: E402

OUT_DIR = ROOT / "pixel_battle" / "output" / "scripted"


def _driver_action_source(driver):
    """Adapt any driver with `.decide(battle)` to the
    (env, obs) -> (left_act, right_act) interface used by `_render_fight`."""
    def _source(env, _obs):
        return driver.decide(env.battle)
    return _source


# Backward-compat alias — existing tests import this name.
_script_action_source = _driver_action_source


def render_script(script_path: Path, out_dir: Path = OUT_DIR) -> Path:
    pygame.init()
    pygame.display.set_mode((1, 1))
    out_dir.mkdir(parents=True, exist_ok=True)

    driver = load_fight_file(script_path)
    tl_seed = getattr(driver.timeline, "seed", None)
    env_kwargs = {"left_id": driver.left, "right_id": driver.right}
    if tl_seed is not None:
        env_kwargs["seed"] = tl_seed
    env = PixelBattleEnv(**env_kwargs)

    raw = out_dir / f"{script_path.stem}_raw.mp4"
    recorder = FrameRecorder(str(raw), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
    recorder.start()
    try:
        _render_fight(recorder, _driver_action_source(driver), env,
                      max_seconds=60.0, end_hold_frames=120)
    finally:
        recorder.stop()
    print(f"Scripted render: {raw}")
    return raw


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("script", type=Path, help="path to a fight-script YAML")
    args = p.parse_args()
    render_script(args.script)
