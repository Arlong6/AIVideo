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


def _glass_force_update_painter(surface, frame: int, attacker: Character, defender: Character) -> None:
    """0-30: glass special_charge glows; 30-50: white flash; 50-130: lock-screen panel over
    defender (hit_recoil→ko_landed after frame 80); 130-180: glass ultimate_pose, defender frozen."""
    surface.fill((10, 10, 18))

    if frame < 30:
        # Glass charges: special_charge sprite with brightening glow tint overlay
        _draw_sprite_at(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2,
                        "special_charge", facing_right=False)
        _draw_sprite_at(surface, defender, int(WIDTH * 0.25), HEIGHT // 2,
                        "idle", facing_right=True)
        # Glow overlay on attacker
        glow = min(255, 150 + frame * 3)
        glow_surf = pygame.Surface((CHAR_W, CHAR_H), pygame.SRCALPHA)
        glow_surf.fill((glow // 4, glow // 2, glow, 60))
        surface.blit(glow_surf, (int(WIDTH * 0.75) - CHAR_W // 2, HEIGHT // 2 - CHAR_H // 2))

    elif frame < 50:
        # White flash fade-in
        progress = (frame - 30) / 20
        surface.fill((255, 255, 255))
        if progress > 0.5:
            _draw_sprite_at(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2,
                            "ultimate_pose", facing_right=False)

    elif frame < 130:
        # Lock-screen panel: attacker ultimate_pose in background; defender behind UI panel
        _draw_sprite_at(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2,
                        "ultimate_pose", facing_right=False)
        def_pose = "hit_recoil" if frame < 80 else "ko_landed"
        _draw_sprite_at(surface, defender, int(WIDTH * 0.25), HEIGHT // 2,
                        def_pose, facing_right=True)
        # Lock-screen UI panel drawn on top of defender
        panel_x, panel_y, panel_w, panel_h = 30, HEIGHT // 4, WIDTH - 60, HEIGHT // 2
        pygame.draw.rect(surface, (15, 15, 25), (panel_x, panel_y, panel_w, panel_h), border_radius=20)
        pygame.draw.rect(surface, (60, 130, 255), (panel_x, panel_y, panel_w, panel_h), width=3, border_radius=20)
        for i in range(3):
            by = panel_y + 60 + i * 50
            pygame.draw.rect(surface, (200, 200, 220), (panel_x + 40, by, panel_w - 80, 12), border_radius=4)
        sp_cx, sp_cy = WIDTH // 2, panel_y + panel_h - 80
        ang = (frame * 12) % 360
        ex = sp_cx + int(20 * math.cos(math.radians(ang)))
        ey = sp_cy + int(20 * math.sin(math.radians(ang)))
        pygame.draw.line(surface, (60, 200, 255), (sp_cx, sp_cy), (ex, ey), 4)

    else:
        # Defender frozen (ko_landed); attacker ultimate_pose
        _draw_sprite_at(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2,
                        "ultimate_pose", facing_right=False)
        _draw_sprite_at(surface, defender, int(WIDTH * 0.25), HEIGHT // 2,
                        "ko_landed", facing_right=True)


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
        CinematicEvent(frame=20, type="caption", payload={"text": "SYSTEM ALERT"}),
        CinematicEvent(frame=35, type="flash", payload={"intensity": 255}),
        CinematicEvent(frame=60, type="caption", payload={"text": "FORCE UPDATE"}),
        CinematicEvent(frame=130, type="caption", payload={"text": "DEVICE LOCKED"}),
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
