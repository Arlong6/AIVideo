"""One-shot script: CLASSIC weapon-family combat SFX via numpy.

Every attack used to share one punch-thud. This adds the recognisable genre
sounds — sword clash, spell shimmer, bow twang, gunshot crack — routed by the
attacker's weapon family in play.py. All transients are SHORT and mid-band
weighted (no sustained pure tones — ear-safe).

Run once:  python3 -m pixel_battle.scripts.gen_combat_sfx

Outputs (assets/sfx/):
  sword_swing.wav  — air-cutting whoosh (any melee windup)
  sword_hit.wav    — metallic CLASH, inharmonic ring (blade connects)
  magic_cast.wav   — rising shimmer + soft sparkle arpeggio (staff windup)
  magic_hit.wav    — arcane impact: thump + crystalline burst
  bow_shot.wav     — string TWANG pluck + arrow whoosh (bow windup)
  arrow_hit.wav    — short wooden THUNK (arrow connects)
  gun_shot.wav     — crack + low boom (gun windup/fire)
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


def _noise_band(t: np.ndarray, centre, width_kernel: int) -> np.ndarray:
    """Noise shifted around a (possibly time-varying) centre frequency."""
    n = len(t)
    base = np.random.uniform(-1, 1, n)
    soft = np.convolve(base, np.ones(width_kernel) / width_kernel, mode="same")
    if np.isscalar(centre):
        carrier = np.cos(2 * np.pi * centre * t)
    else:
        phase = 2 * np.pi * np.cumsum(centre) / SAMPLE_RATE
        carrier = np.cos(phase)
    return soft * carrier


def gen_sword_swing() -> np.ndarray:
    """Air-cutting whoosh: noise band sweeping 1400→450Hz, swell-and-release."""
    t, n = _t(0.18)
    centre = 1400 - (1400 - 450) * np.clip(t / 0.18, 0, 1)
    env = np.sin(np.pi * np.clip(t / 0.18, 0, 1)) ** 1.6      # swell mid-swing
    s = _noise_band(t, centre, 14) * env
    return np.tanh(s * 2.2) * 0.7


def gen_sword_hit() -> np.ndarray:
    """Metallic CLASH: bright noise transient + 3 inharmonic ring modes + knock.
    Ring decays fast (~140ms) so it bites without lingering."""
    t, n = _t(0.16)
    click = np.random.uniform(-1, 1, n) * np.exp(-t * 160)     # steel contact
    ring = np.zeros(n)
    for f0, a in ((1730, 0.16), (2390, 0.13), (3170, 0.09)):   # inharmonic partials
        ring += np.sin(2 * np.pi * f0 * t) * a
    ring *= np.exp(-t * 26)
    knock = np.sin(2 * np.pi * 210 * t) * np.exp(-t * 50)      # body of the blow
    s = click * 0.7 + ring + knock * 0.5
    return np.tanh(s * 1.6) * 0.85


def gen_magic_cast() -> np.ndarray:
    """Spell shimmer: noise sweeping UP 500→2600Hz + soft sparkle arpeggio."""
    t, n = _t(0.32)
    centre = 500 + (2600 - 500) * np.clip(t / 0.3, 0, 1)
    sweep = _noise_band(t, centre, 20) * np.sin(np.pi * np.clip(t / 0.32, 0, 1))
    sparkle = np.zeros(n)
    for k, f0 in enumerate((880, 1175, 1568)):                 # A5-D6-G6 soft blips
        t0 = 0.06 + k * 0.07
        seg = (t >= t0) & (t < t0 + 0.05)
        env = np.where(seg, np.sin(np.pi * (t - t0) / 0.05), 0.0)   # soft in-out
        sparkle += np.sin(2 * np.pi * f0 * t) * env * 0.16
    s = sweep * 0.55 + sparkle
    return np.tanh(s * 1.8) * 0.7


def gen_magic_hit() -> np.ndarray:
    """Arcane impact: 80Hz thump + crystalline high-band burst (~120ms)."""
    t, n = _t(0.2)
    thump = np.sin(2 * np.pi * 80 * t) * np.exp(-t * 24)
    burst = _noise_band(t, 2900, 10) * np.exp(-t * 30)
    chime = (np.sin(2 * np.pi * 1568 * t) * 0.12
             + np.sin(2 * np.pi * 2093 * t) * 0.09) * np.exp(-t * 22)
    s = thump * 0.9 + burst * 0.5 + chime
    return np.tanh(s * 1.6) * 0.8


def gen_bow_shot() -> np.ndarray:
    """String TWANG: plucked 290Hz with fast-decaying harmonics + release whoosh."""
    t, n = _t(0.22)
    pluck = np.zeros(n)
    for h, a in ((1, 0.5), (2, 0.28), (3, 0.16), (4, 0.08)):
        pluck += np.sin(2 * np.pi * 290 * h * t) * a * np.exp(-t * (14 + h * 16))
    click = np.random.uniform(-1, 1, n) * np.exp(-t * 220) * 0.5    # release snap
    whoosh = _noise_band(t, 900 - 500 * np.clip(t / 0.2, 0, 1), 16) \
        * np.where(t > 0.03, np.exp(-(t - 0.03) * 14), 0.0) * 0.4   # arrow leaves
    s = pluck + click + whoosh
    return np.tanh(s * 1.7) * 0.8


def gen_arrow_hit() -> np.ndarray:
    """Short wooden THUNK — 150Hz knock + brief fibrous noise (~90ms)."""
    t, n = _t(0.09)
    knock = np.sin(2 * np.pi * 150 * t) * np.exp(-t * 45)
    fibre = _noise_band(t, 700, 12) * np.exp(-t * 70)
    s = knock * 1.0 + fibre * 0.45
    return np.tanh(s * 1.8) * 0.85


def gen_gun_shot() -> np.ndarray:
    """Revolver crack: 8ms full-band snap + 400Hz bark + 75Hz boom tail."""
    t, n = _t(0.24)
    crack = np.random.uniform(-1, 1, n) * np.where(t < 0.008, 1.0, 0.0)
    bark = _noise_band(t, 420, 8) * np.exp(-t * 38)
    boom = np.sin(2 * np.pi * 75 * t) * np.exp(-t * 16)
    s = crack * 0.9 + bark * 0.55 + boom * 0.8
    return np.tanh(s * 1.6) * 0.9


def main() -> None:
    np.random.seed(13)
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "sword_swing.wav", gen_sword_swing())
    _write_wav(SFX_DIR / "sword_hit.wav", gen_sword_hit())
    _write_wav(SFX_DIR / "magic_cast.wav", gen_magic_cast())
    _write_wav(SFX_DIR / "magic_hit.wav", gen_magic_hit())
    _write_wav(SFX_DIR / "bow_shot.wav", gen_bow_shot())
    _write_wav(SFX_DIR / "arrow_hit.wav", gen_arrow_hit())
    _write_wav(SFX_DIR / "gun_shot.wav", gen_gun_shot())
    print(f"Generated classic combat SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
