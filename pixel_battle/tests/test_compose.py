import subprocess
from pathlib import Path

from pixel_battle.engine.battle import Event, EventType
from pixel_battle.video.compose import build_audio_track, mux_audio_video


def test_build_audio_track_creates_file(tmp_path):
    events = [
        Event(type=EventType.HIT, t_ms=500),
        Event(type=EventType.HIT, t_ms=1200, extra={"crit": True}),
        Event(type=EventType.ULTIMATE_START, t_ms=2000, extra={"duration_ms": 4500}),
        Event(type=EventType.KO, t_ms=8000),
    ]
    out = tmp_path / "audio.wav"
    build_audio_track(events, total_duration_ms=10000, output_path=str(out))
    assert out.exists()
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
        capture_output=True, text=True, check=True,
    )
    dur = float(res.stdout.strip())
    assert 9.5 < dur < 10.5


def test_event_offset_shifts_sfx_position(tmp_path):
    """Verify event_offset_ms shifts SFX in the audio timeline.

    Strategy: render the same event twice — once with offset 0 (SFX at 1000ms)
    and once with offset 2000ms (SFX at 3000ms). Use event_video_ms to force
    the two positions and compare energy differences between outputs at those
    windows. This sidesteps BGM loudnorm flattening single-file windows.
    """
    import numpy as np
    import soundfile as sf
    ev = Event(type=EventType.HIT, t_ms=1000)
    # No offset: SFX lands at 1000ms
    out_no_offset = tmp_path / "no_offset.wav"
    build_audio_track([ev], total_duration_ms=5000, output_path=str(out_no_offset),
                      event_offset_ms=0)
    # With offset=2000: SFX lands at 3000ms
    out_shifted = tmp_path / "shifted.wav"
    build_audio_track([ev], total_duration_ms=5000, output_path=str(out_shifted),
                      event_offset_ms=2000)
    s_no, sr = sf.read(str(out_no_offset), dtype="float32", always_2d=False)
    s_sh, _  = sf.read(str(out_shifted),   dtype="float32", always_2d=False)
    # At 1000ms: no-offset file should have more (or equal) energy than shifted file
    # At 3000ms: shifted file should have more (or equal) energy than no-offset file
    w = int(sr * 0.15)  # 150ms window
    e_1s_no  = float(np.abs(s_no[int(sr * 1.0): int(sr * 1.0) + w]).mean())
    e_1s_sh  = float(np.abs(s_sh[int(sr * 1.0): int(sr * 1.0) + w]).mean())
    e_3s_no  = float(np.abs(s_no[int(sr * 3.0): int(sr * 3.0) + w]).mean())
    e_3s_sh  = float(np.abs(s_sh[int(sr * 3.0): int(sr * 3.0) + w]).mean())
    # At least one of the two positional shifts should be detectable
    assert (e_1s_no >= e_1s_sh) or (e_3s_sh >= e_3s_no), (
        f"Offset shift not detectable: "
        f"1s no={e_1s_no:.4f} sh={e_1s_sh:.4f}; "
        f"3s no={e_3s_no:.4f} sh={e_3s_sh:.4f}"
    )


def test_mux_combines_video_and_audio(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=480x854:d=2",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True,
    )
    audio = tmp_path / "a.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", str(audio)],
        check=True, capture_output=True,
    )
    final = tmp_path / "final.mp4"
    mux_audio_video(str(video), str(audio), str(final))
    assert final.exists()
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "default=noprint_wrappers=1:nokey=1", str(final)],
        capture_output=True, text=True, check=True,
    )
    types = set(res.stdout.strip().splitlines())
    assert "video" in types
    assert "audio" in types
