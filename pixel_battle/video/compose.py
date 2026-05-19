"""Build mixed audio track from event log; mux with rendered video."""
import subprocess
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf

from pixel_battle.engine.battle import Event, EventType

ASSETS = Path(__file__).resolve().parents[1] / "assets"
SFX_DIR = ASSETS / "sfx"
BGM_DIR = ASSETS / "bgm"


# ---------------------------------------------------------------------------
# NumPy-based helpers used by build_audio_track
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
    """Render BGM + SFX into a single wav via the AudioMixer bus pipeline.

    Signature preserved for backward compat with episode runner. Internally
    routes events to bgm/cast/hit/ult buses; cast bus enforces 2-slot
    overlap limit; final ffmpeg pass sidechain-ducks BGM and applies
    loudnorm I=-14 (TikTok target).
    """
    from pixel_battle.video.audio_mixer import AudioMixer

    mixer = AudioMixer(sample_rate=48000)

    # BGM bus
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm_samples = _load_wav(bgm_path, mixer.sr)
        bgm_looped = _loop_to_length(bgm_samples, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(bgm_looped, t_ms=0)

    for ev in events:
        # Same positioning rule as before
        if event_video_ms is not None and id(ev) in event_video_ms:
            pos = event_video_ms[id(ev)]
        else:
            pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue

        if ev.type is EventType.HIT:
            samp = _load_sfx_samples(
                "crit" if ev.extra.get("crit") else "hit", mixer.sr,
            )
            mixer.hit_bus.add(samp, pos)
        elif ev.type is EventType.ATTACK_WINDUP:
            st = ev.extra.get("skill_type", "") if ev.extra else ""
            samp = _load_sfx_samples_or_none(f"cast_{st}", mixer.sr)
            if samp is not None:
                mixer.cast_bus.add(samp, pos)
        elif ev.type is EventType.CRIT:
            mixer.hit_bus.add(_load_sfx_samples("crit", mixer.sr), pos)
        elif ev.type is EventType.ULTIMATE_START:
            charge_pos = max(0, pos - 600)
            charge = _load_sfx_samples_or_none("charge", mixer.sr)
            if charge is not None:
                mixer.ult_bus.add(charge, charge_pos)
            skill_id = ev.extra.get("skill_id", "") if ev.extra else ""
            ult = (_load_sfx_samples_or_none(skill_id, mixer.sr)
                   or _load_sfx_samples_or_none("ultimate", mixer.sr))
            if ult is not None:
                mixer.ult_bus.add(ult, pos)
        elif ev.type is EventType.KO:
            mixer.hit_bus.add(_load_sfx_samples("ko", mixer.sr), pos)

    mixer.export(total_duration_ms, output_path)


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
