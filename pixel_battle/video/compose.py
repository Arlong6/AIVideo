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
    """Load SFX by name; raises if missing (use _load_sfx_or_none for soft lookup)."""
    path = SFX_DIR / f"{name}.wav"
    return AudioSegment.from_file(path)


def _load_sfx_or_none(name: str):
    """Soft SFX lookup — returns None if file is absent."""
    path = SFX_DIR / f"{name}.wav"
    if not path.exists():
        return None
    return AudioSegment.from_file(path)


def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str,
                      event_offset_ms: int = 0) -> None:
    """Render BGM + SFX into a single wav matching total_duration_ms.

    event_offset_ms: time offset in audio at which battle starts.
                     Add to each event's t_ms when overlaying SFX.
    """
    track = AudioSegment.silent(duration=total_duration_ms)

    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = AudioSegment.from_file(bgm_path) - 18
        loops_needed = (total_duration_ms // len(bgm)) + 1
        bgm_full = bgm * loops_needed
        bgm_full = bgm_full[:total_duration_ms]
        track = track.overlay(bgm_full)

    for ev in events:
        # Shift event position by intro offset so SFX aligns with video frame
        pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue  # off-end, skip
        if ev.type is EventType.HIT:
            sfx = _load_sfx("crit") if ev.extra.get("crit") else _load_sfx("hit")
            track = track.overlay(sfx, position=pos)
        elif ev.type is EventType.CRIT:
            track = track.overlay(_load_sfx("crit"), position=pos)
        elif ev.type is EventType.ULTIMATE_START:
            # Charge build-up 600ms before impact + impact
            charge_pos = max(0, pos - 600)
            charge_sfx = _load_sfx_or_none("charge")
            if charge_sfx:
                track = track.overlay(charge_sfx, position=charge_pos)
            # Try skill-specific ult SFX first, fall back to generic ultimate.wav
            skill_id = ev.extra.get("skill_id", "") if ev.extra else ""
            ult_sfx = _load_sfx_or_none(skill_id) or _load_sfx_or_none("ultimate")
            if ult_sfx:
                track = track.overlay(ult_sfx, position=pos)
        elif ev.type is EventType.KO:
            track = track.overlay(_load_sfx("ko"), position=pos)

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
