"""Build mixed audio track from event log; mux with rendered video."""
import subprocess
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf
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


# ---------------------------------------------------------------------------
# NumPy-based helpers (used by the rewritten build_audio_track in T6)
# The old pydub helpers above are kept until T6 replaces build_audio_track.
# ---------------------------------------------------------------------------

def _load_wav(path: Path, target_sr: int) -> np.ndarray:
    """Load a wav/mp3 as mono float32 at target_sr. Resamples if needed."""
    data, sr = sf.read(str(path), always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32, copy=False)
    if sr != target_sr:
        # Simple linear resample — fine for ducking/loop content
        n_out = int(len(data) * target_sr / sr)
        idx = np.linspace(0, len(data) - 1, n_out)
        data = np.interp(idx, np.arange(len(data)), data).astype(np.float32)
    return data


def _loop_to_length(samples: np.ndarray, total_ms: int, sample_rate: int) -> np.ndarray:
    """Repeat-tile then truncate to exactly total_ms worth of samples."""
    n_target = int(total_ms * sample_rate / 1000)
    if len(samples) == 0:
        return np.zeros(n_target, dtype=np.float32)
    reps = (n_target // len(samples)) + 1
    return np.tile(samples, reps)[:n_target].astype(np.float32, copy=False)


def _load_sfx_samples(name: str, sample_rate: int) -> np.ndarray:
    """Hard load — raises if missing (mirrors old _load_sfx)."""
    path = SFX_DIR / f"{name}.wav"
    return _load_wav(path, sample_rate)


def _load_sfx_samples_or_none(name: str, sample_rate: int):
    """Soft load — returns None if missing (mirrors old _load_sfx_or_none)."""
    path = SFX_DIR / f"{name}.wav"
    if not path.exists():
        return None
    return _load_wav(path, sample_rate)


def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str,
                      event_offset_ms: int = 0,
                      event_video_ms: dict | None = None) -> None:
    """Render BGM + SFX into a single wav matching total_duration_ms.

    event_offset_ms: time offset in audio at which battle starts.
                     Add to each event's t_ms when overlaying SFX (default path).
    event_video_ms:  optional {id(event): video_ms} map. When provided and
                     id(event) is in the map, use that value instead of
                     ev.t_ms + event_offset_ms. Used to correct for hit-stop
                     accumulation that pushes video behind battle-time.
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
        # Position: use event_video_ms[id(ev)] if provided (P4 sync correction),
        # else fall back to ev.t_ms + event_offset_ms
        if event_video_ms is not None and id(ev) in event_video_ms:
            pos = event_video_ms[id(ev)]
        else:
            pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue  # off-end, skip
        if ev.type is EventType.HIT:
            sfx = _load_sfx("crit") if ev.extra.get("crit") else _load_sfx("hit")
            track = track.overlay(sfx, position=pos)
        elif ev.type is EventType.ATTACK_WINDUP:
            st = ev.extra.get("skill_type", "") if ev.extra else ""
            cast_name = f"cast_{st}"  # cast_cooldown / cast_special
            cast_sfx = _load_sfx_or_none(cast_name)
            if cast_sfx:
                track = track.overlay(cast_sfx, position=pos)
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
