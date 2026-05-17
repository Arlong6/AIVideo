"""Episode 1 driver. Runs Brick Phone vs Glass Slab, produces final.mp4."""
import json
import os
from pathlib import Path

import pygame

from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.cinematic import CINEMATICS, play_cinematic_frame
from pixel_battle.engine.renderer import (
    AnimationState, Renderer, WIDTH, HEIGHT,
)
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.video.captions import CaptionStyle, draw_caption
from pixel_battle.video.compose import build_audio_track, mux_audio_video
from pixel_battle.video.recorder import FrameRecorder

FPS = 60
TICK_MS = 1000 // FPS  # 16ms ≈ 60fps
EPISODE_ID = "ep01_brick_vs_glass"
OUT_DIR = Path("/Users/arlong/Projects/AIvideo/pixel_battle/output") / EPISODE_ID
SEED = 1


def _animation_for_actor(actor_id: str, char: Character, recent_events) -> AnimationState:
    if char.is_ko():
        return AnimationState.KO
    for ev in reversed(recent_events):
        if ev.type is EventType.HIT and ev.target == actor_id:
            return AnimationState.HIT
        if ev.type is EventType.HIT and ev.actor == actor_id:
            return AnimationState.ATTACK
    return AnimationState.IDLE


def _caption_style_for_event(ev) -> CaptionStyle:
    if ev.type is EventType.ULTIMATE_START:
        return CaptionStyle.ULTIMATE
    if ev.type is EventType.KO:
        return CaptionStyle.KO
    if ev.extra.get("crit"):
        return CaptionStyle.CRIT
    return CaptionStyle.HIT


def _caption_text_for_event(ev) -> str:
    if ev.type is EventType.ULTIMATE_START:
        return ev.extra.get("anim", "ULTIMATE").replace("_", " ").upper()
    if ev.type is EventType.KO:
        return "GAME OVER"
    if ev.extra.get("crit"):
        return "CRITICAL HIT!"
    return f"-{ev.amount}"


def main():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    rng = BattleRNG(SEED)
    battle = Battle(left=left, right=right, rng=rng)
    renderer = Renderer()

    raw_video = OUT_DIR / "battle_raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    recorder = FrameRecorder(str(raw_video), fps=FPS, width=WIDTH, height=HEIGHT)
    recorder.start()

    cinematic_frame_idx = 0
    active_captions = []  # list of (text, style, started_frame)

    frame_no = 0
    while battle.state is not BattleState.KO and battle.elapsed_ms < 60_000:
        prev_event_count = len(battle.events)
        battle.tick_ms(TICK_MS)
        new_events = battle.events[prev_event_count:]

        for ev in new_events:
            if ev.type in (EventType.HIT, EventType.ULTIMATE_START, EventType.KO):
                active_captions.append((_caption_text_for_event(ev), _caption_style_for_event(ev), frame_no))

        if battle.state is BattleState.ULTIMATE_PLAYING:
            ult_event = next(
                (e for e in reversed(battle.events) if e.type is EventType.ULTIMATE_START),
                None,
            )
            if ult_event:
                anim_name = ult_event.extra.get("anim", "indestructible_throw")
                attacker = left if ult_event.actor == left.id else right
                defender = right if attacker is left else left
                play_cinematic_frame(renderer.surface, anim_name, cinematic_frame_idx,
                                     attacker=attacker, defender=defender)
                cinematic_frame_idx += 1
        else:
            cinematic_frame_idx = 0
            la = _animation_for_actor(left.id, left, battle.events[-6:])
            ra = _animation_for_actor(right.id, right, battle.events[-6:])
            renderer.render_frame(left, right, la, ra, anim_frame=frame_no % 8)

        active_captions = [
            (txt, sty, start) for (txt, sty, start) in active_captions
            if frame_no - start < 45
        ]
        for (txt, sty, start) in active_captions:
            draw_caption(renderer.surface, txt, sty, frame_in_anim=frame_no - start)

        recorder.write_frame(renderer.surface)
        frame_no += 1

    # Hold final 30 frames
    for hold_frame in range(30):
        renderer.render_frame(left, right, AnimationState.IDLE, AnimationState.KO if right.is_ko() else AnimationState.IDLE, anim_frame=hold_frame)
        active_captions = [(txt, sty, start) for (txt, sty, start) in active_captions if frame_no - start < 45]
        for (txt, sty, start) in active_captions:
            draw_caption(renderer.surface, txt, sty, frame_in_anim=frame_no - start)
        recorder.write_frame(renderer.surface)
        frame_no += 1

    recorder.stop()

    # Thumbnail: extract frame at the first ultimate's peak
    first_ult = next((e for e in battle.events if e.type is EventType.ULTIMATE_START), None)
    if first_ult:
        # Peak frame ~80 frames into the cinematic
        peak_ms = first_ult.t_ms + (80 * 1000 // 30)  # 80 frames at 30fps
        import subprocess
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(raw_video),
            "-ss", f"{peak_ms/1000:.2f}",
            "-vframes", "1",
            "-q:v", "2",
            str(OUT_DIR / "thumbnail.jpg"),
        ], check=True, capture_output=True)

    total_ms = battle.elapsed_ms + (30 * TICK_MS)
    build_audio_track(battle.events, total_duration_ms=total_ms, output_path=str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))

    with open(OUT_DIR / "battle_events.json", "w") as f:
        json.dump(
            [{"type": e.type.value, "t_ms": e.t_ms, "actor": e.actor,
              "target": e.target, "amount": e.amount, "extra": e.extra}
             for e in battle.events],
            f, indent=2,
        )
    winner = left.display_name if right.is_ko() else right.display_name if left.is_ko() else "Draw"
    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump({
            "episode": EPISODE_ID,
            "seed": SEED,
            "duration_ms": total_ms,
            "winner": winner,
            "title_zh": "磚頭機 vs 玻璃板 — Tech Era Clash Ep.1",
            "title_en": "Brick Phone vs Glass Slab",
            "hashtags": ["#pixelbattle", "#retrovsfuture", "#shorts"],
            "description": "Procedural pixel battle. New episode 2x/week.",
        }, f, indent=2, ensure_ascii=False)

    print(f"✅ Episode 1 produced: {final_mp4}")
    print(f"   Winner: {winner}, duration: {total_ms/1000:.1f}s")


if __name__ == "__main__":
    main()
