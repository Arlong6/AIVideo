"""Impact FX: expanding rings + screen-wide color flash on big hits.

Pure rendering, no game logic. Driven by episode-runner callbacks.
"""
from dataclasses import dataclass
from typing import List, Tuple

import pygame


@dataclass
class ImpactRing:
    x: float
    y: float
    color: Tuple[int, int, int]
    age: int = 0
    lifetime: int = 8       # ~130ms at 60fps
    max_radius: int = 60

    LIFETIME_DEFAULT = 8


class ImpactFXSystem:
    def __init__(self) -> None:
        self.rings: List[ImpactRing] = []
        self._flash_color: Tuple[int, int, int] = (255, 255, 255)
        self._flash_alpha: int = 0
        self._flash_frames_remaining: int = 0

    def spawn_ring(self, x: float, y: float,
                   color: Tuple[int, int, int]) -> None:
        self.rings.append(ImpactRing(x=x, y=y, color=color))

    def request_screen_flash(self, color: Tuple[int, int, int],
                              alpha: int = 80,
                              frames: int = 4) -> None:
        # Newer request always replaces — single active flash
        self._flash_color = color
        self._flash_alpha = alpha
        self._flash_frames_remaining = frames

    def update_and_render(self, surface: pygame.Surface) -> None:
        # 1. Expanding rings
        survivors: List[ImpactRing] = []
        for r in self.rings:
            r.age += 1
            if r.age >= r.lifetime:
                continue
            t = r.age / r.lifetime
            radius = max(1, int(r.max_radius * t))
            alpha = max(0, int(200 * (1 - t)))
            layer = pygame.Surface((radius * 2 + 6, radius * 2 + 6),
                                    pygame.SRCALPHA)
            pygame.draw.circle(layer, (*r.color, alpha),
                               (radius + 3, radius + 3), radius, width=3)
            surface.blit(layer, (int(r.x - radius - 3), int(r.y - radius - 3)))
            survivors.append(r)
        self.rings = survivors

        # 2. Screen-wide color flash (drawn ABOVE everything for max impact)
        if self._flash_frames_remaining > 0:
            flash = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            flash.fill((*self._flash_color, self._flash_alpha))
            surface.blit(flash, (0, 0))
            self._flash_frames_remaining -= 1
