"""Bus-based audio mixer for pixel_battle.

Replaces the flat pydub overlay in compose.py with:
  - SlotLimiter: per-bus concurrent-overlap cap
  - Bus: pedalboard chain + placements
  - AudioMixer: BGM / cast / hit / ult buses + final ffmpeg sidechain mix
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np
from pedalboard import Gain, HighpassFilter, LowShelfFilter, Limiter, Pedalboard


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


@dataclass
class Bus:
    """One audio bus with a pedalboard chain and a list of placements.

    Each placement is (samples, start_t_ms). render() sums all placements
    into a single numpy array of `total_ms` length, then runs the chain.
    """
    name: str
    sample_rate: int
    chain: Pedalboard
    placements: List[Tuple[np.ndarray, int]] = field(default_factory=list)
    limiter: SlotLimiter | None = None

    def add(self, samples: np.ndarray, t_ms: int) -> bool:
        """Place a sample at t_ms. Returns False if limiter rejects."""
        dur_ms = int(len(samples) * 1000 / self.sample_rate)
        if self.limiter and not self.limiter.can_add(t_ms, dur_ms):
            return False
        self.placements.append((samples.astype(np.float32, copy=False), t_ms))
        return True

    def render(self, total_ms: int) -> np.ndarray:
        n = int(total_ms * self.sample_rate / 1000)
        track = np.zeros(n, dtype=np.float32)
        for samp, t_ms in self.placements:
            start = int(t_ms * self.sample_rate / 1000)
            if start >= n:
                continue
            end = min(start + len(samp), n)
            track[start:end] += samp[: end - start]
        return self.chain(track, self.sample_rate)


class AudioMixer:
    """Owns 4 buses (BGM/cast/hit/ult) + a final ffmpeg sidechain export.

    Default chains tuned for pixel-battle:
      - BGM:  -12dB gain   (sits under everything; sidechain target)
      - cast: hi-pass 200Hz + -8dB + limiter + 2-slot SlotLimiter
      - hit:  low-shelf +3dB @ 120Hz + 0dB + limiter (cuts through)
      - ult:  0dB + limiter
    """

    def __init__(self, sample_rate: int = 48000):
        self.sr = sample_rate
        self.bgm_bus = Bus(
            name="bgm", sample_rate=sample_rate,
            chain=Pedalboard([Gain(gain_db=-12.0)]),
        )
        self.cast_bus = Bus(
            name="cast", sample_rate=sample_rate,
            chain=Pedalboard([
                HighpassFilter(cutoff_frequency_hz=200.0),
                Gain(gain_db=-8.0),
                Limiter(threshold_db=-2.0, release_ms=80.0),
            ]),
            limiter=SlotLimiter(max_concurrent=2),
        )
        self.hit_bus = Bus(
            name="hit", sample_rate=sample_rate,
            chain=Pedalboard([
                LowShelfFilter(cutoff_frequency_hz=120.0, gain_db=3.0),
                Gain(gain_db=0.0),
                Limiter(threshold_db=-1.0, release_ms=50.0),
            ]),
        )
        self.ult_bus = Bus(
            name="ult", sample_rate=sample_rate,
            chain=Pedalboard([
                Gain(gain_db=0.0),
                Limiter(threshold_db=-1.0, release_ms=100.0),
            ]),
        )

    def export(self, total_duration_ms: int, output_path: str) -> None:
        raise NotImplementedError("export filled in by Task 4")
