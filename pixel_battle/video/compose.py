"""Build mixed audio track from event log; mux with rendered video."""
import subprocess
from pathlib import Path
from typing import List

from pydub import AudioSegment

from pixel_battle.engine.battle import Event, EventType

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SFX_DIR = ASSETS / "sfx"
BGM_DIR = ASSETS / "bgm"


def _load_sfx(name: str) -> AudioSegment:
    path = SFX_DIR / f"{name}.wav"
    return AudioSegment.from_file(path)


def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str) -> None:
    """Render BGM + SFX into a single wav matching total_duration_ms."""
    track = AudioSegment.silent(duration=total_duration_ms)

    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = AudioSegment.from_file(bgm_path) - 18
        loops_needed = (total_duration_ms // len(bgm)) + 1
        bgm_full = bgm * loops_needed
        bgm_full = bgm_full[:total_duration_ms]
        track = track.overlay(bgm_full)

    for ev in events:
        if ev.type is EventType.HIT:
            sfx = _load_sfx("crit") if ev.extra.get("crit") else _load_sfx("hit")
            track = track.overlay(sfx, position=ev.t_ms)
        elif ev.type is EventType.CRIT:
            track = track.overlay(_load_sfx("crit"), position=ev.t_ms)
        elif ev.type is EventType.ULTIMATE_START:
            track = track.overlay(_load_sfx("ultimate"), position=ev.t_ms)
        elif ev.type is EventType.KO:
            track = track.overlay(_load_sfx("ko"), position=ev.t_ms)

    track.export(output_path, format="wav")


def mux_audio_video(video_path: str, audio_path: str, output_path: str) -> None:
    """Combine silent video + audio into final mp4 with AAC audio."""
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
