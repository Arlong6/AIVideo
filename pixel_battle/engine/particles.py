"""Lightweight particle system for hit/impact bursts."""
import math
import random
from dataclasses import dataclass
from typing import List, Tuple

import pygame


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    age: int
    lifetime: int
    color: Tuple[int, int, int]
    size: int


class ParticleSystem:
    def __init__(self):
        self.particles: List[Particle] = []

    def update(self) -> None:
        gravity = 0.18
        survivors = []
        for p in self.particles:
            p.age += 1
            if p.age >= p.lifetime:
                continue
            p.x += p.vx
            p.y += p.vy
            p.vy += gravity
            survivors.append(p)
        self.particles = survivors

    def render(self, surface: pygame.Surface) -> None:
        for p in self.particles:
            alpha = max(0, 255 - int(255 * (p.age / p.lifetime)))
            if alpha <= 0:
                continue
            color = (*p.color, alpha)
            radius = max(1, int(p.size * (1 - p.age / p.lifetime)))
            tmp = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(tmp, color, (radius + 1, radius + 1), radius)
            surface.blit(tmp, (int(p.x - radius), int(p.y - radius)))

    def emit_hit_burst(self, x: float, y: float,
                       color: Tuple[int, int, int] = (255, 220, 100),
                       count: int = 12,
                       speed: float = 6.0) -> None:
        for i in range(count):
            angle = (i / count) * 2 * math.pi + random.uniform(-0.2, 0.2)
            spd = speed * random.uniform(0.6, 1.2)
            self.particles.append(Particle(
                x=x, y=y,
                vx=math.cos(angle) * spd,
                vy=math.sin(angle) * spd - 1.5,  # slight upward bias
                age=0, lifetime=random.randint(18, 32),
                color=color, size=random.randint(3, 6),
            ))

    def emit_ultimate_burst(self, x: float, y: float) -> None:
        # Big radial burst with mixed colors
        for color in [(255, 220, 100), (255, 130, 50), (255, 255, 255)]:
            self.emit_hit_burst(x, y, color=color, count=15, speed=10.0)

    def emit_ko_burst(self, x: float, y: float) -> None:
        # White stars
        self.emit_hit_burst(x, y, color=(255, 255, 255), count=20, speed=8.0)
        self.emit_hit_burst(x, y, color=(255, 220, 100), count=10, speed=4.0)
