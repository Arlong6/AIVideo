# pixel_battle/rl/play_scripted.py
"""Render a fight from an authored YAML script (no RL policy).

Auto-detects legacy condition scripts and new timeline scripts; the loader
returns whichever driver fits the file."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.play import _render_fight, WIDTH, HEIGHT, RENDER_FPS, ROOT  # noqa: E402
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.script.loader import load_fight_file  # noqa: E402
from pixel_battle.rl import scaled_pygame as _scaled  # noqa: E402

OUT_DIR = ROOT / "pixel_battle" / "output" / "scripted"


def _driver_action_source(driver):
    """Adapt any driver with `.decide(battle)` to the
    (env, obs) -> (left_act, right_act) interface used by `_render_fight`."""
    def _source(env, _obs):
        return driver.decide(env.battle)
    return _source


# Backward-compat alias — existing tests import this name.
_script_action_source = _driver_action_source


def render_script(script_path: Path, out_dir: Path = OUT_DIR) -> Path:
    pygame.init()
    pygame.display.set_mode((1, 1))
    out_dir.mkdir(parents=True, exist_ok=True)

    driver = load_fight_file(script_path)

    # Arena backdrop: explicit `arena:` field in the YAML wins, otherwise rotate
    # themes by script name so a batch reel varies scene to scene.
    import yaml as _yaml
    from pixel_battle.rl.play import set_arena, _ARENA_THEMES
    _arena = None
    try:
        _meta = _yaml.safe_load(script_path.read_text(encoding="utf-8"))
        if isinstance(_meta, dict):
            _arena = _meta.get("arena")
    except Exception:
        _arena = None
    if not _arena:
        _arena = _ARENA_THEMES[sum(map(ord, script_path.stem)) % len(_ARENA_THEMES)]
    set_arena(_arena)

    tl_seed = getattr(driver.timeline, "seed", None)
    env_kwargs = {"left_id": driver.left, "right_id": driver.right}
    if tl_seed is not None:
        env_kwargs["seed"] = tl_seed
    env = PixelBattleEnv(**env_kwargs)

    # Optional per-script starting MP override (lets a script's choreography
    # rely on an ultimate firing at a specific moment without playing 8 setup
    # casts to charge it). Only applies to the timeline (legacy ScriptDriver
    # doesn't expose start MP). Passed INTO _render_fight so it is applied AFTER
    # the internal env.reset() — applying it here would be clobbered by that reset.
    tl = getattr(driver, "timeline", None)
    left_start_mp = getattr(tl, "left_start_mp", None) if tl is not None else None
    right_start_mp = getattr(tl, "right_start_mp", None) if tl is not None else None
    left_start_hp = getattr(tl, "left_start_hp", None) if tl is not None else None
    right_start_hp = getattr(tl, "right_start_hp", None) if tl is not None else None

    raw = out_dir / f"{script_path.stem}_raw.mp4"
    recorder = FrameRecorder(str(raw), fps=RENDER_FPS,
                             width=_scaled.CANVAS_SCALED[0],
                             height=_scaled.CANVAS_SCALED[1])
    recorder.start()
    fight = None
    try:
        fight = _render_fight(recorder, _driver_action_source(driver), env,
                              max_seconds=60.0, end_hold_frames=120,
                              left_start_mp=left_start_mp, right_start_mp=right_start_mp,
                              left_start_hp=left_start_hp, right_start_hp=right_start_hp)
    finally:
        recorder.stop()

    # Audio bed: BGM + routed SFX (hits / casts / ults incl. the summon rumble),
    # muxed INTO the raw so the posting short carries sound. The scripted batch
    # was silent before this — TikTok/Shorts weight audio heavily.
    if fight is not None:
        try:
            from pixel_battle.rl.play import (
                AudioMixer, mux_audio_video, BGM_DIR, _route_audio_for_events,
                _load_wav, _loop_to_length, RENDER_MS)
            total_ms = int(fight["n_frames"] * RENDER_MS)
            mixer = AudioMixer(sample_rate=48000)
            bgm_path = BGM_DIR / "battle_loop.mp3"
            if bgm_path.exists():
                mixer.bgm_bus.add(
                    _loop_to_length(_load_wav(bgm_path, mixer.sr), total_ms, mixer.sr), t_ms=0)
            _route_audio_for_events(fight["events"], fight["event_video_ms"], mixer)
            audio_wav = out_dir / f"{script_path.stem}_audio.wav"
            mixer.export(total_ms, str(audio_wav))
            snd = out_dir / f"{script_path.stem}_snd.mp4"
            mux_audio_video(str(raw), str(audio_wav), str(snd))
            snd.replace(raw)                       # raw now carries the audio track
        except Exception as e:
            print(f"  [audio] skipped ({e})")
    print(f"Scripted render: {raw}")
    return raw


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("script", type=Path, help="path to a fight-script YAML")
    args = p.parse_args()
    render_script(args.script)
