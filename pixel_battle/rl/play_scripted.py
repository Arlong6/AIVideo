# pixel_battle/rl/play_scripted.py
"""Render a fight from an authored YAML script (no RL policy)."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.play import _render_fight, WIDTH, HEIGHT, FPS, ROOT  # noqa: E402
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.script.driver import ScriptDriver  # noqa: E402
from pixel_battle.script.loader import load_script  # noqa: E402

OUT_DIR = ROOT / "pixel_battle" / "output" / "scripted"


def _script_action_source(driver: ScriptDriver):
    """Adapt a ScriptDriver to the (env, obs) -> (left_act, right_act) interface."""
    def _source(env, _obs):
        return driver.decide(env.battle)
    return _source


def render_script(script_path: Path, out_dir: Path = OUT_DIR) -> Path:
    """Render the fight described by `script_path`; return the mp4 path."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    out_dir.mkdir(parents=True, exist_ok=True)

    script = load_script(script_path)
    env = PixelBattleEnv(left_id=script.left, right_id=script.right)
    driver = ScriptDriver(script)

    raw = out_dir / f"{script_path.stem}_raw.mp4"
    recorder = FrameRecorder(str(raw), fps=FPS, width=WIDTH, height=HEIGHT)
    recorder.start()
    try:
        _render_fight(recorder, _script_action_source(driver), env,
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
