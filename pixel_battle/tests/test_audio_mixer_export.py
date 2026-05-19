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
