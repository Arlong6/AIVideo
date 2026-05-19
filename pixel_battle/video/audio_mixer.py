"""Bus-based audio mixer for pixel_battle.

Replaces the flat pydub overlay in compose.py with:
  - SlotLimiter: per-bus concurrent-overlap cap
  - Bus: pedalboard chain + placements
  - AudioMixer: BGM / cast / hit / ult buses + final ffmpeg sidechain mix
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple


class SlotLimiter:
    """Tracks active sound windows on a bus.

    can_add(t_ms, duration_ms) returns False when max_concurrent slots
    are already active at t_ms. Otherwise records the new window and
    returns True.
    """

    def __init__(self, max_concurrent: int):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max = max_concurrent
        self.windows: List[Tuple[int, int]] = []  # (start_ms, end_ms)

    def can_add(self, t_ms: int, duration_ms: int) -> bool:
        # Prune expired windows (end <= t_ms means freed)
        self.windows = [(s, e) for s, e in self.windows if e > t_ms]
        active = sum(1 for s, e in self.windows if s <= t_ms < e)
        if active >= self.max:
            return False
        self.windows.append((t_ms, t_ms + duration_ms))
        return True
