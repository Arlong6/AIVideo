"""Floating caption overlays. Drawn directly onto a Pygame Surface."""
from dataclasses import dataclass
from enum import Enum

import pygame

from pixel_battle.engine.renderer import WIDTH, HEIGHT

DEFAULT_LIFETIME = 45  # frames at 60fps = 0.75s
FADE_IN = 6
FADE_OUT = 12


class CaptionStyle(Enum):
    HIT = "hit"
    CRIT = "crit"
    ULTIMATE = "ultimate"
    KO = "ko"
    INFO = "info"
    DAMAGE_LIGHT = "damage_light"   # small white floating number (damage ≤ 10)
    DAMAGE_HEAVY = "damage_heavy"   # bigger red number for damage > 10
    WINNER = "winner"               # result screen winner banner


_STYLES = {
    CaptionStyle.HIT: {"size": 36, "color": (240, 240, 240), "y": (HEIGHT // 3 + HEIGHT // 2) // 2},
    CaptionStyle.CRIT: {"size": 56, "color": (255, 90, 80), "y": (HEIGHT // 3 + HEIGHT // 2) // 2},
    CaptionStyle.ULTIMATE: {"size": 72, "color": (255, 220, 60), "y": (HEIGHT // 3 + HEIGHT // 2) // 2},
    CaptionStyle.KO: {"size": 96, "color": (255, 30, 30), "y": (HEIGHT // 3 + HEIGHT // 2) // 2},
    CaptionStyle.INFO: {"size": 28, "color": (200, 200, 220), "y": (HEIGHT // 3 + HEIGHT // 2) // 2},
    CaptionStyle.DAMAGE_LIGHT: {"size": 32, "color": (240, 240, 240), "y": HEIGHT // 3},
    CaptionStyle.DAMAGE_HEAVY: {"size": 48, "color": (255, 70, 70), "y": HEIGHT // 3},
    CaptionStyle.WINNER: {"size": 80, "color": (255, 220, 60), "y": HEIGHT // 3},
}


def draw_caption(surface, text: str, style: CaptionStyle, frame_in_anim: int,
                 lifetime: int = DEFAULT_LIFETIME,
                 pos: tuple | None = None) -> None:
    if frame_in_anim < 0 or frame_in_anim >= lifetime:
        return

    cfg = _STYLES[style]
    alpha = 255
    if frame_in_anim < FADE_IN:
        alpha = int(255 * (frame_in_anim / FADE_IN))
    elif frame_in_anim > lifetime - FADE_OUT:
        alpha = int(255 * ((lifetime - frame_in_anim) / FADE_OUT))

    y_offset = int(-20 * (frame_in_anim / lifetime))

    # Scale-pop animation: 0.3 → 1.3 (overshoot) → 1.0 (settle)
    if frame_in_anim < 6:
        t = frame_in_anim / 6
        scale = 0.3 + (1.3 - 0.3) * (1 - (1 - t) ** 2)  # ease-out
    elif frame_in_anim < 12:
        t = (frame_in_anim - 6) / 6
        scale = 1.3 + (1.0 - 1.3) * (1 - (1 - t) ** 2)
    else:
        scale = 1.0

    font = pygame.font.Font(None, cfg["size"])
    img = font.render(text, True, cfg["color"])
    shadow = font.render(text, True, (0, 0, 0))

    if scale != 1.0:
        new_w = max(1, int(img.get_width() * scale))
        new_h = max(1, int(img.get_height() * scale))
        img = pygame.transform.smoothscale(img, (new_w, new_h))
        shadow = pygame.transform.smoothscale(shadow, (new_w, new_h))

    # Auto-shrink if text exceeds canvas width
    max_w = WIDTH - 24  # leave 12px margin each side
    if img.get_width() > max_w:
        shrink = max_w / img.get_width()
        new_w = max_w
        new_h = max(1, int(img.get_height() * shrink))
        img = pygame.transform.smoothscale(img, (new_w, new_h))
        shadow = pygame.transform.smoothscale(shadow, (new_w, new_h))

    img.set_alpha(alpha)
    shadow.set_alpha(alpha // 2)

    # Use provided position if given, else fall back to centered default y
    if pos is not None:
        center_x, center_y = pos
    else:
        center_x, center_y = WIDTH // 2, cfg["y"]

    rect = img.get_rect(center=(center_x, center_y + y_offset))
    surface.blit(shadow, (rect.x + 3, rect.y + 3))
    surface.blit(img, rect)
