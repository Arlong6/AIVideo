"""Script-driven 30s highlight reel with per-frame motion. No physics, no AI —
but every shot has slide-ins, shakes, breathing, particles, damage float-ups.
"""
from __future__ import annotations
import math
import os
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
import yaml  # noqa: E402

from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.video.audio_mixer import AudioMixer  # noqa: E402
from pixel_battle.video.compose import (  # noqa: E402
    _load_wav, _loop_to_length,
    _load_sfx_samples_or_none,
    mux_audio_video,
    BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS

ROOT = Path(__file__).resolve().parents[1]
SPRITES_DIR = ROOT / "assets" / "sprites"
OUT_DIR = ROOT / "output" / "highlight_reel"

BG_COLOR = (18, 22, 40)
BANNER_YELLOW = (255, 220, 100)
CRIT_RED = (255, 80, 80)
DMG_ORANGE = (255, 170, 80)
WHITE = (240, 240, 240)


@dataclass
class Shot:
    t: float
    duration: float
    type: str
    char: Optional[str] = None
    pose: Optional[str] = None
    text: Optional[str] = None
    name: Optional[str] = None
    banner: Optional[str] = None
    sfx: Optional[str] = None
    dmg: Optional[int] = None
    crit: bool = False
    color: Optional[str] = None
    screen_flash: bool = False
    enter_from: str = "left"  # "left" | "right" | "none"


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float  # remaining seconds
    color: Tuple[int, int, int]
    radius: float


def load_script(path: Path) -> Tuple[float, List[Shot]]:
    cfg = yaml.safe_load(path.read_text())
    return float(cfg.get("duration_s", 30)), [Shot(**s) for s in cfg["shots"]]


def active_shot(shots: List[Shot], t_s: float) -> Optional[Shot]:
    for s in shots:
        if s.t <= t_s < (s.t + s.duration):
            return s
    return None


def hex_to_rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t ** 3


def _pick_font(size: int) -> pygame.font.Font:
    for name in ("Arial Black", "Impact", "Helvetica Neue",
                 "Helvetica", "Arial"):
        path = pygame.font.match_font(name, bold=True)
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, size)


def _outlined(font, text, color, outline_w=3, outline_color=(0, 0, 0)):
    base = font.render(text, True, color)
    w, h = base.get_size()
    surf = pygame.Surface((w + 2 * outline_w, h + 2 * outline_w),
                          pygame.SRCALPHA)
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx == 0 and dy == 0:
                continue
            outline = font.render(text, True, outline_color)
            surf.blit(outline, (dx + outline_w, dy + outline_w))
    surf.blit(base, (outline_w, outline_w))
    return surf


def _load_sprite(char: str, pose: str, cache: dict) -> Optional[pygame.Surface]:
    key = (char, pose)
    if key not in cache:
        p = SPRITES_DIR / char / f"{pose}.png"
        if not p.exists():
            cache[key] = None
        else:
            img = pygame.image.load(str(p)).convert_alpha()
            cache[key] = img
    return cache[key]


def draw_background(surf, t_global: float, hit_pulse: float = 0.0):
    base = list(BG_COLOR)
    if hit_pulse > 0:
        boost = int(40 * hit_pulse)
        base = [min(255, c + boost) for c in base]
    surf.fill(tuple(base))


def blit_sprite(surf, sprite, scale: float, offset: Tuple[float, float],
                shake_px: float = 0.0):
    if sprite is None:
        return
    w, h = sprite.get_size()
    nw, nh = int(w * scale), int(h * scale)
    scaled = pygame.transform.scale(sprite, (nw, nh))
    sx = random.uniform(-shake_px, shake_px) if shake_px > 0 else 0
    sy = random.uniform(-shake_px, shake_px) if shake_px > 0 else 0
    x = (WIDTH - nw) // 2 + int(offset[0]) + int(sx)
    y = (HEIGHT - nh) // 2 + int(offset[1]) + int(sy)
    surf.blit(scaled, (x, y))


def draw_vs_title(surf, fonts, t_local: float, duration: float):
    # Two halves slide in from sides, "vs" pops in middle
    progress = min(1.0, t_local / 0.5)
    eased = ease_out_cubic(progress)
    title = _outlined(fonts["huge"], "BRICK", BANNER_YELLOW, outline_w=4)
    bottom = _outlined(fonts["huge"], "GLASS", (180, 220, 255), outline_w=4)
    vs_scale = 0.5 + ease_out_cubic(max(0, t_local - 0.4) / 0.3) * 0.5
    vs_base = _outlined(fonts["title"], "vs", WHITE, outline_w=3)
    vs = pygame.transform.scale(
        vs_base,
        (int(vs_base.get_width() * vs_scale),
         int(vs_base.get_height() * vs_scale))
    )

    center_y = HEIGHT // 2
    brick_x_off = int((1 - eased) * -WIDTH)
    glass_x_off = int((1 - eased) * WIDTH)
    surf.blit(title, ((WIDTH - title.get_width()) // 2 + brick_x_off,
                       center_y - 140))
    surf.blit(bottom, ((WIDTH - bottom.get_width()) // 2 + glass_x_off,
                        center_y + 50))
    surf.blit(vs, ((WIDTH - vs.get_width()) // 2,
                    center_y - vs.get_height() // 2))


def draw_intro(surf, fonts, shot: Shot, sprite, t_local: float):
    # Sprite slides in from side; bobs slightly while held
    progress = min(1.0, t_local / 0.35)
    eased = ease_out_cubic(progress)
    bob = math.sin(t_local * 5.0) * 3.0
    enter_dir = -WIDTH if shot.enter_from == "left" else WIDTH
    x_off = int((1 - eased) * enter_dir)
    blit_sprite(surf, sprite, scale=0.85, offset=(x_off, bob))
    if shot.name:
        color = hex_to_rgb(shot.color) if shot.color else WHITE
        name_surf = _outlined(fonts["title"], shot.name, color, outline_w=3)
        # Name slides up from below
        name_progress = max(0, min(1, (t_local - 0.15) / 0.3))
        name_y_off = int((1 - ease_out_cubic(name_progress)) * 60)
        surf.blit(
            name_surf,
            ((WIDTH - name_surf.get_width()) // 2,
             HEIGHT - 140 + name_y_off),
        )


def draw_action_shot(surf, fonts, shot: Shot, sprite, t_local: float,
                     particles: List[Particle]):
    """Action/hit shot with motion. Different behavior by pose."""
    # Decide which animation by pose
    pose = shot.pose or ""

    if pose == "hit_recoil":
        # Shake hard for first 0.3s, then settle
        shake_t = max(0, 1 - t_local / 0.3)
        shake_px = 12 * shake_t
        # Slight backward push (away from center)
        push = -ease_in_cubic(min(1, t_local / 0.3)) * 30
        # Recover toward center after 0.3s
        if t_local > 0.3:
            push = -30 * (1 - ease_out_cubic(min(1, (t_local - 0.3) / 0.5)))
        offset = (push if shot.char == "brick_phone" else -push, 0)
        blit_sprite(surf, sprite, scale=0.75, offset=offset, shake_px=shake_px)

    elif pose in ("ko_falling",):
        # Drift downward + rotate slightly
        y_drop = ease_in_cubic(t_local / shot.duration) * 100
        blit_sprite(surf, sprite, scale=0.75, offset=(0, y_drop))

    elif pose == "ultimate_pose":
        # Zoom in / pulse glow
        zoom = 0.7 + ease_out_cubic(min(1, t_local / 0.6)) * 0.25
        bob = math.sin(t_local * 8.0) * 2.0
        blit_sprite(surf, sprite, scale=zoom, offset=(0, bob))

    elif pose == "special_charge":
        # Subtle vibrate building up
        shake_t = min(1, t_local / shot.duration)
        shake_px = 2 + shake_t * 5
        scale = 0.75 + 0.05 * math.sin(t_local * 14)
        blit_sprite(surf, sprite, scale=scale, offset=(0, 0),
                    shake_px=shake_px)

    elif pose == "attack_strike":
        # Slide in fast then settle
        progress = min(1.0, t_local / 0.2)
        eased = ease_out_cubic(progress)
        enter_dir = -WIDTH * 0.6 if shot.char == "brick_phone" else WIDTH * 0.6
        x_off = int((1 - eased) * enter_dir)
        # Add small forward push after slide-in
        forward = ease_out_cubic(max(0, (t_local - 0.2) / 0.3)) * 20
        if shot.char == "glass_slab":
            forward = -forward
        blit_sprite(surf, sprite, scale=0.78, offset=(x_off + forward, 0))

    elif pose == "ko_landed":
        # Sit on ground; "dizzy stars" subtle bob
        bob = math.sin(t_local * 3.0) * 1.5
        blit_sprite(surf, sprite, scale=0.75, offset=(0, 50 + bob))

    else:
        # Default: gentle breathing bob
        bob = math.sin(t_local * 4.0) * 2.0
        blit_sprite(surf, sprite, scale=0.75, offset=(0, bob))

    # Banner: slide in from left, hold, slide out at end
    if shot.banner:
        b = _outlined(fonts["banner"], shot.banner, BANNER_YELLOW, outline_w=3)
        progress = min(1.0, t_local / 0.25)
        slide = ease_out_cubic(progress)
        # Slide out in last 0.3s of shot
        time_left = shot.duration - t_local
        if time_left < 0.3:
            slide *= ease_out_cubic(time_left / 0.3)
        x = int((1 - slide) * -WIDTH) + (WIDTH - b.get_width()) // 2
        surf.blit(b, (x, 90))

    # Damage number: float up + fade
    if shot.dmg:
        is_crit = shot.crit
        color = CRIT_RED if is_crit else DMG_ORANGE
        if is_crit:
            crit_surf = _outlined(fonts["title"], "CRITICAL HIT!",
                                   CRIT_RED, outline_w=3)
            # Quick zoom-in
            scale = 0.5 + ease_out_cubic(min(1, t_local / 0.2)) * 0.5
            cs = pygame.transform.scale(
                crit_surf,
                (int(crit_surf.get_width() * scale),
                 int(crit_surf.get_height() * scale)),
            )
            float_y = -t_local * 30
            alpha = max(0, int(255 * (1 - t_local / shot.duration)))
            cs.set_alpha(alpha)
            surf.blit(cs, ((WIDTH - cs.get_width()) // 2,
                            int(HEIGHT - 220 + float_y)))

        dmg_font = fonts["huge"] if is_crit else fonts["banner"]
        dmg = _outlined(dmg_font, f"-{shot.dmg}", color, outline_w=3)
        # Float up + fade out
        float_y = -t_local * 50
        alpha = max(0, int(255 * (1 - t_local / shot.duration)))
        dmg.set_alpha(alpha)
        surf.blit(dmg, ((WIDTH - dmg.get_width()) // 2,
                          int(HEIGHT - 150 + float_y)))


def draw_result(surf, fonts, shot: Shot, t_local: float):
    lines = (shot.text or "").split("\n")
    line_h = fonts["huge"].get_height() + 14
    total_h = line_h * len(lines)
    y_start = (HEIGHT - total_h) // 2
    # Scale in
    overall_progress = min(1.0, t_local / 0.5)
    scale = 0.6 + ease_out_cubic(overall_progress) * 0.4
    pulse = 1.0 + math.sin(t_local * 4.0) * 0.04
    for i, line in enumerate(lines):
        rendered = _outlined(fonts["huge"], line, BANNER_YELLOW, outline_w=4)
        s = pygame.transform.scale(
            rendered,
            (int(rendered.get_width() * scale * pulse),
             int(rendered.get_height() * scale * pulse)),
        )
        y = y_start + i * line_h
        surf.blit(s, ((WIDTH - s.get_width()) // 2, y))


def draw_screen_flash(surf, t_local: float, duration: float = 0.2,
                      alpha: int = 200):
    if t_local < 0 or t_local >= duration:
        return
    fade = 1.0 - (t_local / duration)
    a = int(alpha * fade)
    overlay = pygame.Surface((WIDTH, HEIGHT))
    overlay.fill((255, 255, 255))
    overlay.set_alpha(a)
    surf.blit(overlay, (0, 0))


def spawn_hit_particles(particles: List[Particle], color, count: int = 12):
    cx, cy = WIDTH // 2, HEIGHT // 2
    for _ in range(count):
        angle = random.uniform(0, math.tau)
        speed = random.uniform(120, 280)
        particles.append(Particle(
            x=cx, y=cy,
            vx=math.cos(angle) * speed,
            vy=math.sin(angle) * speed,
            life=random.uniform(0.3, 0.6),
            color=color,
            radius=random.uniform(2, 5),
        ))


def update_and_draw_particles(surf, particles: List[Particle], dt: float):
    survivors = []
    for p in particles:
        p.x += p.vx * dt
        p.y += p.vy * dt
        p.vy += 400 * dt  # gravity
        p.life -= dt
        if p.life > 0:
            alpha = max(0, min(255, int(255 * (p.life / 0.5))))
            r, g, b = p.color
            pygame.draw.circle(surf, (r, g, b), (int(p.x), int(p.y)),
                                max(1, int(p.radius)))
            survivors.append(p)
    particles[:] = survivors


# --- Audio routing ---
CAST_SFX = {"cast_cooldown", "cast_special"}
HIT_SFX = {"hit", "crit", "ko"}


def route_sfx(mixer: AudioMixer, name: str, t_ms: int):
    samp = _load_sfx_samples_or_none(name, mixer.sr)
    if samp is None:
        return
    if name in HIT_SFX:
        mixer.hit_bus.add(samp, t_ms)
    elif name in CAST_SFX:
        mixer.cast_bus.add(samp, t_ms)
    else:
        mixer.ult_bus.add(samp, t_ms)


# --- Main ---

def main():
    pygame.init()
    pygame.display.set_mode((1, 1))
    pygame.font.init()
    random.seed(42)  # deterministic shake/particles

    fonts = {
        "huge": _pick_font(56),
        "title": _pick_font(40),
        "banner": _pick_font(32),
    }

    script_path = ROOT / "data" / "highlight_30s.yaml"
    duration_s, shots = load_script(script_path)
    total_frames = int(duration_s * FPS)
    total_duration_ms = int(total_frames * FRAME_MS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()

    sprite_cache: dict = {}
    particles: List[Particle] = []

    mixer = AudioMixer(sample_rate=48000)
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    for s in shots:
        if s.sfx:
            route_sfx(mixer, s.sfx, int(s.t * 1000))

    surf = pygame.Surface((WIDTH, HEIGHT))
    fired_particles_for: set = set()
    dt = 1.0 / FPS

    for frame in range(total_frames):
        t_s = frame / FPS
        shot = active_shot(shots, t_s)
        t_local = (t_s - shot.t) if shot else 0.0

        # Brief background pulse on hit events (first 0.15s of any hit_recoil shot)
        hit_pulse = 0.0
        if shot and shot.pose == "hit_recoil" and t_local < 0.15:
            hit_pulse = 1.0 - t_local / 0.15

        draw_background(surf, t_global=t_s, hit_pulse=hit_pulse)

        if shot is None:
            pass
        elif shot.type == "vs_title":
            draw_vs_title(surf, fonts, t_local, shot.duration)
        elif shot.type == "intro":
            sprite = _load_sprite(shot.char, shot.pose, sprite_cache)
            draw_intro(surf, fonts, shot, sprite, t_local)
        elif shot.type == "shot":
            sprite = _load_sprite(shot.char, shot.pose, sprite_cache)
            draw_action_shot(surf, fonts, shot, sprite, t_local, particles)
            # Spawn particles on first frame of hit_recoil shots
            shot_key = id(shot)
            if (shot.pose == "hit_recoil"
                    and shot_key not in fired_particles_for):
                fired_particles_for.add(shot_key)
                color = CRIT_RED if shot.crit else DMG_ORANGE
                spawn_hit_particles(particles, color,
                                     count=20 if shot.crit else 12)
        elif shot.type == "result":
            draw_result(surf, fonts, shot, t_local)

        # Particles always drawn after sprite
        update_and_draw_particles(surf, particles, dt)

        # Screen flash (ultimate shots)
        if shot and shot.screen_flash:
            draw_screen_flash(surf, t_local, duration=0.18, alpha=180)

        recorder.write_frame(surf)

    recorder.stop()
    print(f"  video frames: {total_frames}")

    mixer.export(total_duration_ms, str(audio_out))
    print(f"  audio: {audio_out}")

    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ Highlight reel: {final_mp4} ({duration_s}s)")


if __name__ == "__main__":
    main()
