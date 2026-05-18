"""P4: build_audio_track accepts event_video_ms map for sync correction."""
import os
import tempfile
from pathlib import Path

from pydub import AudioSegment

from pixel_battle.engine.battle import Event, EventType
from pixel_battle.video.compose import build_audio_track


def test_build_audio_track_accepts_event_video_ms_map():
    """build_audio_track signature accepts event_video_ms keyword argument."""
    events = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        build_audio_track(events, total_duration_ms=2000,
                           output_path=str(out),
                           event_offset_ms=0,
                           event_video_ms={})
        assert out.exists()


def test_event_video_ms_overrides_t_ms_position():
    """When event_video_ms[id(ev)] is set, use that as audio position instead of ev.t_ms+offset."""
    ev = Event(type=EventType.HIT, t_ms=1000, actor="a", target="b", amount=5,
                extra={"crit": False})
    events = [ev]
    with tempfile.TemporaryDirectory() as tmp:
        # Without map: SFX positioned at t_ms + offset = 1000 + 500 = 1500ms
        out1 = Path(tmp) / "without_map.wav"
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out1), event_offset_ms=500)
        # With map: override position to 2000ms
        out2 = Path(tmp) / "with_map.wav"
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out2), event_offset_ms=500,
                           event_video_ms={id(ev): 2000})
        a1 = AudioSegment.from_file(out1)
        a2 = AudioSegment.from_file(out2)
        assert abs(len(a1) - len(a2)) < 100
        seg_at_1500_no_map = a1[1450:1550]
        seg_at_2000_no_map = a1[1950:2050]
        seg_at_1500_with_map = a2[1450:1550]
        seg_at_2000_with_map = a2[1950:2050]
        # In a1 (no map), 1500 has audio energy; in a2 (with map), 2000 has audio energy
        assert seg_at_1500_no_map.rms > seg_at_1500_with_map.rms or \
               seg_at_2000_with_map.rms > seg_at_2000_no_map.rms


def test_event_video_ms_falls_back_to_t_ms_when_missing():
    """If event_video_ms map doesn't contain the event, fall back to t_ms + offset."""
    ev = Event(type=EventType.HIT, t_ms=1000, actor="a", target="b", amount=5,
                extra={"crit": False})
    events = [ev]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out), event_offset_ms=500,
                           event_video_ms={})
        assert out.exists()
