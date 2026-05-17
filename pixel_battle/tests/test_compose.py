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
