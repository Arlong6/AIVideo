# Pixel Battle Audio Mixer Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `compose.py`'s flat pydub overlay with a bus-based audio mixer (`pedalboard` + ffmpeg `sidechaincompress`) so cast SFX no longer blanket-overlap and real hits cut through via BGM ducking. Final loudness normalized to -14 LUFS (TikTok target). BGM swap to synthwave track.

**Architecture:** New `pixel_battle/video/audio_mixer.py` module with `SlotLimiter`, `Bus`, `AudioMixer`. Each bus owns a `pedalboard.Pedalboard` chain (gain/EQ/limiter). Buses render to numpy arrays, then a final ffmpeg `filter_complex` pass performs sidechain ducking and `loudnorm`. `compose.py::build_audio_track` is rewritten to route events to buses but keeps its public signature.

**Tech Stack:** Python 3, numpy, pedalboard (Spotify), soundfile, ffmpeg 8.0+, pytest. New dep: `pip install pedalboard soundfile`.

**Spec:** `docs/superpowers/specs/2026-05-19-pixel-battle-audio-mixer-design.md`

---

## File Structure

**Created:**
- `pixel_battle/video/audio_mixer.py` — `SlotLimiter`, `Bus`, `AudioMixer`
- `pixel_battle/tests/test_audio_mixer_slot_limiter.py` — SlotLimiter unit tests
- `pixel_battle/tests/test_audio_mixer_bus.py` — Bus unit tests
- `pixel_battle/tests/test_audio_mixer_export.py` — End-to-end export tests

**Modified:**
- `pixel_battle/video/compose.py` — rewrite `build_audio_track`; signature preserved
- `pixel_battle/assets/bgm/battle_loop.mp3` — replaced with chosen synthwave track (separate BGM-hunt task delivers candidates)
- `pixel_battle/tests/test_compose.py` — adapt to new internals

**Unchanged:** `pixel_battle/video/compose.py::mux_audio_video`, `pixel_battle/video/recorder.py`, episode runner.

---

## Implementation Order

1. **Task 1** — Install dependencies + `SlotLimiter` (TDD)
2. **Task 2** — `Bus` class + `pedalboard` chain (TDD)
3. **Task 3** — `AudioMixer` skeleton (4-bus instantiation, TDD)
4. **Task 4** — `AudioMixer.export` ffmpeg sidechain integration (TDD with smoke)
5. **Task 5** — Helper functions in `compose.py` (`_load_wav`, `_loop_to_length`, `_load_sfx_samples`)
6. **Task 6** — Rewrite `compose.py::build_audio_track`; keep signature
7. **Task 7** — BGM swap (consumes BGM-hunt output)
8. **Task 8** — Visual regression: regenerate `final.mp4`, verify loudness

---

### Task 1: Dependencies + `SlotLimiter`

**Files:**
- Create: `pixel_battle/video/audio_mixer.py` (initial — only `SlotLimiter`)
- Create: `pixel_battle/tests/test_audio_mixer_slot_limiter.py`

- [ ] **Step 1.1: Install runtime deps**

Run: `pip install pedalboard soundfile`
Expected: install successful (pedalboard >=0.9.0, soundfile >=0.12).
Verify: `python -c "import pedalboard, soundfile; print(pedalboard.__version__, soundfile.__version__)"`

- [ ] **Step 1.2: Write failing tests**

Create `pixel_battle/tests/test_audio_mixer_slot_limiter.py`:

```python
"""SlotLimiter caps concurrent-overlapping events on a bus."""
from pixel_battle.video.audio_mixer import SlotLimiter


def test_fresh_limiter_accepts_first_event():
    lim = SlotLimiter(max_concurrent=2)
    assert lim.can_add(t_ms=0, duration_ms=300) is True


def test_limiter_accepts_up_to_max_concurrent():
    lim = SlotLimiter(max_concurrent=2)
    assert lim.can_add(0, 300) is True
    assert lim.can_add(50, 300) is True
    # Third overlapping event rejected
    assert lim.can_add(100, 300) is False


def test_limiter_accepts_after_window_expires():
    lim = SlotLimiter(max_concurrent=2)
    lim.can_add(0, 300)
    lim.can_add(50, 300)
    # At t=500, both windows (ending 300, 350) have expired
    assert lim.can_add(500, 300) is True


def test_limiter_non_overlapping_all_accepted():
    lim = SlotLimiter(max_concurrent=1)
    for t in (0, 400, 800, 1200):
        assert lim.can_add(t, 300) is True


def test_limiter_boundary_inclusive():
    """If a window ends at t_ms exactly, that slot is free at t_ms."""
    lim = SlotLimiter(max_concurrent=1)
    lim.can_add(0, 300)   # window [0, 300)
    assert lim.can_add(300, 300) is True
```

- [ ] **Step 1.3: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_audio_mixer_slot_limiter.py -v`
Expected: ImportError — `pixel_battle.video.audio_mixer` does not exist yet.

- [ ] **Step 1.4: Implement `SlotLimiter`**

Create `pixel_battle/video/audio_mixer.py`:

```python
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
```

- [ ] **Step 1.5: Run tests to verify pass**

Run: `pytest pixel_battle/tests/test_audio_mixer_slot_limiter.py -v`
Expected: PASS (5 passed)

- [ ] **Step 1.6: Commit**

```bash
git add pixel_battle/video/audio_mixer.py pixel_battle/tests/test_audio_mixer_slot_limiter.py
git commit -m "feat(pixel-battle): audio_mixer SlotLimiter — concurrent-overlap cap"
```

---

### Task 2: `Bus` class with pedalboard chain

**Files:**
- Modify: `pixel_battle/video/audio_mixer.py` (append Bus class)
- Create: `pixel_battle/tests/test_audio_mixer_bus.py`

- [ ] **Step 2.1: Write the failing test**

Create `pixel_battle/tests/test_audio_mixer_bus.py`:

```python
"""Bus owns a pedalboard chain and renders placements to a numpy array."""
import numpy as np
from pedalboard import Pedalboard, Gain

from pixel_battle.video.audio_mixer import Bus, SlotLimiter


def test_bus_add_returns_true_when_no_limiter():
    b = Bus(name="test", sample_rate=48000, chain=Pedalboard([Gain(gain_db=0)]))
    samp = np.zeros(48000, dtype=np.float32)  # 1s of silence
    assert b.add(samp, t_ms=0) is True


def test_bus_add_respects_limiter():
    lim = SlotLimiter(max_concurrent=1)
    b = Bus(name="test", sample_rate=48000,
            chain=Pedalboard([Gain(gain_db=0)]), limiter=lim)
    samp = np.zeros(int(48000 * 0.5), dtype=np.float32)  # 500ms
    assert b.add(samp, t_ms=0) is True
    assert b.add(samp, t_ms=100) is False  # Overlap → reject


def test_bus_render_produces_array_of_total_length():
    b = Bus(name="test", sample_rate=48000, chain=Pedalboard([Gain(gain_db=0)]))
    samp = np.ones(4800, dtype=np.float32)  # 100ms
    b.add(samp, t_ms=200)
    out = b.render(total_ms=1000)
    assert out.shape == (48000,), f"expected (48000,), got {out.shape}"
    # Sample should land at index 9600 (200ms * 48 samples/ms)
    assert np.any(out[9600:14400] != 0), "sample not placed at correct position"


def test_bus_render_multiple_placements_sum():
    b = Bus(name="test", sample_rate=48000, chain=Pedalboard([Gain(gain_db=0)]))
    samp = np.ones(4800, dtype=np.float32) * 0.5
    b.add(samp, t_ms=0)
    b.add(samp, t_ms=50)  # Overlaps first by 50ms
    out = b.render(total_ms=500)
    # In the overlap window (50-100ms = idx 2400-4800), value should be ~1.0
    assert out[3000] > 0.9, f"overlap should sum to ~1.0, got {out[3000]}"


def test_bus_chain_applies_gain():
    """Pedalboard chain affects rendered output."""
    quiet = Bus(name="q", sample_rate=48000,
                chain=Pedalboard([Gain(gain_db=-20)]))
    samp = np.ones(4800, dtype=np.float32)
    quiet.add(samp, t_ms=0)
    out = quiet.render(total_ms=200)
    # -20dB should attenuate to ~0.1 amplitude
    peak = np.abs(out).max()
    assert 0.05 < peak < 0.15, f"expected ~0.1 peak from -20dB, got {peak}"
```

- [ ] **Step 2.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_audio_mixer_bus.py -v`
Expected: ImportError — `Bus` not exported from `audio_mixer`.

- [ ] **Step 2.3: Implement `Bus`**

Append to `pixel_battle/video/audio_mixer.py`:

```python
import numpy as np
from pedalboard import Pedalboard


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
```

- [ ] **Step 2.4: Run tests to verify pass**

Run: `pytest pixel_battle/tests/test_audio_mixer_bus.py -v`
Expected: PASS (5 passed)

- [ ] **Step 2.5: Commit**

```bash
git add pixel_battle/video/audio_mixer.py pixel_battle/tests/test_audio_mixer_bus.py
git commit -m "feat(pixel-battle): audio_mixer Bus — pedalboard chain + placements"
```

---

### Task 3: `AudioMixer` skeleton with 4 buses

**Files:**
- Modify: `pixel_battle/video/audio_mixer.py` (append AudioMixer)
- Create: `pixel_battle/tests/test_audio_mixer_export.py` (initial — instantiation tests only)

- [ ] **Step 3.1: Write the failing test**

Create `pixel_battle/tests/test_audio_mixer_export.py`:

```python
"""AudioMixer composes BGM / cast / hit / ult buses."""
import numpy as np
from pixel_battle.video.audio_mixer import AudioMixer, Bus


def test_audio_mixer_has_four_buses():
    m = AudioMixer()
    assert isinstance(m.bgm_bus, Bus) and m.bgm_bus.name == "bgm"
    assert isinstance(m.cast_bus, Bus) and m.cast_bus.name == "cast"
    assert isinstance(m.hit_bus, Bus) and m.hit_bus.name == "hit"
    assert isinstance(m.ult_bus, Bus) and m.ult_bus.name == "ult"


def test_cast_bus_has_two_slot_limiter():
    m = AudioMixer()
    assert m.cast_bus.limiter is not None
    assert m.cast_bus.limiter.max == 2


def test_other_buses_have_no_limiter():
    m = AudioMixer()
    assert m.bgm_bus.limiter is None
    assert m.hit_bus.limiter is None
    assert m.ult_bus.limiter is None


def test_audio_mixer_sample_rate_default_48000():
    m = AudioMixer()
    assert m.sr == 48000
    for b in (m.bgm_bus, m.cast_bus, m.hit_bus, m.ult_bus):
        assert b.sample_rate == 48000
```

- [ ] **Step 3.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_audio_mixer_export.py -v`
Expected: ImportError — `AudioMixer` not defined.

- [ ] **Step 3.3: Implement `AudioMixer` skeleton**

Append to `pixel_battle/video/audio_mixer.py`:

```python
from pedalboard import Gain, HighpassFilter, LowShelfFilter, Limiter


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
```

- [ ] **Step 3.4: Run tests to verify pass**

Run: `pytest pixel_battle/tests/test_audio_mixer_export.py -v`
Expected: PASS (4 passed)

- [ ] **Step 3.5: Commit**

```bash
git add pixel_battle/video/audio_mixer.py pixel_battle/tests/test_audio_mixer_export.py
git commit -m "feat(pixel-battle): AudioMixer skeleton — 4 buses (BGM/cast/hit/ult)"
```

---

### Task 4: `AudioMixer.export` with ffmpeg sidechain

**Files:**
- Modify: `pixel_battle/video/audio_mixer.py` (replace `export` stub)
- Modify: `pixel_battle/tests/test_audio_mixer_export.py` (add end-to-end test)

- [ ] **Step 4.1: Write the failing test**

Append to `pixel_battle/tests/test_audio_mixer_export.py`:

```python
import os
import subprocess
import tempfile

import numpy as np

from pixel_battle.video.audio_mixer import AudioMixer


def _has_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def test_export_produces_wav_of_expected_length(tmp_path):
    if not _has_ffmpeg():
        import pytest
        pytest.skip("ffmpeg not on PATH")
    m = AudioMixer()
    # Single 100ms hit sample at t=500ms
    hit = (np.sin(2 * np.pi * 220 * np.arange(4800) / 48000)
           * 0.3).astype(np.float32)
    m.hit_bus.add(hit, t_ms=500)
    out = tmp_path / "out.wav"
    m.export(total_duration_ms=2000, output_path=str(out))
    assert out.exists()
    # Probe duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    dur = float(r.stdout.strip())
    assert 1.9 < dur < 2.1, f"expected ~2.0s, got {dur}"


def test_export_applies_loudnorm_keeps_below_clipping(tmp_path):
    if not _has_ffmpeg():
        import pytest
        pytest.skip("ffmpeg not on PATH")
    m = AudioMixer()
    # Very loud BGM samples (would clip without loudnorm)
    bgm = (np.ones(48000 * 2, dtype=np.float32) * 0.95)
    m.bgm_bus.add(bgm, t_ms=0)
    out = tmp_path / "loud.wav"
    m.export(total_duration_ms=2000, output_path=str(out))
    # Read back and check peak
    import soundfile as sf
    samples, sr = sf.read(str(out))
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    peak_db = 20 * np.log10(np.abs(samples).max() + 1e-9)
    # loudnorm TP=-1.5 means true-peak should not exceed -1.5dB
    assert peak_db < -0.5, f"peak {peak_db}dB exceeds loudnorm contract"
```

- [ ] **Step 4.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_audio_mixer_export.py -v`
Expected: 2 new tests FAIL with `NotImplementedError`.

- [ ] **Step 4.3: Implement `export`**

In `pixel_battle/video/audio_mixer.py`, add imports near top:

```python
import subprocess
import tempfile
from pathlib import Path

import soundfile as sf
```

Replace the `export` stub with:

```python
    def export(self, total_duration_ms: int, output_path: str) -> None:
        """Render each bus → 4 temp wavs → ffmpeg sidechain mix → output.

        ffmpeg graph:
          1. [hit][ult]amix=2          → [trig]    (sidechain trigger)
          2. [bgm][trig]sidechaincompress → [bgm_ducked]
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
                "[0:a][trig]sidechaincompress="
                "threshold=0.1:ratio=4:attack=5:release=200[bgm_ducked];"
                "[bgm_ducked][1:a][2:a][3:a]amix=inputs=4:"
                "duration=longest:normalize=0[mixed];"
                "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[out]",
                "-map", "[out]",
                output_path,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
```

- [ ] **Step 4.4: Run tests to verify pass**

Run: `pytest pixel_battle/tests/test_audio_mixer_export.py -v`
Expected: PASS (6 passed — 4 from Task 3 + 2 new export tests)

- [ ] **Step 4.5: Run full suite — no regressions**

Run: `pytest pixel_battle/tests/ --ignore=pixel_battle/tests/test_renderer.py --deselect pixel_battle/tests/test_battle_ai_priority.py::test_ai_retreats_when_mp_high_and_close -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 4.6: Commit**

```bash
git add pixel_battle/video/audio_mixer.py pixel_battle/tests/test_audio_mixer_export.py
git commit -m "feat(pixel-battle): AudioMixer.export — ffmpeg sidechain + loudnorm -14"
```

---

### Task 5: Helper functions in `compose.py`

**Files:**
- Modify: `pixel_battle/video/compose.py` (add helpers above `build_audio_track`)
- Create: `pixel_battle/tests/test_compose_helpers.py`

- [ ] **Step 5.1: Write the failing tests**

Create `pixel_battle/tests/test_compose_helpers.py`:

```python
"""Helpers used by the rewritten build_audio_track."""
import numpy as np
import soundfile as sf

from pixel_battle.video.compose import (
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
)


def test_load_wav_resamples_to_target(tmp_path):
    p = tmp_path / "src.wav"
    # Write 1s of 44.1k mono sine
    src = np.sin(2 * np.pi * 440 * np.arange(44100) / 44100).astype(np.float32)
    sf.write(str(p), src, 44100)
    out = _load_wav(p, target_sr=48000)
    # Should be ~48000 samples for 1s at 48k
    assert 47900 < len(out) < 48100, f"unexpected length {len(out)}"
    assert out.dtype == np.float32


def test_loop_to_length_extends_short_sample():
    samp = np.ones(48000, dtype=np.float32) * 0.5  # 1s @ 48k
    looped = _loop_to_length(samp, total_ms=2500, sample_rate=48000)
    # Should be 2.5s = 120,000 samples
    assert len(looped) == 120000


def test_loop_to_length_truncates_long_sample():
    samp = np.ones(48000 * 5, dtype=np.float32)  # 5s
    looped = _loop_to_length(samp, total_ms=2000, sample_rate=48000)
    assert len(looped) == 96000  # 2s


def test_load_sfx_samples_or_none_missing_returns_none():
    assert _load_sfx_samples_or_none("definitely_not_a_real_sfx_xyz", 48000) is None
```

- [ ] **Step 5.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_compose_helpers.py -v`
Expected: ImportError — helpers not defined yet.

- [ ] **Step 5.3: Add helpers to `compose.py`**

In `pixel_battle/video/compose.py`, after the existing imports add:

```python
import numpy as np
import soundfile as sf
```

After `_load_sfx_or_none`, add:

```python
def _load_wav(path: Path, target_sr: int) -> np.ndarray:
    """Load a wav/mp3 as mono float32 at target_sr. Resamples if needed."""
    data, sr = sf.read(str(path), always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32, copy=False)
    if sr != target_sr:
        # Simple linear resample — fine for ducking/loop content
        n_out = int(len(data) * target_sr / sr)
        idx = np.linspace(0, len(data) - 1, n_out)
        data = np.interp(idx, np.arange(len(data)), data).astype(np.float32)
    return data


def _loop_to_length(samples: np.ndarray, total_ms: int, sample_rate: int) -> np.ndarray:
    """Repeat-tile then truncate to exactly total_ms worth of samples."""
    n_target = int(total_ms * sample_rate / 1000)
    if len(samples) == 0:
        return np.zeros(n_target, dtype=np.float32)
    reps = (n_target // len(samples)) + 1
    return np.tile(samples, reps)[:n_target].astype(np.float32, copy=False)


def _load_sfx_samples(name: str, sample_rate: int) -> np.ndarray:
    """Hard load — raises if missing (mirrors old _load_sfx)."""
    path = SFX_DIR / f"{name}.wav"
    return _load_wav(path, sample_rate)


def _load_sfx_samples_or_none(name: str, sample_rate: int):
    """Soft load — returns None if missing (mirrors old _load_sfx_or_none)."""
    path = SFX_DIR / f"{name}.wav"
    if not path.exists():
        return None
    return _load_wav(path, sample_rate)
```

- [ ] **Step 5.4: Run tests to verify pass**

Run: `pytest pixel_battle/tests/test_compose_helpers.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5.5: Commit**

```bash
git add pixel_battle/video/compose.py pixel_battle/tests/test_compose_helpers.py
git commit -m "feat(pixel-battle): compose helpers — _load_wav / _loop / _sfx_samples"
```

---

### Task 6: Rewrite `compose.py::build_audio_track`

**Files:**
- Modify: `pixel_battle/video/compose.py` (replace `build_audio_track` body)
- Modify: `pixel_battle/tests/test_compose.py` (adapt assertions to new internals)

- [ ] **Step 6.1: Read existing `test_compose.py` to understand current assertions**

Run: `cat pixel_battle/tests/test_compose.py`
Note: the test checks that `build_audio_track` produces a wav of expected duration. After rewrite the signature is identical, so most tests should still pass; some pydub-specific internal mocks may need updating.

- [ ] **Step 6.2: Rewrite `build_audio_track`**

In `pixel_battle/video/compose.py`, REPLACE the existing `build_audio_track` function with:

```python
def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str,
                      event_offset_ms: int = 0,
                      event_video_ms: dict | None = None) -> None:
    """Render BGM + SFX into a single wav via the AudioMixer bus pipeline.

    Signature preserved for backward compat with episode runner. Internally
    routes events to bgm/cast/hit/ult buses; cast bus enforces 2-slot
    overlap limit; final ffmpeg pass sidechain-ducks BGM and applies
    loudnorm I=-14 (TikTok target).
    """
    from pixel_battle.video.audio_mixer import AudioMixer

    mixer = AudioMixer(sample_rate=48000)

    # BGM bus
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm_samples = _load_wav(bgm_path, mixer.sr)
        bgm_looped = _loop_to_length(bgm_samples, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(bgm_looped, t_ms=0)

    for ev in events:
        # Same positioning rule as before
        if event_video_ms is not None and id(ev) in event_video_ms:
            pos = event_video_ms[id(ev)]
        else:
            pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue

        if ev.type is EventType.HIT:
            samp = _load_sfx_samples(
                "crit" if ev.extra.get("crit") else "hit", mixer.sr,
            )
            mixer.hit_bus.add(samp, pos)
        elif ev.type is EventType.ATTACK_WINDUP:
            st = ev.extra.get("skill_type", "") if ev.extra else ""
            samp = _load_sfx_samples_or_none(f"cast_{st}", mixer.sr)
            if samp is not None:
                mixer.cast_bus.add(samp, pos)
        elif ev.type is EventType.CRIT:
            mixer.hit_bus.add(_load_sfx_samples("crit", mixer.sr), pos)
        elif ev.type is EventType.ULTIMATE_START:
            charge_pos = max(0, pos - 600)
            charge = _load_sfx_samples_or_none("charge", mixer.sr)
            if charge is not None:
                mixer.ult_bus.add(charge, charge_pos)
            skill_id = ev.extra.get("skill_id", "") if ev.extra else ""
            ult = (_load_sfx_samples_or_none(skill_id, mixer.sr)
                   or _load_sfx_samples_or_none("ultimate", mixer.sr))
            if ult is not None:
                mixer.ult_bus.add(ult, pos)
        elif ev.type is EventType.KO:
            mixer.hit_bus.add(_load_sfx_samples("ko", mixer.sr), pos)

    mixer.export(total_duration_ms, output_path)
```

Also remove the now-unused `from pydub import AudioSegment` import and the old `_load_sfx` (keep `_load_sfx_or_none` if used elsewhere — grep first).

- [ ] **Step 6.3: Verify nothing else uses pydub**

Run: `grep -rn "pydub\|AudioSegment\|_load_sfx[^_]" pixel_battle/`
Expected: no remaining import or reference except within the helpers we removed. If anything else references pydub, fix it minimally to use the new helpers.

- [ ] **Step 6.4: Run compose-related tests**

Run: `pytest pixel_battle/tests/test_compose.py pixel_battle/tests/test_compose_helpers.py pixel_battle/tests/test_audio_video_ms_map.py -v`
Expected: all PASS. If `test_compose.py` had pydub-specific assertions, update them to use the new path (e.g., check output wav duration via ffprobe instead of pydub `len()`).

- [ ] **Step 6.5: Run full suite**

Run: `pytest pixel_battle/tests/ --ignore=pixel_battle/tests/test_renderer.py --deselect pixel_battle/tests/test_battle_ai_priority.py::test_ai_retreats_when_mp_high_and_close -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 6.6: Commit**

```bash
git add pixel_battle/video/compose.py pixel_battle/tests/test_compose.py
git commit -m "feat(pixel-battle): build_audio_track → AudioMixer bus pipeline"
```

---

### Task 7: BGM swap

**Files:**
- Replace: `pixel_battle/assets/bgm/battle_loop.mp3`

**Depends on:** the parallel BGM-hunt subagent task delivering candidates to `pixel_battle/assets/bgm_candidates/`. If candidates aren't ready, this task BLOCKS — surface as `BLOCKED` waiting for BGM hunt.

- [ ] **Step 7.1: Check candidate availability**

Run: `ls pixel_battle/assets/bgm_candidates/ 2>/dev/null && cat pixel_battle/assets/bgm_candidates/README.md 2>/dev/null | head -40`
Expected: at least one candidate + README with metadata. If empty, report `BLOCKED` to controller.

- [ ] **Step 7.2: Wait for user selection**

The controller (this skill's caller) presents candidates to the user and obtains a selection. The implementer of this task is told which file to use, e.g., `01_synthwave_drive.mp3`.

- [ ] **Step 7.3: Replace `battle_loop.mp3`**

Once the chosen file is `{candidate_filename}`:

```bash
cp pixel_battle/assets/bgm/battle_loop.mp3 pixel_battle/assets/bgm/battle_loop.mp3.bak
cp pixel_battle/assets/bgm_candidates/{candidate_filename} pixel_battle/assets/bgm/battle_loop.mp3
```

If the chosen candidate is `.wav` not `.mp3`, transcode first:

```bash
ffmpeg -y -i pixel_battle/assets/bgm_candidates/{candidate_filename} \
    -codec:a libmp3lame -q:a 2 pixel_battle/assets/bgm/battle_loop.mp3
```

- [ ] **Step 7.4: Verify**

Run: `ffprobe -v error -show_entries format=duration,size,bit_rate pixel_battle/assets/bgm/battle_loop.mp3`
Expected: duration > 30s, bit_rate >= 192k.

- [ ] **Step 7.5: Commit**

```bash
git add pixel_battle/assets/bgm/battle_loop.mp3
git commit -m "feat(pixel-battle): swap BGM to synthwave action track"
```

(The `.bak` file is not committed — local rollback only. Add to `.gitignore` if not already.)

---

### Task 8: Visual regression — regenerate `final.mp4`

**Files:** none modified; verification only.

- [ ] **Step 8.1: Regenerate match video**

Run: `SDL_VIDEODRIVER=dummy python -m pixel_battle.episodes.ep01_brick_vs_glass 2>&1 | tail -10`
Expected: `✅ Episode 1 produced: ... final.mp4`. Duration / outcome reported.

- [ ] **Step 8.2: Verify artifacts**

Run: `ls -la pixel_battle/output/ep01_brick_vs_glass/final.mp4 pixel_battle/output/ep01_brick_vs_glass/audio.wav`
Expected: both fresh.

- [ ] **Step 8.3: Measure audio loudness**

Run: `ffmpeg -i pixel_battle/output/ep01_brick_vs_glass/final.mp4 -af loudnorm=print_format=json -f null - 2>&1 | tail -20 | grep -E "input_i|output_i"`
Expected: `output_i` near -14 LUFS (±1).

- [ ] **Step 8.4: Spot-check cast SFX overlap reduction**

Run the same Python diagnostic script used in earlier session:

```bash
python -c "
import json
e = json.load(open('pixel_battle/output/ep01_brick_vs_glass/battle_events.json'))
casts = [x for x in e if x['type']=='attack_windup']
print(f'Total casts emitted: {len(casts)}')
print('Note: cast_bus 2-slot limiter will drop ~half. Check ffmpeg log or add a debug print in compose.py temporarily if exact count is needed.')
"
```

- [ ] **Step 8.5: Manual review checklist**

Open the new `final.mp4` and confirm subjectively:
- BGM is clearly synthwave/electronic (no longer ambient pad)
- BGM audibly **ducks down** at every hit/ult moment
- Cast SFX no longer feel like a continuous "wash" — there's air between them
- Hit SFX cuts through cleanly
- Overall loudness is louder than P5 (TikTok-friendly)

- [ ] **Step 8.6: No commit needed unless incidental fix landed**

If Step 8.1-8.5 surfaced an issue requiring a code change, fix and commit. Otherwise this task only verifies.

---

## Out of scope (do not implement)

- Stereo panning by character side (left/right)
- Multi-band compression beyond hi-pass + low-shelf
- VST3 plugin loading via pedalboard
- Backwards compatibility with pydub path (clean break)
- Real-time monitoring / live audio preview
- Refactoring `mux_audio_video` (it's fine)

## Tuning knobs

- Sample rate: `48000 Hz`
- BGM gain: `-12 dB`
- Cast bus: hi-pass `200 Hz`, gain `-8 dB`, limiter `-2 dB`, 2-slot
- Hit bus: low-shelf `+3 dB @ 120 Hz`, gain `0 dB`, limiter `-1 dB`
- Sidechain: threshold `0.1`, ratio `4`, attack `5 ms`, release `200 ms`
- loudnorm: `I=-14`, `LRA=11`, `TP=-1.5`
