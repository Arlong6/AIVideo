"""Cinematic ultimate sequences. Each cinematic = scripted frame-by-frame painter."""
from dataclasses import dataclass, field
from typing import Callable, Dict, List

import pygame

from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import (
    WIDTH, HEIGHT, BG_COLOR, CHAR_W, CHAR_H,
)


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


def _brick_throw_painter(surface, frame: int, attacker: Character, defender: Character) -> None:
    """0-30: grab approach; 30-60: lift overhead; 60-120: slam slow-mo; 120-180: dust."""
    surface.fill((10, 10, 18))

    if frame < 30:
        progress = frame / 30
        ax = int(WIDTH * 0.25 + (WIDTH * 0.25) * progress)
        _draw_block(surface, attacker, ax, HEIGHT // 2, CHAR_W, CHAR_H)
        _draw_block(surface, defender, int(WIDTH * 0.75), HEIGHT // 2, CHAR_W, CHAR_H)
    elif frame < 60:
        progress = (frame - 30) / 30
        ax = WIDTH // 2 - 60
        dx = WIDTH // 2 + 60
        dy = int(HEIGHT // 2 - 200 * progress)
        _draw_block(surface, attacker, ax, HEIGHT // 2, CHAR_W, CHAR_H)
        _draw_block(surface, defender, dx, dy, CHAR_W, CHAR_H)
    elif frame < 120:
        progress = (frame - 60) / 60
        ease = progress * progress
        ax = WIDTH // 2 - 60
        dy = int(HEIGHT // 2 - 200 + (260 * ease))
        _draw_block(surface, attacker, ax, HEIGHT // 2, CHAR_W, CHAR_H)
        _draw_block(surface, defender, WIDTH // 2 + 60, dy, CHAR_W, CHAR_H)
        if 90 <= frame < 100:
            ghost = pygame.Surface((CHAR_W, CHAR_H))
            ghost.set_alpha(80)
            ghost.fill(defender.color)
            surface.blit(ghost, (WIDTH // 2 + 60 - CHAR_W // 2, dy - 30))
    else:
        progress = (frame - 120) / 60
        ax = WIDTH // 2 - 60
        _draw_block(surface, attacker, ax, HEIGHT // 2, CHAR_W, CHAR_H)
        _draw_block(
            surface, defender, WIDTH // 2 + 60, int(HEIGHT // 2 + 60),
            CHAR_H, CHAR_W // 2,
        )
        for i in range(8):
            cx = WIDTH // 2 + 60 + (i - 4) * 18
            cy = HEIGHT // 2 + 60 + int(progress * 30)
            pygame.draw.circle(surface, (200, 200, 200), (cx, cy), max(1, 6 - int(progress * 6)))


def _draw_block(surface, char: Character, center_x: int, center_y: int, w: int, h: int) -> None:
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
    """0-30: glass charges up; 30-50: white flash; 50-130: lock screen overlay; 130-180: defender frozen."""
    surface.fill((10, 10, 18))

    if frame < 30:
        glow = min(255, 150 + frame * 3)
        glow_color = (glow // 2, glow, 255)
        _draw_block_color(surface, glow_color, int(WIDTH * 0.75), HEIGHT // 2, CHAR_W, CHAR_H)
        _draw_block(surface, defender, int(WIDTH * 0.25), HEIGHT // 2, CHAR_W, CHAR_H)
    elif frame < 50:
        progress = (frame - 30) / 20
        alpha = int(255 * (1 - progress))
        surface.fill((255, 255, 255))
        if progress > 0.5:
            _draw_block(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2, CHAR_W, CHAR_H)
    elif frame < 130:
        _draw_block(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2, CHAR_W, CHAR_H)
        panel_x, panel_y, panel_w, panel_h = 30, HEIGHT // 4, WIDTH - 60, HEIGHT // 2
        pygame.draw.rect(surface, (15, 15, 25), (panel_x, panel_y, panel_w, panel_h), border_radius=20)
        pygame.draw.rect(surface, (60, 130, 255), (panel_x, panel_y, panel_w, panel_h), width=3, border_radius=20)
        for i in range(3):
            by = panel_y + 60 + i * 50
            pygame.draw.rect(surface, (200, 200, 220), (panel_x + 40, by, panel_w - 80, 12), border_radius=4)
        sp_cx, sp_cy = WIDTH // 2, panel_y + panel_h - 80
        ang = (frame * 12) % 360
        import math
        ex = sp_cx + int(20 * math.cos(math.radians(ang)))
        ey = sp_cy + int(20 * math.sin(math.radians(ang)))
        pygame.draw.line(surface, (60, 200, 255), (sp_cx, sp_cy), (ex, ey), 4)
    else:
        _draw_block(surface, attacker, int(WIDTH * 0.75), HEIGHT // 2, CHAR_W, CHAR_H)
        gray_def_color = (90, 90, 100)
        _draw_block_color(surface, gray_def_color, int(WIDTH * 0.25), HEIGHT // 2, CHAR_W, CHAR_H)


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
