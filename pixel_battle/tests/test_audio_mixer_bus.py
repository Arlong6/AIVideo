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
