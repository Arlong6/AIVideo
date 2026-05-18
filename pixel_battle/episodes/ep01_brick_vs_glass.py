"""Episode 1 driver. Runs Brick Phone vs Glass Slab, produces final.mp4."""
import json
import os
from pathlib import Path

import pygame

from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.cinematic import CINEMATICS, play_cinematic_frame
from pixel_battle.engine.renderer import (
    AnimationState, Renderer, WIDTH, HEIGHT, HORIZON_Y,
)
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.video.captions import CaptionStyle, draw_caption
from pixel_battle.video.compose import build_audio_track, mux_audio_video
from pixel_battle.video.recorder import FrameRecorder


_HIT_COLOR_BY_SKILL_TYPE = {
    "basic":    (220, 220, 180),   # white-yellow
    "cooldown": ( 80, 180, 255),   # cyan
    "special":  (255, 140,  40),   # orange
}

_BANNER_COLOR_BY_SKILL_TYPE = {
    "cooldown": ( 80, 180, 255),
    "special":  (255, 140,  40),
    "ultimate": (255, 220,  80),
}

_SKILL_BANNER_NAME = {
    "screw_dart":           "SCREW DART!",
    "shard_scatter":        "SHARD SCATTER!",
    "snake_strike":         "SNAKE STRIKE!",
    "ringtone_blast":       "RINGTONE BLAST!",
    "ringtone_shock":       "RINGTONE SHOCK!",
    "ad_popup_spam":        "AD POPUP SPAM!",
    "indestructible_throw": "INDESTRUCTIBLE THROW!",
    "force_update":         "FORCE UPDATE!",
}


def _result_pop_scale(frame: int, peak_frame: int = 8) -> float:
    """Scale animation: 0 → 1.3 → 1.0."""
    if frame < 0:
        return 0.0
    if frame < peak_frame:
        t = frame / peak_frame
        return 1.3 * (1 - (1 - t) ** 2)
    elif frame < peak_frame + 6:
        t = (frame - peak_frame) / 6
        return 1.3 + (1.0 - 1.3) * (1 - (1 - t) ** 2)
    return 1.0


def _draw_result_screen(renderer, winner_char, loser_char, hits, ults, match_seconds, frame):
    """Paint the post-KO result screen onto renderer.surface."""
    surface = renderer.surface
    # Fade-in background: black with subtle vignette
    bg_alpha = min(255, int(255 * (frame / 30)))
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, bg_alpha))

    # First fill background from arena
    surface.blit(renderer._arena_bg, (0, 0))
    surface.blit(overlay, (0, 0))

    if not pygame.font.get_init():
        pygame.font.init()

    # "K.O." big text top — scale-pop in first 12 frames
    ko_scale = _result_pop_scale(frame, peak_frame=8)
    ko_font_size = int(120 * ko_scale)
    if ko_font_size > 1:
        ko_font = pygame.font.Font(None, ko_font_size)
        ko_img = ko_font.render("K.O.", True, (255, 70, 70))
        ko_rect = ko_img.get_rect(center=(WIDTH // 2, 140))
        # Black drop shadow
        ko_shadow = ko_font.render("K.O.", True, (0, 0, 0))
        surface.blit(ko_shadow, (ko_rect.x + 5, ko_rect.y + 5))
        surface.blit(ko_img, ko_rect)

    # Winner sprite at center — animates upward over first 30 frames
    if frame > 15:
        sprites = renderer._get_sprites(winner_char.id)
        winner_sprite = sprites.get_pose("ultimate_pose")
        # Scale up 1.4x for emphasis
        ws_w = int(winner_sprite.get_width() * 1.4)
        ws_h = int(winner_sprite.get_height() * 1.4)
        big_sprite = pygame.transform.smoothscale(winner_sprite, (ws_w, ws_h))
        sprite_y_target = HEIGHT // 2 + 20
        sprite_progress = min(1.0, (frame - 15) / 25)
        sprite_y = int(HEIGHT + (sprite_y_target - HEIGHT) * sprite_progress)
        sprite_rect = big_sprite.get_rect(center=(WIDTH // 2, sprite_y))
        surface.blit(big_sprite, sprite_rect)

    # "WINNER" banner under sprite — appears at frame 40
    if frame > 40:
        banner_scale = _result_pop_scale(frame - 40, peak_frame=8)
        banner_size = max(1, int(60 * banner_scale))
        banner_font = pygame.font.Font(None, banner_size)
        banner_img = banner_font.render("WINNER", True, (255, 220, 60))
        banner_rect = banner_img.get_rect(center=(WIDTH // 2, HEIGHT - 220))
        shadow = banner_font.render("WINNER", True, (0, 0, 0))
        surface.blit(shadow, (banner_rect.x + 3, banner_rect.y + 3))
        surface.blit(banner_img, banner_rect)
        # Winner display name below banner
        name_font = pygame.font.Font(None, 36)
        name_img = name_font.render(winner_char.display_name, True, (240, 240, 240))
        name_rect = name_img.get_rect(center=(WIDTH // 2, HEIGHT - 170))
        surface.blit(name_img, name_rect)

    # Stats panel at bottom — appears at frame 70
    if frame > 70:
        stats_font = pygame.font.Font(None, 24)
        stats_lines = [
            f"TIME      {match_seconds:5.1f}s",
            f"HITS      {hits}",
            f"ULTIMATES {ults}",
        ]
        for i, line in enumerate(stats_lines):
            line_img = stats_font.render(line, True, (200, 200, 220))
            line_rect = line_img.get_rect(center=(WIDTH // 2, HEIGHT - 100 + i * 28))
            surface.blit(line_img, line_rect)

def _draw_pop_text(surface, text: str, pos: tuple, size: int = 32,
                   color=(255, 255, 255), scale: float = 1.0,
                   alpha: int = 255, shadow: bool = True) -> None:
    """Render text with scale + alpha, optionally with a black drop shadow."""
    if scale <= 0.05 or alpha <= 5:
        return
    if not pygame.font.get_init():
        pygame.font.init()
    actual_size = max(1, int(size * scale))
    font = pygame.font.Font(None, actual_size)
    img = font.render(text, True, color)
    img.set_alpha(alpha)
    rect = img.get_rect(center=pos)
    if shadow:
        shadow_img = font.render(text, True, (0, 0, 0))
        shadow_img.set_alpha(alpha // 2)
        surface.blit(shadow_img, (rect.x + 3, rect.y + 3))
    surface.blit(img, rect)


def _draw_intro_screen(renderer, left_char, right_char, frame: int):
    """Paint the pre-battle intro: name labels + VS + GAME START."""
    surface = renderer.surface
    # Paint the arena + characters idle (so the scene is in place behind text)
    renderer.render_frame(left_char, right_char,
                          AnimationState.IDLE, AnimationState.IDLE,
                          anim_frame=frame % 8)

    if not pygame.font.get_init():
        pygame.font.init()

    # Phase 1 — name labels (visible 0-150, fade 150-180)
    name_fade = 1.0
    if frame >= 150:
        name_fade = max(0.0, 1.0 - (frame - 150) / 30)
    name_scale = _result_pop_scale(frame, peak_frame=12) if frame < 30 else 1.0
    _draw_pop_text(
        surface, left_char.display_name.upper(),
        (WIDTH // 4, 80), size=28, color=(180, 240, 255),
        scale=name_scale, alpha=int(255 * name_fade), shadow=True,
    )
    _draw_pop_text(
        surface, right_char.display_name.upper(),
        (WIDTH * 3 // 4, 80), size=28, color=(180, 240, 255),
        scale=name_scale, alpha=int(255 * name_fade), shadow=True,
    )

    # Phase 2 — VS (appears at frame 30, holds, fades 150-180)
    if frame >= 30:
        vs_fade = 1.0
        if frame >= 150:
            vs_fade = max(0.0, 1.0 - (frame - 150) / 30)
        vs_scale = _result_pop_scale(frame - 30, peak_frame=10) if frame < 60 else 1.0
        _draw_pop_text(
            surface, "VS",
            (WIDTH // 2, HEIGHT // 2 - 100),
            size=120, color=(255, 200, 60),
            scale=vs_scale, alpha=int(255 * vs_fade), shadow=True,
        )

    # Phase 3 — GAME START (appears at frame 90, holds, fades 150-180)
    if frame >= 90:
        gs_fade = 1.0
        if frame >= 150:
            gs_fade = max(0.0, 1.0 - (frame - 150) / 30)
        gs_scale = _result_pop_scale(frame - 90, peak_frame=12) if frame < 120 else 1.0
        _draw_pop_text(
            surface, "GAME START!",
            (WIDTH // 2, HEIGHT // 2 + 80),
            size=80, color=(120, 255, 120),
            scale=gs_scale, alpha=int(255 * gs_fade), shadow=True,
        )


FPS = 60
TICK_MS = 1000 // FPS  # 16ms ≈ 60fps
EPISODE_ID = "ep01_brick_vs_glass"
OUT_DIR = Path("/Users/arlong/Projects/AIvideo/pixel_battle/output") / EPISODE_ID
SEED = 1


def _animation_for_actor(char: Character) -> AnimationState:
    """Map character action_state to AnimationState. Source of truth is char.action_state."""
    if char.is_ko():
        return AnimationState.KO
    if char.action_state == "hit_stagger":
        return AnimationState.HIT
    if char.action_state == "attacking":
        return AnimationState.ATTACK
    if char.action_state == "jumping":
        return AnimationState.JUMPING
    if char.action_state == "walking":
        return AnimationState.WALKING
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
    # Battle.__init__ calls reset_physics on both characters
    battle = Battle(left=left, right=right, rng=rng)
    renderer = Renderer()
    renderer.set_hud(left, right)

    raw_video = OUT_DIR / "battle_raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    recorder = FrameRecorder(str(raw_video), fps=FPS, width=WIDTH, height=HEIGHT)
    recorder.start()

    cinematic_frame_idx = 0.0
    active_captions = []  # list of (text, style, started_frame, pos|None)

    frame_no = 0

    # Intro phase — 180 frames (3s at 60fps)
    INTRO_FRAMES = 180
    for intro_frame in range(INTRO_FRAMES):
        _draw_intro_screen(renderer, left, right, intro_frame)
        recorder.write_frame(renderer.surface)
        frame_no += 1

    while battle.state is not BattleState.KO and battle.elapsed_ms < 60_000:
        # Hit-stop: only when actually fighting (not during cinematics)
        if battle.state is BattleState.ULTIMATE_PLAYING:
            renderer.hit_stop_frames = 0
        elif renderer.hit_stop_frames > 0:
            renderer.hit_stop_frames -= 1
            recorder.write_frame(renderer.surface)
            frame_no += 1
            continue

        prev_event_count = len(battle.events)
        battle.tick_ms(TICK_MS)
        new_events = battle.events[prev_event_count:]

        for ev in new_events:
            # Resolve target character object for position-based effects
            target_char = left if ev.target == left.id else right

            if ev.type in (EventType.HIT, EventType.ULTIMATE_START, EventType.KO):
                if ev.type is EventType.HIT:
                    # Use world position: above character's head
                    victim_x = int(target_char.pos_x)
                    victim_y = int(target_char.pos_y) - 200
                    # Damage tier
                    dmg_style = CaptionStyle.DAMAGE_HEAVY if ev.amount > 10 else CaptionStyle.DAMAGE_LIGHT
                    active_captions.append((f"-{ev.amount}", dmg_style, frame_no, (victim_x, victim_y)))
                    # Crit additionally fires the centered "CRITICAL HIT!" big banner
                    if ev.extra.get("crit"):
                        active_captions.append(("CRITICAL HIT!", CaptionStyle.CRIT, frame_no, None))
                else:
                    # ULTIMATE_START and KO use the system style/text and centered position
                    style = _caption_style_for_event(ev)
                    text = _caption_text_for_event(ev)
                    active_captions.append((text, style, frame_no, None))
            # Screen shake + particles + hit-stop + HUD record + (CD-skill: projectile)
            if ev.type is EventType.HIT:
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 80
                actor_char = left if ev.actor == left.id else right
                attacker_x = int(actor_char.pos_x)
                attacker_y = int(actor_char.pos_y) - 80

                st = ev.extra.get("skill_type", "basic")
                skill_id = ev.extra.get("skill_id", "")
                is_crit = bool(ev.extra.get("crit"))
                color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))

                if st == "cooldown":
                    # Deferred particle burst until projectile lands.
                    count = int((10 + int(ev.amount)) * 1.8)
                    speed = (6.0 + ev.amount * 0.2) * 1.3
                    shape = "screw" if skill_id == "screw_dart" else "shard"

                    def _land_callback(tx=target_x, ty=target_y, c=color,
                                        ct=count, sp=speed, tgt=ev.target):
                        renderer.particles.emit_hit_burst(tx, ty,
                                                           color=c,
                                                           count=ct, speed=sp)
                        renderer.add_shake(4.0)
                        renderer.request_hit_stop(2)
                        renderer.add_char_flash(tgt, 1.0)

                    renderer.projectiles.spawn(
                        x_start=attacker_x, y_start=attacker_y,
                        x_end=target_x,    y_end=target_y,
                        shape=shape, color=color, lifetime=8,
                        on_land=_land_callback,
                    )
                else:
                    # Basic / special: immediate particle burst
                    count = 10 + int(ev.amount)
                    speed = 6.0 + ev.amount * 0.2
                    renderer.particles.emit_hit_burst(target_x, target_y,
                                                       color=color,
                                                       count=count, speed=speed)
                    if is_crit:
                        renderer.add_shake(8.0)
                        renderer.request_hit_stop(4)
                    elif st == "special":
                        renderer.add_shake(5.0)
                        renderer.request_hit_stop(3)
                    else:
                        renderer.add_shake(3.0)
                    renderer.add_char_flash(ev.target, 1.0)

                # Skill-name banner for non-basic hits
                banner_color = _BANNER_COLOR_BY_SKILL_TYPE.get(st)
                banner_text = _SKILL_BANNER_NAME.get(skill_id)
                if banner_color and banner_text:
                    renderer.banners.spawn(banner_text, banner_color)

                # Record into HUD (popup + DPS) — fires immediately on HIT regardless
                renderer.hud.record_hit(
                    actor_id=ev.actor,
                    dmg=ev.amount,
                    is_crit=is_crit,
                    target_x=target_x,
                    target_y=target_y,
                    t_ms=battle.elapsed_ms,
                )
            elif ev.type is EventType.ULTIMATE_START:
                renderer.add_shake(12.0)
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 80
                renderer.particles.emit_ultimate_burst(target_x, target_y)
                renderer.request_hit_stop(5)
                # Skill-name banner for the ultimate
                ult_skill_id = ev.extra.get("skill_id") or ev.extra.get("anim", "")
                banner_text = _SKILL_BANNER_NAME.get(ult_skill_id)
                if banner_text:
                    renderer.banners.spawn(banner_text, (255, 220, 80))
            elif ev.type is EventType.KO:
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 60
                renderer.particles.emit_ko_burst(target_x, target_y)
                renderer.add_shake(10.0)

        if battle.state is BattleState.ULTIMATE_PLAYING:
            ult_event = next(
                (e for e in reversed(battle.events) if e.type is EventType.ULTIMATE_START),
                None,
            )
            if ult_event:
                anim_name = ult_event.extra.get("anim", "indestructible_throw")
                attacker = left if ult_event.actor == left.id else right
                defender = right if attacker is left else left
                play_cinematic_frame(renderer.surface, anim_name,
                                     int(cinematic_frame_idx),
                                     attacker=attacker, defender=defender)
                cinematic_frame_idx += 0.5  # half-speed — ~6s cinematic
        else:
            cinematic_frame_idx = 0.0
            la = _animation_for_actor(left)
            ra = _animation_for_actor(right)
            renderer.render_frame(left, right, la, ra, anim_frame=frame_no % 8,
                                   elapsed_ms=battle.elapsed_ms)

        active_captions = [
            (txt, sty, start, pos) for (txt, sty, start, pos) in active_captions
            if frame_no - start < 45
        ]
        for (txt, sty, start, pos) in active_captions:
            draw_caption(renderer.surface, txt, sty, frame_in_anim=frame_no - start, pos=pos)

        recorder.write_frame(renderer.surface)
        frame_no += 1

    # Hold final 30 frames
    for hold_frame in range(30):
        renderer.render_frame(left, right, _animation_for_actor(left), _animation_for_actor(right), anim_frame=hold_frame, elapsed_ms=battle.elapsed_ms)
        active_captions = [(txt, sty, start, pos) for (txt, sty, start, pos) in active_captions if frame_no - start < 45]
        for (txt, sty, start, pos) in active_captions:
            draw_caption(renderer.surface, txt, sty, frame_in_anim=frame_no - start, pos=pos)
        recorder.write_frame(renderer.surface)
        frame_no += 1

    # Result screen — 180 frames (3s at 60fps)
    if right.is_ko() or left.is_ko():
        winner_char = left if right.is_ko() else right
        loser_char = right if right.is_ko() else left
        hits_landed = sum(1 for e in battle.events
                          if e.type is EventType.HIT and e.actor == winner_char.id)
        ults_used = sum(1 for e in battle.events
                        if e.type is EventType.ULTIMATE_START and e.actor == winner_char.id)
        match_seconds = battle.elapsed_ms / 1000

        for result_frame in range(180):
            _draw_result_screen(
                renderer,
                winner_char=winner_char,
                loser_char=loser_char,
                hits=hits_landed,
                ults=ults_used,
                match_seconds=match_seconds,
                frame=result_frame,
            )
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

    total_ms = (INTRO_FRAMES * TICK_MS) + battle.elapsed_ms + (30 * TICK_MS) + (180 * TICK_MS)
    intro_offset_ms = INTRO_FRAMES * TICK_MS
    build_audio_track(battle.events,
                      total_duration_ms=total_ms,
                      output_path=str(audio_out),
                      event_offset_ms=intro_offset_ms)
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
