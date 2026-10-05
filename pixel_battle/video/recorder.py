"""Pipe Pygame Surface frames to ffmpeg subprocess for mp4 encoding."""
import subprocess
from typing import Optional

import pygame


class FrameRecorder:
    def __init__(self, output_path: str, fps: int, width: int, height: int,
                 out_size: Optional[tuple[int, int]] = None):
        self.output_path = output_path
        self.fps = fps
        self.width = width
        self.height = height
        # When frames arrive larger than the delivered size (supersampling),
        # ffmpeg downscales them here. Lanczos keeps thin lines crisp.
        self.out_size = out_size if out_size and tuple(out_size) != (width, height) else None
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
            *(["-vf", f"scale={self.out_size[0]}:{self.out_size[1]}:flags=lanczos"]
              if self.out_size else []),
            "-vcodec", "libx264",
            "-pix_fmt", "yuv420p",
            # Near-lossless intermediate — this raw gets re-encoded by
            # build_short, so artifacts here would compound downstream.
            "-preset", "fast",
            "-crf", "16",
            self.output_path,
        ]
        # stderr was DEVNULL, which threw away the only explanation whenever an
        # encode failed — "ffmpeg encoding failed (exit code 255)" with nothing
        # to act on. Keep the tail instead; ffmpeg is chatty but bounded, and a
        # failed render is exactly when those lines are worth having.
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )

    def write_frame(self, surface: pygame.Surface) -> None:
        if self._proc is None:
            raise RuntimeError("Recorder not started")
        raw = pygame.image.tostring(surface, "RGB")
        try:
            self._proc.stdin.write(raw)
        except BrokenPipeError:
            # ffmpeg died mid-render. Surface its complaint now rather than
            # letting the next 3000 frames fail one at a time.
            err = self._drain_stderr()
            raise RuntimeError(
                f"ffmpeg closed the pipe mid-render:\n{err}") from None

    def _drain_stderr(self, keep: int = 2000) -> str:
        if self._proc is None or self._proc.stderr is None:
            return "(no stderr captured)"
        try:
            return self._proc.stderr.read().decode("utf-8", "replace")[-keep:]
        except Exception:
            return "(stderr unreadable)"

    def stop(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        err = self._drain_stderr()
        rc = self._proc.wait(timeout=30)
        self._proc = None
        if rc != 0:
            raise RuntimeError(
                f"ffmpeg encoding failed (exit code {rc}):\n{err}")
