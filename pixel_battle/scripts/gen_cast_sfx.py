"""One-shot: generate cast SFX files via numpy.

Run once:  python3 -m pixel_battle.scripts.gen_cast_sfx

Outputs:
  pixel_battle/assets/sfx/cast_cooldown.wav  — short 'tssht' for CD skills (~0.25s)
  pixel_battle/assets/sfx/cast_special.wav   — bright 'zwoom' for specials (~0.35s)
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


def _gen_cast_cooldown() -> np.ndarray:
    """Short 'tssht!' — 220Hz triangle + white noise hiss, 250ms with sharp decay."""
    duration = 0.25
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # 220Hz triangle (low rumble), fast decay
    tri = 2 * np.abs(2 * (t * 220 - np.floor(t * 220 + 0.5))) - 1
    body_env = np.exp(-t * 12.0)
    # White noise hiss, faster decay
    hiss = np.random.uniform(-1, 1, n)
    hiss_env = np.exp(-t * 20.0)
    samples = tri * 0.45 * body_env + hiss * 0.35 * hiss_env
    return samples


def _gen_cast_special() -> np.ndarray:
    """Bright 'zwoom!' — 400→1200Hz chirp UP + 1760Hz bell, 350ms."""
    duration = 0.35
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Upward chirp 400→1200Hz over first 150ms
    chirp_start, chirp_end = 0.00, 0.15
    freq = np.where(
        (t >= chirp_start) & (t < chirp_end),
        400 + (1200 - 400) * (t - chirp_start) / (chirp_end - chirp_start),
        0,
    )
    chirp_phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    chirp = np.sin(chirp_phase)
    chirp_env = np.where((t >= chirp_start) & (t < chirp_end), 1.0, 0.0)
    # 1760Hz bell tone after chirp, with exponential decay
    bell = np.sin(2 * np.pi * 1760 * t)
    bell_env = np.where(t >= 0.10, np.exp(-(t - 0.10) * 8.0), 0.0)
    samples = chirp * 0.50 * chirp_env + bell * 0.35 * bell_env
    return samples


def main() -> None:
    np.random.seed(7)
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "cast_cooldown.wav", _gen_cast_cooldown())
    _write_wav(SFX_DIR / "cast_special.wav", _gen_cast_special())
    print(f"Generated cast SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
