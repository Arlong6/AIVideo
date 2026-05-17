import os
import subprocess
import pygame
from pathlib import Path

from pixel_battle.video.recorder import FrameRecorder
from pixel_battle.engine.renderer import WIDTH, HEIGHT


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()


def test_recorder_produces_mp4_with_correct_duration(tmp_path):
    out = tmp_path / "out.mp4"
    rec = FrameRecorder(str(out), fps=60, width=WIDTH, height=HEIGHT)
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((30, 30, 100))
    rec.start()
    for _ in range(120):
        rec.write_frame(surf)
    rec.stop()

    assert out.exists()
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    dur = float(res.stdout.strip())
    assert 1.8 < dur < 2.2, f"Expected ~2s, got {dur}"
