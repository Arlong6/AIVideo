"""Synthesize fighting-game-style SFX using pydub. Run once to regenerate assets."""
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine, Square, WhiteNoise

SFX_DIR = Path(__file__).resolve().parents[1] / "assets" / "sfx"
BGM_DIR = Path(__file__).resolve().parents[1] / "assets" / "bgm"


def hit_sfx() -> AudioSegment:
    """Light punch impact: sharp noise burst + low thud."""
    noise = WhiteNoise().to_audio_segment(duration=70, volume=-8)
    thud = Sine(140).to_audio_segment(duration=160, volume=-4)
    return noise.overlay(thud).fade_in(2).fade_out(120)


def crit_sfx() -> AudioSegment:
    """Heavy crit: longer noise + sub-bass + high-frequency ring."""
    noise = WhiteNoise().to_audio_segment(duration=120, volume=-5)
    thud = Sine(80).to_audio_segment(duration=300, volume=-2)
    ring = Sine(880).to_audio_segment(duration=200, volume=-10).overlay(
        Sine(1320).to_audio_segment(duration=200, volume=-12))
    base = noise.overlay(thud)
    base = base.overlay(ring, position=20)
    return base.fade_in(2).fade_out(200)


def ultimate_sfx() -> AudioSegment:
    """Massive boom: sub-bass + noise burst + chord."""
    subbass = Sine(60).to_audio_segment(duration=800, volume=-2)
    noise = WhiteNoise().to_audio_segment(duration=300, volume=-6)
    chord = (Sine(440).to_audio_segment(duration=600, volume=-10)
             .overlay(Sine(330).to_audio_segment(duration=600, volume=-10))
             .overlay(Sine(550).to_audio_segment(duration=600, volume=-12)))
    base = subbass.overlay(noise)
    base = base.overlay(chord, position=50)
    return base.fade_in(5).fade_out(500)


def ko_sfx() -> AudioSegment:
    """Game-over jingle: descending sweep + crash + dark chord."""
    sweep = AudioSegment.silent(duration=0)
    for i in range(20):
        f = 800 - i * 35
        seg = Sine(f).to_audio_segment(duration=60, volume=-8)
        sweep += seg
    crash = WhiteNoise().to_audio_segment(duration=400, volume=-10)
    chord = (Sine(220).to_audio_segment(duration=1000, volume=-6)
             .overlay(Sine(165).to_audio_segment(duration=1000, volume=-8)))
    base = chord.overlay(crash)
    base = base.overlay(sweep)
    return base.fade_in(2).fade_out(600)


def charge_sfx() -> AudioSegment:
    """Power-up build-up: ascending tone over 600ms."""
    charge = AudioSegment.silent(duration=0)
    for i in range(30):
        f = 200 + i * 25  # 200 → 925 Hz
        seg = Sine(f).to_audio_segment(duration=20, volume=-12)
        charge += seg
    return charge.fade_in(10).fade_out(80)


def bgm_loop() -> AudioSegment:
    """Simple chiptune-style fighting loop: bass kicks + square-wave lead arpeggio."""
    bar_ms = 2000  # 120 BPM, 4 beats per bar
    bars = []
    lead_freqs = [440, 523, 659, 440]  # A C E A
    for _bar in range(4):  # 4 bars = 8s
        kick = Sine(80).to_audio_segment(duration=120, volume=-4).fade_out(100)
        bar_audio = AudioSegment.silent(duration=bar_ms)
        for i, freq in enumerate(lead_freqs):
            lead_note = Square(freq).to_audio_segment(duration=400, volume=-14).fade_out(350)
            bar_audio = bar_audio.overlay(lead_note, position=i * 500)
        bar_audio = bar_audio.overlay(kick, position=0)
        bar_audio = bar_audio.overlay(kick, position=1000)
        bars.append(bar_audio)
    return sum(bars[1:], bars[0])


def main():
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating SFX + BGM...")
    hit_sfx().export(SFX_DIR / "hit.wav", format="wav")
    crit_sfx().export(SFX_DIR / "crit.wav", format="wav")
    ultimate_sfx().export(SFX_DIR / "ultimate.wav", format="wav")
    ko_sfx().export(SFX_DIR / "ko.wav", format="wav")
    charge_sfx().export(SFX_DIR / "charge.wav", format="wav")
    bgm_loop().export(BGM_DIR / "battle_loop.mp3", format="mp3", bitrate="128k")
    for name in ["hit", "crit", "ultimate", "ko", "charge"]:
        p = SFX_DIR / f"{name}.wav"
        print(f"  {name}.wav: {p.stat().st_size // 1024} KB")
    print(f"  battle_loop.mp3: {(BGM_DIR / 'battle_loop.mp3').stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
