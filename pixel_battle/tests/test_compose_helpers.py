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
