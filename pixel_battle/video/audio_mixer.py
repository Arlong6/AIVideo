"""Bus-based audio mixer for pixel_battle.

Replaces the flat pydub overlay in compose.py with:
  - SlotLimiter: per-bus concurrent-overlap cap
  - Bus: pedalboard chain + placements
  - AudioMixer: BGM / cast / hit / ult buses + final ffmpeg sidechain mix
"""
from __future__ import annotations
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import numpy as np
import soundfile as sf
from pedalboard import (Gain, HighpassFilter, Limiter, LowShelfFilter,
                        Pedalboard, PeakFilter)


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
      - BGM:  hi-pass 40Hz + -12dB   (sits under everything; sidechain target)
      - cast: hi-pass 200Hz + -8dB + limiter + 2-slot SlotLimiter
      - hit:  hi-pass 50Hz + presence +3dB @ 2kHz + limiter (cuts through)
      - ult:  hi-pass 45Hz + 0dB + limiter

    THE LOW-END REBALANCE (2026-09-20) — why the hit bus no longer boosts bass.

    arlong reported the finished videos are uncomfortable to listen to. The first
    theory was harshness; measurement killed it (the mix sits at 2% of energy in
    2-8kHz, about as un-harsh as audio gets). The actual spectrum of a shipped
    short was the opposite pathology:

        <60Hz    35.3%        300Hz-2kHz  11.4%
        60-120Hz 47.0%        2k-8kHz      2.0%

    82% of all energy below 120Hz, and a hollow midrange. Sustained sub-bass at
    volume is a known fatigue mechanism — it reads as ear pressure rather than
    sharpness, which is exactly why it did not look like a problem at first.

    Three things were stacking it up: the synthesized hits are almost pure
    low thumps (hit.wav measures 99.8% under 300Hz), no bus had a high-pass so
    sub-60Hz rumble passed through untouched, and this bus then added another
    +3dB under 120Hz on top.

    The replacement keeps hits cutting through, but does it in the midrange
    where the ear actually locates an impact. That also fixes a second problem
    nobody had connected: phone speakers roll off steeply in the low bass, so on
    the device most of this audience watches on, 82% of the energy was simply
    not being reproduced and the hits landed weak.
    """

    def __init__(self, sample_rate: int = 48000):
        self.sr = sample_rate
        self.bgm_bus = Bus(
            name="bgm", sample_rate=sample_rate,
            chain=Pedalboard([
                # Nothing musical lives below 40Hz in a loop like this; what is
                # down there is rumble that only shows up as pressure.
                HighpassFilter(cutoff_frequency_hz=40.0),
                Gain(gain_db=-12.0),
            ]),
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
                HighpassFilter(cutoff_frequency_hz=50.0),
                # Was LowShelfFilter(120Hz, +3dB) — see the class docstring. A
                # presence bump does the same job (make the hit read) in the band
                # the ear uses to place an impact, and that a phone can reproduce.
                PeakFilter(cutoff_frequency_hz=2000.0, gain_db=3.0, q=0.8),
                Gain(gain_db=0.0),
                Limiter(threshold_db=-1.0, release_ms=50.0),
            ]),
        )
        self.ult_bus = Bus(
            name="ult", sample_rate=sample_rate,
            chain=Pedalboard([
                # The ultimate is allowed more weight than a basic hit, so this
                # sits lower than the other buses — but still not sub-audible.
                HighpassFilter(cutoff_frequency_hz=45.0),
                Gain(gain_db=0.0),
                Limiter(threshold_db=-1.0, release_ms=100.0),
            ]),
        )

    def export(self, total_duration_ms: int, output_path: str) -> None:
        """Render each bus → 4 temp wavs → ffmpeg sidechain mix → output.

        ffmpeg graph:
          1. [hit][ult]amix=2          → [trig]    (sidechain trigger)
          2. [bgm][trig]sidechaincompress → [bgm_ducked]   (ratio 2.5, rel 120ms)
          3. [bgm_ducked][cast][hit][ult]amix=4 → [mixed]
          4. [mixed]loudnorm=I=-14:TP=-1.5 → [out]
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = {}
            for bus in (self.bgm_bus, self.cast_bus, self.hit_bus, self.ult_bus):
                samples = bus.render(total_duration_ms)
                p = Path(tmpdir) / f"{bus.name}.wav"
                sf.write(str(p), samples, self.sr)
                paths[bus.name] = str(p)

            cmd = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", paths["bgm"],
                "-i", paths["cast"],
                "-i", paths["hit"],
                "-i", paths["ult"],
                "-filter_complex",
                "[2:a][3:a]amix=inputs=2:duration=longest:normalize=0[trig];"
                # ratio 4 / release 200ms ducked the music hard on every single
                # hit — 36 of them in a 53s fight, measured as 97 jumps over 6dB
                # and 50 over 10dB per 100ms window. That constant pumping is
                # fatiguing on its own, separately from the low-end problem.
                # Gentler ratio and a faster recovery keep the duck audible as
                # space for the impact without the mix breathing all the way in
                # and out several dozen times.
                "[0:a][trig]sidechaincompress="
                "threshold=0.1:ratio=2.5:attack=5:release=120[bgm_ducked];"
                "[bgm_ducked][1:a][2:a][3:a]amix=inputs=4:"
                "duration=longest:normalize=0[mixed];"
                "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[out]",
                "-map", "[out]",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
