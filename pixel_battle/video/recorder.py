"""Pipe Pygame Surface frames to ffmpeg subprocess for mp4 encoding."""
import subprocess
from typing import Optional

import pygame


class FrameRecorder:
    def __init__(self, output_path: str, fps: int, width: int, height: int):
        self.output_path = output_path
        self.fps = fps
        self.width = width
        self.height = height
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", "-",
            "-an",
            "-vcodec", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "veryfast",
            "-crf", "22",
            self.output_path,
        ]
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def write_frame(self, surface: pygame.Surface) -> None:
        if self._proc is None:
            raise RuntimeError("Recorder not started")
        raw = pygame.image.tostring(surface, "RGB")
        self._proc.stdin.write(raw)

    def stop(self) -> None:
        if self._proc is None:
            return
        self._proc.stdin.close()
        self._proc.wait(timeout=30)
        self._proc = None
