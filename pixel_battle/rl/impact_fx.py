"""Renderer-side impact effects: big sparks, screen flash, floating text.

Stateless per spawn; `update_and_draw` ticks all active effects and renders
them onto the supplied world surface. Spawning is decoupled from drawing
so `_render_fight` can route engine events to the spawn helpers and the
per-frame draw step composites everything."""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

TEXT_FONT_SIZE = 22
TEXT_LIFETIME_MS = 400
TEXT_RISE_PX = 30
FLASH_DECAY_PER_FRAME = 18


@dataclass
class _Spark:
    x: float
    y: float
    vx: float
    vy: float
    life_ms: int
    color: Tuple[int, int, int]


@dataclass
class _FloatingText:
    x: int
    y: int
    text: str
    color: Tuple[int, int, int]
    age_ms: int = 0


class ImpactFX:
    """Registry of active impact effects. Construct once per render; call
    `update_and_draw` each frame after drawing the world surface."""

    def __init__(self):
        self._active: List[_Spark] = []
        self._texts: List[_FloatingText] = []
        self._flash_color: Tuple[int, int, int] = (255, 255, 255)
        self._flash_alpha: int = 0
        self._text_font = pygame.font.SysFont(None, TEXT_FONT_SIZE * 2)

    def spawn_hit_spark(self, x: int, y: int, damage: int,
                        color: Tuple[int, int, int]) -> None:
        """Radial burst of sparks; count scales with damage."""
        n = max(6, min(28, 6 + damage * 2))
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(2.5, 5.5)
            life = random.randint(140, 280)
            self._active.append(_Spark(
                x=float(x), y=float(y),
                vx=math.cos(ang) * speed, vy=math.sin(ang) * speed,
                life_ms=life, color=color))

    def flash_screen(self, color: Tuple[int, int, int], alpha: int = 200) -> None:
        """Request a full-screen color flash at the given alpha."""
        self._flash_color = color
        self._flash_alpha = max(self._flash_alpha, alpha)

    def spawn_floating_text(self, x: int, y: int, text: str,
                            color: Tuple[int, int, int]) -> None:
        """Spawn text that rises and fades over TEXT_LIFETIME_MS ms."""
        self._texts.append(_FloatingText(x=x, y=y, text=text, color=color))

    def update_and_draw(self, surf: pygame.Surface, dt_ms: int) -> None:
        """Advance all effects by dt_ms and draw onto surf."""
        # Update and draw sparks
        alive: List[_Spark] = []
        for s in self._active:
            s.x += s.vx
            s.y += s.vy
            s.vy += 0.25   # gravity-like droop
            s.life_ms -= dt_ms
            if s.life_ms > 0:
                alive.append(s)
                pygame.draw.line(surf, s.color,
                                 (int(s.x), int(s.y)),
                                 (int(s.x - s.vx), int(s.y - s.vy)),
                                 width=2)
        self._active = alive

        # Update and draw floating text
        alive_texts: List[_FloatingText] = []
        for t in self._texts:
            t.age_ms += dt_ms
            if t.age_ms < TEXT_LIFETIME_MS:
                alive_texts.append(t)
                frac = t.age_ms / TEXT_LIFETIME_MS
                y_offset = int(TEXT_RISE_PX * frac)
                fade = max(0, 255 - int(255 * frac))
                try:
                    rendered = self._text_font.render(t.text, True, t.color)
                    rendered.set_alpha(fade)
                    surf.blit(rendered, (t.x - rendered.get_width() // 2,
                                         t.y - y_offset - rendered.get_height()))
                except Exception:
                    pass  # graceful no-op if font unavailable
        self._texts = alive_texts

        # Draw screen flash overlay (on top of everything)
        if self._flash_alpha > 0:
            try:
                overlay = pygame.Surface(surf.get_size(), flags=pygame.SRCALPHA)
                overlay.fill((*self._flash_color, self._flash_alpha))
                surf.blit(overlay, (0, 0))
            except Exception:
                pass
            self._flash_alpha = max(0, self._flash_alpha - FLASH_DECAY_PER_FRAME)
