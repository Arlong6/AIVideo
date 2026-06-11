"""One-shot script: regenerate the IMPACT family of SFX via numpy.

Replaces the brick-phone-era pydub WhiteNoise sounds (hit/crit/ko/charge)
with layered fighting-game impacts: a sub THUMP body + a band-passed snap
transient + a short airy tail. All energy lives low/mid — no ringing sine
tones (ear-safe).

Run once:  python3 -m pixel_battle.scripts.gen_hit_sfx
"""
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
SFX_DIR = Path(__file__).resolve().parents[1] / "assets" / "sfx"


def _write_wav(path: Path, samples: np.ndarray) -> None:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def _t(duration: float):
    n = int(SAMPLE_RATE * duration)
    return np.linspace(0, duration, n, endpoint=False), n


def _lp_noise(n: int, kernel: int) -> np.ndarray:
    """Low-passed white noise (moving average) — soft 'air', no hiss."""
    x = np.random.uniform(-1, 1, n)
    return np.convolve(x, np.ones(kernel) / kernel, mode="same")


def _bp_snap(t: np.ndarray, centre: float, decay: float) -> np.ndarray:
    """Band-passed knock transient: noise ring-modulated around `centre` Hz."""
    n = len(t)
    body = _lp_noise(n, 24) * np.cos(2 * np.pi * centre * t)
    return body * np.exp(-t * decay)


def _thump(t: np.ndarray, f0: float, f1: float, decay: float) -> np.ndarray:
    """Pitch-dropping sine body — the classic impact 'boom' (f0 → f1)."""
    k = np.exp(-t * 14.0)
    freq = f1 + (f0 - f1) * k                       # fast drop f0 → f1
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    return np.sin(phase) * np.exp(-t * decay)


def gen_hit() -> np.ndarray:
    """Quick body blow: 110→55Hz thump + 900Hz knuckle snap. ~110ms."""
    t, n = _t(0.11)
    s = (_thump(t, 110, 55, 26) * 0.85
         + _bp_snap(t, 900, 60) * 0.55
         + _lp_noise(n, 8) * np.exp(-t * 70) * 0.25)
    return np.tanh(s * 1.6) * 0.9


def gen_crit() -> np.ndarray:
    """Heavy crit: deeper 90→42Hz boom, double snap, longer push. ~240ms."""
    t, n = _t(0.24)
    snap2 = np.zeros(n)                              # second knock 35ms later
    off = int(0.035 * SAMPLE_RATE)
    base = _bp_snap(t, 700, 48)
    snap2[off:] = base[:-off] * 0.6
    s = (_thump(t, 90, 42, 13) * 1.0
         + _bp_snap(t, 1100, 55) * 0.5 + snap2
         + _lp_noise(n, 10) * np.exp(-t * 30) * 0.3)
    return np.tanh(s * 1.7) * 0.95


def gen_ko() -> np.ndarray:
    """Finisher: long sub drop 100→32Hz + slam + rumbling settle. ~0.8s."""
    t, n = _t(0.8)
    drop_k = np.clip(t / 0.25, 0, 1)
    freq = 100 - (100 - 32) * drop_k
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sub = np.sin(phase) * np.exp(-t * 4.5)
    s = (sub * 1.0
         + _bp_snap(t, 600, 30) * 0.7
         + _lp_noise(n, 60) * np.exp(-t * 6) * 0.5)
    return np.tanh(s * 1.5) * 0.95


def gen_charge() -> np.ndarray:
    """Beam-windup riser: low-passed noise swell + rising 70→160Hz hum. ~0.7s."""
    t, n = _t(0.7)
    swell = np.clip(t / 0.6, 0, 1) ** 2
    freq = 70 + (160 - 70) * np.clip(t / 0.7, 0, 1)
    phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    hum = np.sin(phase) * 0.5 + np.sin(phase * 2) * 0.2
    s = (_lp_noise(n, 30) * swell * 0.6 + hum * swell * 0.6)
    fade = np.where(t > 0.62, np.exp(-(t - 0.62) * 25), 1.0)   # snap off at release
    return np.tanh(s * 1.4) * 0.85 * fade


def main() -> None:
    np.random.seed(11)
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "hit.wav", gen_hit())
    _write_wav(SFX_DIR / "crit.wav", gen_crit())
    _write_wav(SFX_DIR / "ko.wav", gen_ko())
    _write_wav(SFX_DIR / "charge.wav", gen_charge())
    print(f"Generated impact SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
