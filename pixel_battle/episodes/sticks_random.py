"""Phase 2 deliverable: PixelBattleEnv + random agents + stick visuals."""
from __future__ import annotations
import os
import random
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv
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
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

OUT_DIR = Path(__file__).resolve().parents[1] / "output" / "sticks_random"


def main(max_seconds: int = 30, seed: int = 7):
    pygame.init()
    pygame.display.set_mode((1, 1))
    random.seed(seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    env = PixelBattleEnv(seed=seed)
    env.reset()

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()

    surf = pygame.Surface((WIDTH, HEIGHT))
    mixer = AudioMixer(sample_rate=48000)
    total_frames = max_seconds * FPS
    total_duration_ms = int(total_frames * FRAME_MS)

    for frame in range(total_frames):
        action = (random.randint(0, 6), random.randint(0, 6))
        env.step(action)

        surf.fill(BG)
        pygame.draw.line(surf, (60, 70, 110), (0, GROUND_Y),
                          (WIDTH, GROUND_Y), 2)
        draw_stick_figure(surf, env.left, RED)
        draw_stick_figure(surf, env.right, BLUE)
        recorder.write_frame(surf)

        if env.battle.state.name == "KO":
            # Hold a few frames after KO then stop
            for _ in range(60):
                recorder.write_frame(surf)
            break

    recorder.stop()

    # Minimal audio: BGM only (no SFX wiring for random agent)
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ Sticks random: {final_mp4} ({max_seconds}s)")


if __name__ == "__main__":
    main()
