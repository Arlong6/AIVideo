"""One-shot script: generate ultimate-specific SFX files via numpy.

Run once:  python3 -m pixel_battle.scripts.gen_ult_sfx

Outputs:
  pixel_battle/assets/sfx/indestructible_throw.wav  — metallic clang (brick ult)
  pixel_battle/assets/sfx/force_update.wav          — glass shatter + error beep (glass ult)
"""
import struct
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
SFX_DIR = Path(__file__).resolve().parents[1] / "assets" / "sfx"


def _write_wav(path: Path, samples: np.ndarray) -> None:
    """Write mono 16-bit PCM WAV. samples should be float in [-1, 1]."""
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def _gen_indestructible_throw() -> np.ndarray:
    """Metallic clang: 880Hz triangle + noise burst + 600ms exponential decay."""
    duration = 0.6
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)

    # Triangle wave at 880Hz (metallic fundamental)
    tri = 2 * np.abs(2 * (t * 880 - np.floor(t * 880 + 0.5))) - 1

    # Noise burst at the front (first 80ms) for impact transient
    noise = np.random.uniform(-1, 1, n)
    noise_env = np.where(t < 0.08, 1.0 - t / 0.08, 0.0)

    # Exponential decay envelope for the triangle body
    body_env = np.exp(-t * 6.0)

    # Add a higher overtone for ring (1760Hz, 1/4 amplitude)
    overtone = 2 * np.abs(2 * (t * 1760 - np.floor(t * 1760 + 0.5))) - 1

    samples = (tri * 0.6 + overtone * 0.2) * body_env + noise * noise_env * 0.4
    return samples


def _gen_force_update() -> np.ndarray:
    """Glass shatter + downward sweep + 3-pulse error beep. 0.8s total."""
    duration = 0.8
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)

    # Glass shatter: white noise burst for first 120ms with sharp attack
    shatter = np.random.uniform(-1, 1, n)
    shatter_env = np.where(t < 0.12, (1.0 - t / 0.12) ** 1.5, 0.0)

    # Downward chirp 1500Hz → 200Hz over 200-450ms window
    sweep_start, sweep_end = 0.20, 0.45
    freq = np.where(
        (t >= sweep_start) & (t < sweep_end),
        1500 - (1500 - 200) * (t - sweep_start) / (sweep_end - sweep_start),
        0,
    )
    sweep_phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    sweep = np.sin(sweep_phase)
    sweep_env = np.where((t >= sweep_start) & (t < sweep_end), 1.0, 0.0)

    # 3-pulse error beep at 0.5s, 0.6s, 0.7s — square wave at 660Hz
    beep = np.zeros(n)
    for pulse_t in [0.50, 0.60, 0.70]:
        mask = (t >= pulse_t) & (t < pulse_t + 0.05)
        square = np.sign(np.sin(2 * np.pi * 660 * t))
        beep += np.where(mask, square, 0.0)

    samples = shatter * shatter_env * 0.5 + sweep * sweep_env * 0.35 + beep * 0.25
    return samples


def _gen_summon() -> np.ndarray:
    """Deep SUMMONING rumble for summoner ultimates: a rising sub-bass swell +
    a building low 'earth-tearing' noise rush + a low boom as the summon lands.
    All low-frequency content (no ringing high tones). ~1.0s."""
    duration = 1.0
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Rising sub-bass 45→90Hz over the first 700ms (the summon wells up)
    f0 = 45 + (90 - 45) * np.clip(t / 0.7, 0, 1)
    phase = 2 * np.pi * np.cumsum(f0) / SAMPLE_RATE
    sub = np.sin(phase)
    sub2 = np.sin(phase * 2) * 0.4                       # an octave up for body
    sub_env = np.clip(t / 0.25, 0, 1) * np.exp(-np.clip(t - 0.7, 0, None) * 3.0)
    # Building low-passed noise rush
    noise = np.random.uniform(-1, 1, n)
    noise_lp = np.convolve(noise, np.ones(140) / 140, mode="same")   # heavy low-pass = rumble
    rush_env = (np.clip(t / 0.7, 0, 1) ** 2) * np.where(t < 0.78, 1.0, np.exp(-(t - 0.78) * 6))
    # Low boom impact at ~0.70s (the summon lands)
    boom = np.sin(2 * np.pi * 60 * t)
    boom_env = np.where(t >= 0.70, np.exp(-(t - 0.70) * 7.0), 0.0)
    boom_noise = noise * np.where((t >= 0.70) & (t < 0.78), 1.0, 0.0) * 0.5
    samples = ((sub + sub2) * sub_env * 0.55
               + noise_lp * rush_env * 0.30
               + (boom + boom_noise) * boom_env * 0.5)
    return np.tanh(samples * 1.2)                        # soft clip for glue


def main() -> None:
    np.random.seed(42)  # deterministic for re-runs
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "indestructible_throw.wav", _gen_indestructible_throw())
    _write_wav(SFX_DIR / "force_update.wav", _gen_force_update())
    _write_wav(SFX_DIR / "summon.wav", _gen_summon())
    print(f"Generated SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
