# Pixel Battle — Audio Mixer Overhaul (pedalboard + ffmpeg sidechain)

**Date**: 2026-05-19
**Status**: Approved
**Trigger**: P5 final.mp4 — user reports "音效還是沒有對齊 / 越來越歪". Diagnostic showed: per-event timing is correct (mean +29ms drift, total length matches within 4ms); the real problem is **68 cast SFX in 60s overlapping continuously** (3-5 concurrent at any moment), drowning the 13 actual hit SFX. Current pydub `.overlay()` has no concept of buses / ducking / overlap limits.

## Goal

Replace the flat-overlay audio pipeline with a **bus-based mixer** so individual events stay legible:

1. **Bus structure**: BGM / cast / hit / ult — each rendered with independent gain + EQ + limiter via `pedalboard`.
2. **Sidechain ducking**: HitBus + UltBus combined as a sidechain trigger → BGM ducks -10dB on every real impact.
3. **Overlap cap**: CastBus enforces a 2-slot SlotLimiter — 3rd+ concurrent cast SFX is skipped.
4. **Mastering**: Final mix `loudnorm=I=-14 LUFS` for TikTok/Shorts targeting.
5. **BGM swap**: Replace ambient `battle_loop.mp3` with a synthwave/electronic-action track.

## Three blocks

### A. New module: `pixel_battle/video/audio_mixer.py`

Three classes:

**A1. `SlotLimiter`**

Tracks active sound windows on a bus. `can_add(t_ms, duration_ms)` returns `False` if `max_concurrent` slots are already active at `t_ms`.

```python
class SlotLimiter:
    def __init__(self, max_concurrent: int):
        self.max = max_concurrent
        self.windows: list[tuple[int, int]] = []  # [(start_ms, end_ms)]

    def can_add(self, t_ms: int, duration_ms: int) -> bool:
        # Prune expired windows
        self.windows = [(s, e) for s, e in self.windows if e > t_ms]
        active = sum(1 for s, e in self.windows if s <= t_ms < e)
        if active >= self.max:
            return False
        self.windows.append((t_ms, t_ms + duration_ms))
        return True
```

**A2. `Bus`**

A bus owns a per-bus pedalboard chain (gain + optional EQ + limiter) and a list of `(sample, t_ms)` placements. Renders to a numpy array of the full track length, then applies the chain.

```python
from dataclasses import dataclass, field
import numpy as np
from pedalboard import Pedalboard

@dataclass
class Bus:
    name: str
    sample_rate: int
    chain: Pedalboard
    placements: list[tuple[np.ndarray, int]] = field(default_factory=list)
    limiter: SlotLimiter | None = None

    def add(self, samples: np.ndarray, t_ms: int) -> bool:
        """Returns True if placed, False if rejected by limiter."""
        dur_ms = int(len(samples) * 1000 / self.sample_rate)
        if self.limiter and not self.limiter.can_add(t_ms, dur_ms):
            return False
        self.placements.append((samples, t_ms))
        return True

    def render(self, total_ms: int) -> np.ndarray:
        n_samples = int(total_ms * self.sample_rate / 1000)
        track = np.zeros(n_samples, dtype=np.float32)
        for samp, t_ms in self.placements:
            start = int(t_ms * self.sample_rate / 1000)
            end = min(start + len(samp), n_samples)
            track[start:end] += samp[: end - start]
        return self.chain(track, self.sample_rate)
```

**A3. `AudioMixer`**

Owns the four buses, the BGM track, and exports the final WAV after final ffmpeg sidechain pass.

```python
class AudioMixer:
    def __init__(self, sample_rate: int = 48000):
        self.sr = sample_rate
        self.bgm_bus = Bus(name="bgm", sample_rate=sample_rate,
                           chain=Pedalboard([Gain(gain_db=-12)]))
        self.cast_bus = Bus(name="cast", sample_rate=sample_rate,
                            chain=Pedalboard([
                                HighpassFilter(cutoff_frequency_hz=200),
                                Gain(gain_db=-8),
                                Limiter(threshold_db=-2.0, release_ms=80),
                            ]),
                            limiter=SlotLimiter(max_concurrent=2))
        self.hit_bus = Bus(name="hit", sample_rate=sample_rate,
                           chain=Pedalboard([
                               LowShelfFilter(cutoff_frequency_hz=120, gain_db=+3),
                               Gain(gain_db=0),
                               Limiter(threshold_db=-1.0, release_ms=50),
                           ]))
        self.ult_bus = Bus(name="ult", sample_rate=sample_rate,
                           chain=Pedalboard([
                               Gain(gain_db=0),
                               Limiter(threshold_db=-1.0, release_ms=100),
                           ]))

    def export(self, total_ms: int, output_path: str) -> None:
        # Step 1: render each bus to its own wav file
        bus_wavs = {}
        for bus in (self.bgm_bus, self.cast_bus, self.hit_bus, self.ult_bus):
            wav = bus.render(total_ms)
            path = f"/tmp/_mix_{bus.name}.wav"
            sf.write(path, wav, self.sr)
            bus_wavs[bus.name] = path

        # Step 2: ffmpeg filter_complex — sidechain duck BGM by (hit+ult), then mix all + loudnorm
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", bus_wavs["bgm"],
            "-i", bus_wavs["cast"],
            "-i", bus_wavs["hit"],
            "-i", bus_wavs["ult"],
            "-filter_complex",
            "[2:a][3:a]amix=inputs=2:duration=longest:normalize=0[trig];"
            "[0:a][trig]sidechaincompress=threshold=0.1:ratio=4:attack=5:release=200[bgm_ducked];"
            "[bgm_ducked][1:a][2:a][3:a]amix=inputs=4:duration=longest:normalize=0[mixed];"
            "[mixed]loudnorm=I=-14:LRA=11:TP=-1.5[out]",
            "-map", "[out]",
            output_path,
        ]
        subprocess.run(cmd, check=True)
```

### B. Rewrite `compose.py::build_audio_track`

Keep public signature identical (backward-compatible with episode runner). Internally route events to buses:

```python
def build_audio_track(events, total_duration_ms, output_path,
                      event_offset_ms=0, event_video_ms=None) -> None:
    mixer = AudioMixer()

    # BGM: load synthwave track, loop to total duration
    bgm_path = BGM_DIR / "battle_loop.mp3"  # will be the new synthwave file
    if bgm_path.exists():
        bgm_samples = _load_wav(bgm_path, target_sr=mixer.sr)
        bgm_looped = _loop_to_length(bgm_samples, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(bgm_looped, t_ms=0)

    # Route events
    for ev in events:
        pos = event_video_ms[id(ev)] if event_video_ms and id(ev) in event_video_ms \
            else ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue

        if ev.type is EventType.ATTACK_WINDUP:
            st = ev.extra.get("skill_type", "")
            samp = _load_sfx_samples_or_none(f"cast_{st}", mixer.sr)
            if samp is not None:
                mixer.cast_bus.add(samp, pos)

        elif ev.type is EventType.HIT:
            sfx = _load_sfx_samples("crit" if ev.extra.get("crit") else "hit", mixer.sr)
            mixer.hit_bus.add(sfx, pos)

        elif ev.type is EventType.CRIT:
            mixer.hit_bus.add(_load_sfx_samples("crit", mixer.sr), pos)

        elif ev.type is EventType.ULTIMATE_START:
            charge = _load_sfx_samples_or_none("charge", mixer.sr)
            if charge is not None:
                mixer.ult_bus.add(charge, max(0, pos - 600))
            skill_id = ev.extra.get("skill_id", "")
            ult = _load_sfx_samples_or_none(skill_id, mixer.sr) or \
                  _load_sfx_samples_or_none("ultimate", mixer.sr)
            if ult is not None:
                mixer.ult_bus.add(ult, pos)

        elif ev.type is EventType.KO:
            mixer.hit_bus.add(_load_sfx_samples("ko", mixer.sr), pos)

    mixer.export(total_duration_ms, output_path)
```

Helper functions:
- `_load_wav(path, target_sr)` — load via soundfile, resample if needed
- `_loop_to_length(samples, total_ms, sr)` — np.tile loop, truncate to length
- `_load_sfx_samples(name, sr)` / `_load_sfx_samples_or_none(name, sr)` — replace existing pydub-based loaders

### C. BGM swap

Replace `assets/bgm/battle_loop.mp3` with synthwave track from candidate pool (separate task — running parallel in background). New file lands at the same path so no episode-runner change needed.

## Architecture

Three sets of edits:
- `pixel_battle/video/audio_mixer.py` — NEW, contains `SlotLimiter`, `Bus`, `AudioMixer`
- `pixel_battle/video/compose.py` — rewrite `build_audio_track` body; keep signature; `mux_audio_video` unchanged
- `pixel_battle/assets/bgm/battle_loop.mp3` — replaced with synthwave track

## Error handling

- Missing SFX files: `_load_sfx_samples_or_none` returns None, event skipped (current behavior)
- BGM missing: skip BGM bus (current behavior)
- `SlotLimiter.can_add` rejection: silently drop event from cast bus (counts logged at end for visibility)
- ffmpeg failure: `subprocess.CalledProcessError` propagates with full ffmpeg stderr
- Numpy/pedalboard always uses float32 to avoid clipping in intermediate stages

## Testing

### Unit tests (new)

- `tests/test_audio_mixer_slot_limiter.py`:
  - Fresh limiter accepts up to `max_concurrent` events
  - Rejects the (max+1)th overlapping
  - Accepts new event after previous windows expire
  - Independent windows (non-overlapping) all accepted

- `tests/test_audio_mixer_bus.py`:
  - `Bus.add` returns True when limiter absent
  - `Bus.add` returns False when limiter rejects
  - `Bus.render(total_ms)` produces array of correct length
  - Multiple placements sum into the track

- `tests/test_audio_mixer_export.py`:
  - End-to-end: build mixer with stub samples, call `export`, verify output wav exists, duration matches `total_ms` ±50ms, peak amplitude ≤ -1.5 dBTP (loudnorm contract)

### Integration

- `tests/test_compose.py` — adapt existing test to new internals; signature unchanged
- `tests/test_audio_video_ms_map.py` — should still pass without modification (the map contract is preserved)

### Visual regression

Re-run `python -m pixel_battle.episodes.ep01_brick_vs_glass`. Confirm:
- Cast SFX no longer blanket-overlaps (audible "space" between casts)
- Hit SFX cuts through (ducked BGM on impact)
- BGM noticeably more energetic (synthwave swap)
- Final audio loudness near -14 LUFS (measure via `ffprobe -of json -show_streams ...` or `ffmpeg -af loudnorm=print_format=json`)

## Implementation order

1. **A1 SlotLimiter** — pure logic, TDD
2. **A2 Bus** — pedalboard wiring + render, TDD
3. **A3 AudioMixer skeleton** — instantiate buses, expose `export` (ffmpeg call mocked at first for unit test)
4. **A3 export integration** — real ffmpeg call, smoke test with stub samples
5. **B rewrite compose.py** — route events to buses, keep signature
6. **C BGM swap** — drop in chosen synthwave track
7. **Visual regression** — regenerate final.mp4

## Out of scope

- Multi-band compression / EQ tweaks beyond hi-pass + low-shelf
- Stereo positioning (panning by character side) — interesting but defer
- Dynamic ranging / loudness measurement (rely on loudnorm contract)
- VST3 plugin loading — pure pedalboard built-ins are enough

## Tuning knobs

- BGM gain: `-12dB` (was `-18` in pydub path, raised to fit ducked envelope)
- Cast bus: hi-pass `200Hz`, gain `-8dB`, 2-slot limiter
- Hit bus: low-shelf `+3dB @ 120Hz`, gain `0dB`
- Sidechain: threshold `0.1`, ratio `4`, attack `5ms`, release `200ms` (snappy duck, smooth recovery)
- Master loudnorm: `I=-14, LRA=11, TP=-1.5` (TikTok-friendly)
- Sample rate: `48000 Hz` (matches video frame multiples cleanly)
