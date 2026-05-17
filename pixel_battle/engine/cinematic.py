"""Cinematic ultimate sequences. Each cinematic = scripted frame-by-frame painter."""
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import math

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
    """0-30: brick walks toward defender (windup→strike); 30-60: brick ultimate_pose, defender
    lifted (ko_falling); 60-120: defender slammed down with ease; 120-180: defender ko_landed."""
    surface.fill((10, 10, 18))

    if frame < 30:
        # Brick approaches: use windup for first half, strike for second half
        progress = frame / 30
        ax = int(WIDTH * 0.25 + (WIDTH * 0.25) * progress)
        pose = "attack_windup" if frame < 15 else "attack_strike"
        _draw_sprite_at(surface, attacker, ax, HEIGHT // 2, pose, facing_right=True)
        _draw_sprite_at(surface, defender, int(WIDTH * 0.75), HEIGHT // 2, "idle", facing_right=False)

    elif frame < 60:
        # Brick grabs: attacker in ultimate_pose; defender ko_falling being lifted overhead
        progress = (frame - 30) / 30
        ax = WIDTH // 2 - 60
        dy = int(HEIGHT // 2 - 200 * progress)
        _draw_sprite_at(surface, attacker, ax, HEIGHT // 2, "ultimate_pose", facing_right=True)
        _draw_sprite_at(surface, defender, WIDTH // 2 + 60, dy, "ko_falling", facing_right=False)

    elif frame < 120:
        # Defender slammed down with eased motion
        progress = (frame - 60) / 60
        ease = progress * progress
        ax = WIDTH // 2 - 60
        dy = int(HEIGHT // 2 - 200 + (260 * ease))
        _draw_sprite_at(surface, attacker, ax, HEIGHT // 2, "ultimate_pose", facing_right=True)
        _draw_sprite_at(surface, defender, WIDTH // 2 + 60, dy, "ko_falling", facing_right=False)
        # Ghost trail near impact
        if 90 <= frame < 100:
            _draw_sprite_at(surface, defender, WIDTH // 2 + 60, dy - 30, "ko_falling",
                            facing_right=False, alpha=80)

    else:
        # Defender ko_landed on ground; dust particles
        progress = (frame - 120) / 60
        ax = WIDTH // 2 - 60
        _draw_sprite_at(surface, attacker, ax, HEIGHT // 2, "ultimate_pose", facing_right=True)
        _draw_sprite_at(surface, defender, WIDTH // 2 + 60, int(HEIGHT // 2 + 60), "ko_landed",
                        facing_right=False)
        for i in range(8):
            cx = WIDTH // 2 + 60 + (i - 4) * 18
            cy = HEIGHT // 2 + 60 + int(progress * 30)
            pygame.draw.circle(surface, (200, 200, 200), (cx, cy), max(1, 6 - int(progress * 6)))


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
            CinematicEvent(frame=30, type="screen_shake", payload={"intensity": 3}),
            CinematicEvent(frame=60, type="caption", payload={"text": "INDESTRUCTIBLE"}),
            CinematicEvent(frame=80, type="screen_shake", payload={"intensity": 8}),
            CinematicEvent(frame=120, type="caption", payload={"text": "THROW!"}),
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
