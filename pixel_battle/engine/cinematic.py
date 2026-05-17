"""Cinematic ultimate sequences. Each cinematic = scripted frame-by-frame painter."""
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import math
import random as _r

import pygame

from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import (
    WIDTH, HEIGHT, BG_COLOR, CHAR_W, CHAR_H,
)

# ---------------------------------------------------------------------------
# Sprite helpers (lazy to avoid circular imports at load time)
# ---------------------------------------------------------------------------

_sprite_cache: Dict[str, object] = {}


def _sprites_for(char: Character):
    if char.id not in _sprite_cache:
        from pixel_battle.engine.animator import CharacterSprites
        _sprite_cache[char.id] = CharacterSprites(char.id)
    return _sprite_cache[char.id]


def _draw_sprite_at(
    surface,
    char: Character,
    center_x: int,
    center_y: int,
    pose: str,
    facing_right: bool = True,
    alpha: int = 255,
) -> None:
    """Blit a character's sprite pose centered at (center_x, center_y)."""
    sprites = _sprites_for(char)
    s = sprites.get_pose(pose)
    if not facing_right:
        s = pygame.transform.flip(s, True, False)
    if alpha < 255:
        s = s.copy()
        s.set_alpha(alpha)
    rect = s.get_rect(center=(center_x, center_y))
    surface.blit(s, rect)


# ---------------------------------------------------------------------------
# CinematicEvent / CinematicSpec
# ---------------------------------------------------------------------------


@dataclass
class CinematicEvent:
    frame: int
    type: str
    payload: dict = field(default_factory=dict)


@dataclass
class CinematicSpec:
    name: str
    total_frames: int
    events: List[CinematicEvent]
    painter: Callable


# ---------------------------------------------------------------------------
# Painters
# ---------------------------------------------------------------------------

def _brick_throw_painter(surface, frame: int, attacker: Character, defender: Character) -> None:
    """Anime-style ultimate: charge → sky launch → spin-kick → meteor descent → shockwave.

    Frames 0-180 (6s at 30fps):
      0-25:   Charge with dust whirlwind + earth shake
      25-55:  Brick launches skyward, defender on ground watching
      55-80:  Spin-kick at apex — defender is sky-high too
      80-115: Meteor descent — both spiraling, sky tints red/purple, speed lines
      115-135: IMPACT — shockwave + massive flash + particles
      135-180: Aftermath — Brick standing on crater
    """
    atk_x_floor = int(WIDTH * 0.25)
    def_x_floor = int(WIDTH * 0.75)
    ground_y = HEIGHT - 200  # rough ground line; characters stand here

    # Default fill — overridden per phase
    surface.fill((10, 10, 18))

    if frame < 25:
        # Phase 1: Charge — dust whirlwind around brick's feet, earth shake
        _draw_sprite_at(surface, attacker, atk_x_floor, ground_y, "special_charge", facing_right=True)
        _draw_sprite_at(surface, defender, def_x_floor, ground_y, "idle", facing_right=False)
        # Dust whirlwind: rotating particles around brick's feet
        for i in range(8):
            ang = (frame * 0.4) + (i / 8) * 2 * math.pi
            radius = 40 + (frame * 1.5) % 30
            dx = int(math.cos(ang) * radius)
            dy = int(math.sin(ang) * radius * 0.3)
            pygame.draw.circle(surface, (200, 180, 140),
                               (atk_x_floor + dx, ground_y + 70 + dy), 4)
        # Earth shake lines
        for i in range(3):
            shake_y = HEIGHT - 80 - i * 20
            for x in range(0, WIDTH, 60):
                pygame.draw.line(surface, (120, 80, 60),
                                 (x + _r.randint(-4, 4), shake_y),
                                 (x + 30 + _r.randint(-4, 4), shake_y), 2)

    elif frame < 55:
        # Phase 2: Brick launches skyward
        progress = (frame - 25) / 30  # 0 → 1
        # Brick rises off-screen
        brick_y = int(ground_y - 600 * progress)
        # Trail behind brick
        for trail in range(5):
            trail_y = brick_y + trail * 30
            trail_alpha = max(0, 200 - trail * 40)
            trail_surf = pygame.Surface((40, 40), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, (255, 220, 100, trail_alpha), (20, 20), 18 - trail * 3)
            surface.blit(trail_surf, (atk_x_floor - 20, trail_y - 20))
        _draw_sprite_at(surface, attacker, atk_x_floor, brick_y, "ultimate_pose", facing_right=True)
        # Defender on ground, looking up (hit_recoil shows surprise)
        _draw_sprite_at(surface, defender, def_x_floor, ground_y, "hit_recoil", facing_right=False)

    elif frame < 80:
        # Phase 3: Brick at apex meets defender (defender appears sky-high too — kicked up)
        progress = (frame - 55) / 25
        # Both characters mid-air, center of screen
        cy = HEIGHT // 3
        # Brick is on right side now (spinning around), defender on left
        # Add rotational position for drama
        angle = progress * math.pi * 2
        brick_off_x = int(math.cos(angle) * 60)
        def_off_x = int(math.cos(angle + math.pi) * 60)
        # Background flash
        flash_alpha = int(200 * (1 - progress))
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 240, 200, flash_alpha))
        surface.blit(flash, (0, 0))
        _draw_sprite_at(surface, attacker, WIDTH // 2 + brick_off_x, cy,
                        "ultimate_pose", facing_right=True)
        _draw_sprite_at(surface, defender, WIDTH // 2 + def_off_x, cy + 30,
                        "ko_falling", facing_right=False)
        # Speed lines radiating from center
        for i in range(12):
            line_ang = (i / 12) * 2 * math.pi + progress * 0.5
            r1 = 80
            r2 = 250
            x1 = WIDTH // 2 + int(math.cos(line_ang) * r1)
            y1 = cy + int(math.sin(line_ang) * r1)
            x2 = WIDTH // 2 + int(math.cos(line_ang) * r2)
            y2 = cy + int(math.sin(line_ang) * r2)
            pygame.draw.line(surface, (255, 255, 220), (x1, y1), (x2, y2), 2)

    elif frame < 115:
        # Phase 4: Meteor descent — sky tints red/purple
        progress = (frame - 80) / 35  # 0 → 1
        # Background gradient: red→dark purple
        for y in range(HEIGHT):
            t = y / HEIGHT
            r = int(60 + (180 - 60) * (1 - t) * (1 - progress * 0.5))
            g = int(20 + 30 * (1 - t))
            b = int(40 + (120 - 40) * t)
            pygame.draw.line(surface, (r, g, b), (0, y), (WIDTH, y))
        # Both characters falling — spiral
        cy_start = HEIGHT // 4
        cy_end = HEIGHT - 250
        cy = int(cy_start + (cy_end - cy_start) * progress)
        spiral_angle = progress * math.pi * 6
        brick_x = WIDTH // 2 + int(math.cos(spiral_angle) * 40)
        def_x = WIDTH // 2 + int(math.cos(spiral_angle + math.pi) * 40)
        # Flame trail behind brick
        for trail in range(8):
            trail_cy = cy - trail * 25
            if trail_cy < 0:
                continue
            trail_alpha = max(0, 220 - trail * 28)
            flame_color = (255, 180 - trail * 15, 60, trail_alpha)
            trail_surf = pygame.Surface((30, 30), pygame.SRCALPHA)
            pygame.draw.circle(trail_surf, flame_color, (15, 15), 12 - trail)
            surface.blit(trail_surf, (brick_x - 15, trail_cy - 15))
        _draw_sprite_at(surface, attacker, brick_x, cy, "ultimate_pose", facing_right=True)
        _draw_sprite_at(surface, defender, def_x, cy + 50, "ko_falling", facing_right=False)
        # Vertical speed lines
        for i in range(20):
            x = (i * WIDTH // 20 + frame * 4) % WIDTH
            pygame.draw.line(surface, (255, 255, 220), (x, 0), (x, HEIGHT), 1)

    elif frame < 135:
        # Phase 5: IMPACT — shockwave + massive flash
        progress = (frame - 115) / 20
        # White flash decaying
        flash_alpha = int(255 * (1 - progress))
        surface.fill((255, 250, 220))
        # Expanding shockwave ring
        ring_radius = int(80 + 250 * progress)
        ring_thickness = max(1, int(20 * (1 - progress)))
        pygame.draw.circle(surface, (255, 200, 100),
                           (WIDTH // 2, ground_y + 60), ring_radius, ring_thickness)
        # Inner shockwave
        if progress > 0.2:
            inner_r = int(100 * (progress - 0.2))
            pygame.draw.circle(surface, (255, 240, 180),
                               (WIDTH // 2, ground_y + 60), inner_r, 4)
        # Particles flying out from impact point
        for i in range(40):
            ang = (i / 40) * 2 * math.pi + progress * 0.3
            speed = 80 + (i % 7) * 30
            px = int(WIDTH // 2 + math.cos(ang) * speed * progress)
            py = int(ground_y + 60 + math.sin(ang) * speed * progress * 0.6)
            size = max(1, 4 - int(progress * 2))
            pygame.draw.circle(surface, (255, 180, 80), (px, py), size)
        # Brick centered atop crater, ultimate pose
        _draw_sprite_at(surface, attacker, WIDTH // 2, ground_y - 20,
                        "ultimate_pose", facing_right=True)
        # Decay overlay flash
        if flash_alpha > 0:
            decay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            decay.fill((255, 250, 200, flash_alpha))
            surface.blit(decay, (0, 0))

    else:
        # Phase 6: Aftermath — Brick standing on crater, Glass embedded
        progress = (frame - 135) / 45
        # Dim red/orange background
        for y in range(HEIGHT):
            t = y / HEIGHT
            r = int(80 - 30 * t - 30 * progress)
            g = int(30 - 10 * t)
            b = int(50 + 20 * t)
            pygame.draw.line(surface, (max(0, r), max(0, g), max(0, b)), (0, y), (WIDTH, y))
        # Crater on ground — dark ellipse
        crater_y = HEIGHT - 150
        crater_w = int(280 - progress * 20)
        crater_h = 60
        pygame.draw.ellipse(surface, (40, 25, 30),
                            (WIDTH // 2 - crater_w // 2, crater_y, crater_w, crater_h))
        pygame.draw.ellipse(surface, (80, 50, 60),
                            (WIDTH // 2 - crater_w // 2, crater_y, crater_w, crater_h), 4)
        # Glass embedded (ko_landed) inside crater
        _draw_sprite_at(surface, defender,
                        WIDTH // 2, crater_y + crater_h // 2 + 10,
                        "ko_landed", facing_right=False)
        # Brick standing tall above crater
        _draw_sprite_at(surface, attacker,
                        WIDTH // 2, crater_y - 100,
                        "ultimate_pose", facing_right=True)
        # Slowly rising smoke
        for i in range(6):
            smoke_x = WIDTH // 2 + (i - 3) * 40
            smoke_y = crater_y - int(progress * (60 + i * 10))
            smoke_alpha = max(0, 180 - int(progress * 200) - i * 10)
            if smoke_alpha > 0:
                smoke = pygame.Surface((40, 40), pygame.SRCALPHA)
                pygame.draw.circle(smoke, (200, 180, 160, smoke_alpha), (20, 20), 18)
                surface.blit(smoke, (smoke_x - 20, smoke_y - 20))


def _draw_block(surface, char: Character, center_x: int, center_y: int, w: int, h: int) -> None:
    """Rectangle fallback block (kept for the lock-screen panel helpers below)."""
    x = center_x - w // 2
    y = center_y - h // 2
    pygame.draw.rect(surface, char.color, (x, y, w, h), border_radius=10)
    sw, sh = max(4, w - 24), max(4, h - 60)
    pygame.draw.rect(surface, char.accent_color, (x + 12, y + 20, sw, sh), border_radius=4)


def _draw_block_color(surface, color, center_x: int, center_y: int, w: int, h: int) -> None:
    x = center_x - w // 2
    y = center_y - h // 2
    pygame.draw.rect(surface, color, (x, y, w, h), border_radius=10)


def _draw_lock_icon(surface, cx: int, cy: int, color=(255, 255, 255), size: int = 20) -> None:
    """Draw a closed padlock icon at (cx, cy)."""
    # Body (rectangle)
    body_w = size
    body_h = int(size * 0.7)
    body_rect = pygame.Rect(cx - body_w // 2, cy, body_w, body_h)
    pygame.draw.rect(surface, color, body_rect, border_radius=3)
    # Keyhole (small dark circle)
    pygame.draw.circle(surface, (20, 20, 30), (cx, cy + body_h // 2 - 2), max(1, size // 8))
    # Shackle (U-shape arc above body)
    shackle_r = body_w // 2 - 2
    shackle_cx = cx
    shackle_cy = cy
    # Draw an arc that goes from bottom-left through top to bottom-right
    pygame.draw.arc(surface, color,
                    (shackle_cx - shackle_r, shackle_cy - shackle_r,
                     shackle_r * 2, shackle_r * 2),
                    3.14, 2 * 3.14, 3)


def _draw_text(surface, text: str, pos, size: int = 16,
               color=(255, 255, 255), center: bool = False) -> None:
    """Draw text at pos. Lazy-init font."""
    if not pygame.font.get_init():
        pygame.font.init()
    font = pygame.font.Font(None, size)
    img = font.render(text, True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surface.blit(img, rect)


def _glass_force_update_painter(surface, frame: int, attacker: Character, defender: Character) -> None:
    """Force Update cinematic — Glass Slab's iOS-update ultimate.

    0-25:   charge up
    25-45:  WiFi waves stream toward defender
    45-55:  white flash impact
    55-110: iOS lock screen over defender, progress bar fills
    110-180: device locked, dim defender frozen
    """
    surface.fill((10, 10, 18))

    atk_x = int(WIDTH * 0.75)
    def_x = int(WIDTH * 0.25)
    mid_y = HEIGHT // 2

    if frame < 25:
        # Phase 1: Glass charges with brightening aura
        _draw_sprite_at(surface, attacker, atk_x, mid_y, "special_charge", facing_right=False)
        _draw_sprite_at(surface, defender, def_x, mid_y, "idle", facing_right=True)
        # Pulsing aura around glass
        aura_radius = 80 + int(frame * 2)
        aura_alpha = 60 + int(frame * 4)
        aura = pygame.Surface((aura_radius * 2, aura_radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(aura, (60, 180, 255, aura_alpha), (aura_radius, aura_radius), aura_radius)
        pygame.draw.circle(aura, (200, 240, 255, aura_alpha + 40), (aura_radius, aura_radius),
                           aura_radius // 2)
        surface.blit(aura, (atk_x - aura_radius, mid_y - aura_radius),
                     special_flags=pygame.BLEND_ADD)

    elif frame < 45:
        # Phase 2: Three Wi-Fi waves stream from Glass toward Brick
        _draw_sprite_at(surface, attacker, atk_x, mid_y, "ultimate_pose", facing_right=False)
        _draw_sprite_at(surface, defender, def_x, mid_y, "idle", facing_right=True)
        progress = (frame - 25) / 20  # 0 to 1
        for wave_i in range(3):
            wave_offset = (wave_i / 3) + progress  # each wave delayed
            if wave_offset > 1.0:
                continue
            cx = int(atk_x - (atk_x - def_x) * wave_offset)
            cy = mid_y
            wave_radius = 30 + int(wave_offset * 80)
            alpha = max(0, int(255 * (1 - wave_offset)))
            wave_surf = pygame.Surface((wave_radius * 2 + 4, wave_radius * 2 + 4), pygame.SRCALPHA)
            # Draw 3 concentric arc-like circles (just rings)
            for ring in range(3):
                ring_r = wave_radius - ring * 12
                if ring_r > 0:
                    pygame.draw.circle(wave_surf, (60 + ring * 50, 180, 255, alpha // (ring + 1)),
                                       (wave_radius + 2, wave_radius + 2), ring_r, 3)
            surface.blit(wave_surf, (cx - wave_radius - 2, cy - wave_radius - 2))

    elif frame < 55:
        # Phase 3: White flash impact
        flash_progress = (frame - 45) / 10
        flash_alpha = int(255 * (1 - flash_progress * 0.7))
        _draw_sprite_at(surface, attacker, atk_x, mid_y, "ultimate_pose", facing_right=False)
        _draw_sprite_at(surface, defender, def_x, mid_y, "hit_recoil", facing_right=True)
        flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        flash.fill((255, 255, 255, flash_alpha))
        surface.blit(flash, (0, 0))

    elif frame < 110:
        # Phase 4: iOS lock screen overlays brick
        _draw_sprite_at(surface, attacker, atk_x, mid_y, "ultimate_pose", facing_right=False)

        # Brick is faintly visible (very dim)
        _draw_sprite_at(surface, defender, def_x, mid_y, "ko_landed", facing_right=True)
        # Add RGB-glitch tint over defender area
        glitch = pygame.Surface((CHAR_W + 40, CHAR_H + 40), pygame.SRCALPHA)
        glitch.fill((0, 255, 80, 40))
        surface.blit(glitch, (def_x - CHAR_W // 2 - 20, mid_y - CHAR_H // 2 - 20),
                     special_flags=pygame.BLEND_ADD)

        # iOS lock screen panel
        panel_w, panel_h = 200, 320
        panel_x = def_x - panel_w // 2
        panel_y = mid_y - panel_h // 2
        # Black rounded panel with thin blue border (iOS style)
        pygame.draw.rect(surface, (0, 0, 0), (panel_x, panel_y, panel_w, panel_h), border_radius=24)
        pygame.draw.rect(surface, (60, 140, 255), (panel_x, panel_y, panel_w, panel_h),
                         width=2, border_radius=24)

        # Header: "iOS 17 UPDATE"
        _draw_text(surface, "iOS 17 UPDATE", (panel_x + panel_w // 2, panel_y + 30),
                   size=18, color=(255, 255, 255), center=True)

        # Lock icon (closed padlock)
        lock_cx = panel_x + panel_w // 2
        lock_cy = panel_y + 80
        _draw_lock_icon(surface, lock_cx, lock_cy, color=(100, 200, 255))

        # Progress bar: fills 0→100% over phase
        prog = (frame - 55) / 55  # 0 to 1
        bar_w, bar_h = panel_w - 40, 12
        bar_x = panel_x + 20
        bar_y = panel_y + 150
        pygame.draw.rect(surface, (40, 40, 60), (bar_x, bar_y, bar_w, bar_h), border_radius=6)
        pygame.draw.rect(surface, (80, 200, 100), (bar_x, bar_y, int(bar_w * prog), bar_h),
                         border_radius=6)
        # Percentage text
        _draw_text(surface, f"{int(prog * 100)}%", (panel_x + panel_w // 2, bar_y + 30),
                   size=20, color=(200, 220, 255), center=True)

        # "INSTALLING SECURITY PATCH" subtext
        _draw_text(surface, "INSTALLING SECURITY PATCH",
                   (panel_x + panel_w // 2, bar_y + 60),
                   size=14, color=(180, 180, 200), center=True)

        # iOS 8-dot spinner
        sp_cx = panel_x + panel_w // 2
        sp_cy = panel_y + panel_h - 50
        active_dot = (frame // 4) % 8
        for i in range(8):
            ang = (i / 8) * 2 * math.pi - math.pi / 2
            dx = int(20 * math.cos(ang))
            dy = int(20 * math.sin(ang))
            distance = (i - active_dot) % 8
            dot_alpha = max(50, 255 - distance * 30)
            dot = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(dot, (255, 255, 255, dot_alpha), (5, 5), 4)
            surface.blit(dot, (sp_cx + dx - 5, sp_cy + dy - 5))

    else:
        # Phase 5: Device locked — big red text
        _draw_sprite_at(surface, attacker, atk_x, mid_y, "ultimate_pose", facing_right=False)
        _draw_sprite_at(surface, defender, def_x, mid_y, "ko_landed", facing_right=True)

        # Black panel
        panel_w, panel_h = 220, 200
        panel_x = def_x - panel_w // 2
        panel_y = mid_y - panel_h // 2
        pygame.draw.rect(surface, (0, 0, 0), (panel_x, panel_y, panel_w, panel_h), border_radius=24)
        pygame.draw.rect(surface, (255, 50, 50), (panel_x, panel_y, panel_w, panel_h),
                         width=3, border_radius=24)

        # Big lock icon
        _draw_lock_icon(surface, panel_x + panel_w // 2, panel_y + 60,
                        color=(255, 80, 80), size=30)

        # "DEVICE LOCKED" red text
        _draw_text(surface, "DEVICE LOCKED",
                   (panel_x + panel_w // 2, panel_y + 130),
                   size=24, color=(255, 80, 80), center=True)


CINEMATICS: Dict[str, CinematicSpec] = {
    "indestructible_throw": CinematicSpec(
        name="indestructible_throw",
        total_frames=180,
        events=[
            CinematicEvent(frame=20, type="caption", payload={"text": "AWAKENING"}),
            CinematicEvent(frame=50, type="screen_shake", payload={"intensity": 4}),
            CinematicEvent(frame=70, type="caption", payload={"text": "SKY KICK"}),
            CinematicEvent(frame=110, type="caption", payload={"text": "METEOR"}),
            CinematicEvent(frame=120, type="screen_shake", payload={"intensity": 16}),
            CinematicEvent(frame=125, type="caption", payload={"text": "IMPACT!"}),
        ],
        painter=_brick_throw_painter,
    ),
}

CINEMATICS["force_update"] = CinematicSpec(
    name="force_update",
    total_frames=180,
    events=[
        CinematicEvent(frame=20, type="caption", payload={"text": "BROADCASTING"}),
        CinematicEvent(frame=45, type="flash", payload={"intensity": 255}),
        CinematicEvent(frame=50, type="caption", payload={"text": "FORCE UPDATE"}),
        CinematicEvent(frame=110, type="caption", payload={"text": "INSTALLING..."}),
        CinematicEvent(frame=140, type="caption", payload={"text": "DEVICE LOCKED"}),
    ],
    painter=_glass_force_update_painter,
)


def play_cinematic_frame(surface, name: str, frame: int, attacker: Character, defender: Character) -> None:
    if name not in CINEMATICS:
        raise KeyError(f"Cinematic not registered: {name}")
    spec = CINEMATICS[name]
    if frame >= spec.total_frames:
        frame = spec.total_frames - 1
    spec.painter(surface, frame, attacker, defender)
