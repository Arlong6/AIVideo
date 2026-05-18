"""Charge-up FX: sparkles converging on the attacker before a CD/special attack lands.

Triggered by EventType.ATTACK_WINDUP events. Pure rendering, no game logic.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import math
import pygame


@dataclass
class ChargeEffect:
    x: float                       # attacker world x
    y: float                       # attacker world y (feet)
    color: Tuple[int, int, int]
    age: int = 0
    lifetime: int = 12             # matches ATTACK_WINDUP_MS (~200ms at 60fps)
    on_complete: Optional[Callable[[], None]] = None
    _completed: bool = False

    LIFETIME_DEFAULT = 12          # class-level default for tests/tuning


class ChargeFXSystem:
    SPARKLE_COUNT = 6
    ORBIT_RADIUS_START = 30
    ORBIT_RADIUS_END = 0

    def __init__(self) -> None:
        self.effects: List[ChargeEffect] = []

    def spawn(self,
              x: float, y: float,
              color: Tuple[int, int, int],
              on_complete: Optional[Callable[[], None]] = None) -> None:
        self.effects.append(ChargeEffect(x=x, y=y, color=color,
                                          on_complete=on_complete))

    def _current_orbit_radius(self, eff: ChargeEffect) -> float:
        t = min(1.0, eff.age / eff.lifetime)
        return self.ORBIT_RADIUS_START + \
               (self.ORBIT_RADIUS_END - self.ORBIT_RADIUS_START) * t

    def update_and_render(self, surface: pygame.Surface) -> None:
        survivors: List[ChargeEffect] = []
        for eff in self.effects:
            eff.age += 1
            if eff.age >= eff.lifetime:
                if eff.on_complete is not None and not eff._completed:
                    eff.on_complete()
                    eff._completed = True
                continue

            radius = self._current_orbit_radius(eff)
            alpha = int(255 * (eff.age / eff.lifetime))  # brighter as it converges
            for i in range(self.SPARKLE_COUNT):
                angle = (2 * math.pi * i / self.SPARKLE_COUNT) + eff.age * 0.3
                sx = eff.x + math.cos(angle) * radius
                sy = eff.y - 80 + math.sin(angle) * radius * 0.5  # elliptical, head-height
                size = max(2, 5 - eff.age // 3)
                halo = pygame.Surface((size * 2 + 4, size * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(halo, (*eff.color, alpha),
                                   (size + 2, size + 2), size)
                surface.blit(halo, (int(sx - size - 2), int(sy - size - 2)))
            survivors.append(eff)
        self.effects = survivors
