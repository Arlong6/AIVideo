"""Phase 1 demo: existing engine + heuristic AI + stick figure visuals.

Output: pixel_battle/output/sticks_demo/final.mp4
"""
from __future__ import annotations
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.rl.stick_renderer import draw_stick_figure
from pixel_battle.video.recorder import FrameRecorder
from pixel_battle.video.audio_mixer import AudioMixer
from pixel_battle.video.compose import (
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
TICK_MS = 16
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "sticks_demo"


def draw_arena(surf, ground_y):
    surf.fill(BG)
    pygame.draw.line(surf, (60, 70, 110), (0, ground_y),
                      (WIDTH, ground_y), 2)


def main(max_seconds: int = 30):
    pygame.init()
    pygame.display.set_mode((1, 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    rng = BattleRNG(42)
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    battle = Battle(left=left, right=right, rng=rng)

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()

    mixer = AudioMixer(sample_rate=48000)

    surf = pygame.Surface((WIDTH, HEIGHT))
    total_frames = max_seconds * FPS
    event_video_ms: dict = {}

    for frame_no in range(total_frames):
        if battle.state == BattleState.KO:
            # Hold last frame for 2s of result, then stop
            if frame_no > total_frames - 120:
                break
        prev_n = len(battle.events)
        battle.tick_ms(TICK_MS)
        for ev in battle.events[prev_n:]:
            event_video_ms[id(ev)] = int(frame_no * FRAME_MS)

        draw_arena(surf, GROUND_Y)
        draw_stick_figure(surf, left, RED)
        draw_stick_figure(surf, right, BLUE)
        recorder.write_frame(surf)

    recorder.stop()

    # Build audio track using existing helpers — reuses synthwave BGM + SFX
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, int(total_frames * FRAME_MS), mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    for ev in battle.events:
        pos = event_video_ms.get(id(ev), int(ev.t_ms))
        name_map = {"hit": "hit", "crit": "crit", "ko": "ko",
                     "attack_windup": None, "ultimate_start": "ultimate"}
        # See ev.type.value for the string form
        type_val = ev.type.value
        sfx_name = name_map.get(type_val)
        if sfx_name is None and type_val == "attack_windup":
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

    mixer.export(int(total_frames * FRAME_MS), str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ Sticks demo: {final_mp4} ({max_seconds}s)")


if __name__ == "__main__":
    main()
