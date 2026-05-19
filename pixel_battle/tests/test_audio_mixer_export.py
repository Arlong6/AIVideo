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


import subprocess

import numpy as np


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
