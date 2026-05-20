"""Load a trained PPO checkpoint, render a self-play fight as mp4."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.stick_renderer import draw_stick_figure  # noqa: E402
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.video.audio_mixer import AudioMixer  # noqa: E402
from pixel_battle.video.compose import (  # noqa: E402
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = ROOT / "data" / "rl_checkpoints" / "ppo_final.zip"
OUT_DIR = ROOT / "pixel_battle" / "output" / "rl_play"


def _route_audio_for_events(events, event_video_ms, mixer):
    """Use the existing audio routing convention from compose.py."""
    for ev in events:
        pos = event_video_ms.get(id(ev))
        if pos is None:
            continue
        type_val = ev.type.value
        sfx_name = None
        if type_val == "hit":
            sfx_name = "crit" if (ev.extra or {}).get("crit") else "hit"
        elif type_val == "crit":
            sfx_name = "crit"
        elif type_val == "ko":
            sfx_name = "ko"
        elif type_val == "ultimate_start":
            sfx_name = "ultimate"
        elif type_val == "attack_windup":
            kind = (ev.extra or {}).get("skill_type", "")
            sfx_name = f"cast_{kind}"
        if not sfx_name:
            continue
        samp = _load_sfx_samples_or_none(sfx_name, mixer.sr)
        if samp is None:
            continue
        if sfx_name in ("hit", "crit", "ko"):
            mixer.hit_bus.add(samp, pos)
        elif sfx_name.startswith("cast_"):
            mixer.cast_bus.add(samp, pos)
        else:
            mixer.ult_bus.add(samp, pos)


def run_one_match(model, seed: int, out_dir: Path,
                   max_seconds: float = 60.0,
                   match_name: str = "final") -> dict:
    """Run a single self-play match. Returns:
        {"finished_by_ko": bool,
         "duration_s": float,
         "winner": "left"|"right"|None,
         "mp4_path": Path,
         "raw_path": Path,
         "audio_path": Path}
    The mp4 is written to out_dir/{match_name}.mp4. Caller decides whether
    to keep or discard based on finished_by_ko.
    Assumes pygame is already initialized (caller's responsibility).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_video = out_dir / f"{match_name}_raw.mp4"
    audio_out = out_dir / f"{match_name}_audio.wav"
    final_mp4 = out_dir / f"{match_name}.mp4"

    env = PixelBattleEnv(seed=seed)
    (obs_left, obs_right), _ = env.reset()

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()
    mixer = AudioMixer(sample_rate=48000)

    surf = pygame.Surface((WIDTH, HEIGHT))
    total_frames = int(max_seconds * FPS)
    event_video_ms: dict = {}
    terminated = False
    frame = 0

    for frame in range(total_frames):
        left_act, _ = model.predict(obs_left, deterministic=False)
        right_act, _ = model.predict(obs_right, deterministic=False)

        prev_ev_n = len(env.battle.events)
        (obs_left, obs_right), _, terminated, truncated, _ = env.step(
            (int(left_act), int(right_act))
        )
        for ev in env.battle.events[prev_ev_n:]:
            event_video_ms[id(ev)] = int(frame * FRAME_MS)

        surf.fill(BG)
        pygame.draw.line(surf, (60, 70, 110), (0, GROUND_Y),
                          (WIDTH, GROUND_Y), 2)
        draw_stick_figure(surf, env.left, RED)
        draw_stick_figure(surf, env.right, BLUE)
        recorder.write_frame(surf)

        if terminated:
            for _ in range(120):  # 2s hold
                recorder.write_frame(surf)
            break

    recorder.stop()
    actual_frames = (frame + 1 + 120) if terminated else total_frames
    total_duration_ms = int(actual_frames * FRAME_MS)

    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    _route_audio_for_events(env.battle.events, event_video_ms, mixer)

    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))

    # Determine winner
    if terminated:
        if env.right.is_ko() and not env.left.is_ko():
            winner = "left"
        elif env.left.is_ko() and not env.right.is_ko():
            winner = "right"
        else:
            winner = None
    else:
        winner = None

    return {
        "finished_by_ko": bool(terminated),
        "duration_s": total_duration_ms / 1000.0,
        "winner": winner,
        "mp4_path": final_mp4,
        "raw_path": raw_video,
        "audio_path": audio_out,
    }


def main(checkpoint: Path = DEFAULT_CKPT, max_seconds: float = 60.0,
          seed: int = 1234):
    pygame.init()
    pygame.display.set_mode((1, 1))
    model = PPO.load(str(checkpoint))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = run_one_match(model, seed=seed, out_dir=OUT_DIR,
                            max_seconds=max_seconds, match_name="final")
    print(f"✅ RL play: {result['mp4_path']} ({result['duration_s']:.1f}s)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--max_seconds", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=1234)
    args = p.parse_args()
    main(checkpoint=args.checkpoint,
          max_seconds=args.max_seconds, seed=args.seed)
