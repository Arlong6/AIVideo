"""One-shot script: KOF-style SUPER-MOVE ultimate audio via numpy.

Fighting-game supers sell the moment with a three-beat audio arc:
  1. ult_flash.wav — the ACTIVATION stab: an orchestra-hit style minor-chord
     "DUN!" + sub thump (the screen-freeze moment, a la KOF/SF super flash)
  2. ult_riser.wav — 1.5s tension build under the anticipation freeze:
     rising noise sweep + accelerating pulse, cut dead at release
  3. ult_blast.wav — the payoff: layered explosion — crack, long sub DROP,
     mid crunch, sparkle-dust shimmer tail, delayed echo punch

Routed in play.py: flash+riser at ultimate_start, blast at +ANTICIPATION_MS
(summoner ults swap the blast for the summon rumble landing instead).

Run once:  python3 -m pixel_battle.scripts.gen_ult_blast_sfx
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
    x = np.random.uniform(-1, 1, n)
    return np.convolve(x, np.ones(kernel) / kernel, mode="same")


def _band(t, centre, kernel):
    n = len(t)
    soft = _lp_noise(n, kernel)
    if np.isscalar(centre):
        return soft * np.cos(2 * np.pi * centre * t)
    phase = 2 * np.pi * np.cumsum(centre) / SAMPLE_RATE
    return soft * np.cos(phase)


def gen_ult_flash() -> np.ndarray:
    """Orchestra-hit activation stab: Am chord brass-stack + crash + sub thump."""
    t, n = _t(0.75)
    chord = np.zeros(n)
    for f0, a in ((110, 0.30), (165, 0.24), (220, 0.22), (262, 0.16), (330, 0.12)):
        tone = (np.sin(2 * np.pi * f0 * t)
                + 0.45 * np.sin(2 * np.pi * f0 * 2 * t)
                + 0.20 * np.sin(2 * np.pi * f0 * 3 * t))      # brassy harmonics
        chord += tone * a
    chord *= np.exp(-t * 5.5)                                  # sharp stab decay
    crash = _band(t, 2200, 8) * np.exp(-t * 16) * 0.4          # cymbal-ish crash
    sub = np.sin(2 * np.pi * 62 * t) * np.exp(-t * 9) * 0.9    # weight under it
    s = chord + crash + sub
    return np.tanh(s * 1.5) * 0.92


def gen_ult_riser() -> np.ndarray:
    """1.5s anticipation build: noise sweep up + accelerating pulse, hard cut."""
    t, n = _t(1.5)
    prog = np.clip(t / 1.5, 0, 1)
    sweep = _band(t, 300 + 2700 * prog ** 1.6, 18) * (0.25 + 0.75 * prog)
    # accelerating heartbeat pulse (rate 4 → 14 Hz)
    pulse_phase = 2 * np.pi * np.cumsum(4 + 10 * prog) / SAMPLE_RATE
    pulse = np.maximum(0, np.sin(pulse_phase)) ** 6
    thump = np.sin(2 * np.pi * 70 * t) * pulse * (0.3 + 0.5 * prog)
    rise_tone = np.sin(2 * np.pi * np.cumsum(90 + 240 * prog) / SAMPLE_RATE)
    s = sweep * 0.55 + thump + rise_tone * 0.16 * prog
    s *= np.where(t > 1.46, np.exp(-(t - 1.46) * 90), 1.0)     # cut dead at release
    return np.tanh(s * 1.5) * 0.8


def gen_ult_blast() -> np.ndarray:
    """The payoff explosion: crack + long sub DROP + crunch + shimmer + echo."""
    t, n = _t(1.4)
    crack = np.random.uniform(-1, 1, n) * np.where(t < 0.007, 1.0, 0.0)
    drop_f = 30 + (105 - 30) * np.exp(-t * 9)                  # 105 → 30Hz drop
    sub = np.sin(2 * np.pi * np.cumsum(drop_f) / SAMPLE_RATE) * np.exp(-t * 2.6)
    crunch = _band(t, 420, 26) * np.exp(-t * 7.5)              # body debris
    shimmer = _band(t, 2600, 8) * np.exp(-t * 3.8) * 0.30      # dust sparkle tail
    echo = np.zeros(n)                                         # delayed second punch
    off = int(0.18 * SAMPLE_RATE)
    echo[off:] = (np.sin(2 * np.pi * 55 * t) * np.exp(-t * 11))[:-off] * 0.55
    s = crack * 0.95 + sub * 1.05 + crunch * 0.6 + shimmer + echo
    return np.tanh(s * 1.45) * 0.95


def main() -> None:
    np.random.seed(17)
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "ult_flash.wav", gen_ult_flash())
    _write_wav(SFX_DIR / "ult_riser.wav", gen_ult_riser())
    _write_wav(SFX_DIR / "ult_blast.wav", gen_ult_blast())
    print(f"Generated super-move ultimate SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
