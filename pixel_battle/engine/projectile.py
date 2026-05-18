"""Projectile system: short-lived flying objects (screw darts, glass shards) that
travel from a start to an end point over `lifetime` frames, optionally firing an
`on_land` callback when they reach the end.

Pure rendering — no game logic. Spawned by the episode runner.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import math
import pygame


@dataclass
class Projectile:
    x: float
    y: float
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    shape: str          # "screw" or "shard"
    color: Tuple[int, int, int]
    lifetime: int
    age: int = 0
    on_land: Optional[Callable[[], None]] = None
    _landed_fired: bool = False


class ProjectileSystem:
    def __init__(self):
        self.projectiles: List[Projectile] = []

    def spawn(self,
              x_start: float, y_start: float,
              x_end: float, y_end: float,
              shape: str,
              color: Tuple[int, int, int],
              lifetime: int = 8,
              on_land: Optional[Callable[[], None]] = None) -> None:
        self.projectiles.append(Projectile(
            x=x_start, y=y_start,
            x_start=x_start, y_start=y_start,
            x_end=x_end, y_end=y_end,
            shape=shape, color=color,
            lifetime=lifetime, age=0,
            on_land=on_land,
        ))

    def update(self) -> None:
        survivors: List[Projectile] = []
        for p in self.projectiles:
            p.age += 1
            if p.age >= p.lifetime:
                if p.on_land is not None and not p._landed_fired:
                    p.on_land()
                    p._landed_fired = True
                # Drop projectile this frame (don't survive)
                continue
            # Linear lerp from start to end over lifetime frames
            t = p.age / p.lifetime
            p.x = p.x_start + (p.x_end - p.x_start) * t
            p.y = p.y_start + (p.y_end - p.y_start) * t
            survivors.append(p)
        self.projectiles = survivors

    def render(self, surface: pygame.Surface) -> None:
        for p in self.projectiles:
            if p.shape == "screw":
                self._draw_screw(surface, p)
            elif p.shape == "shard":
                self._draw_shard(surface, p)

    def _draw_screw(self, surface: pygame.Surface, p: Projectile) -> None:
        # 6x3 px rotating rect with diagonal threads
        cx, cy = int(p.x), int(p.y)
        angle = p.age * 0.4  # rotation speed
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        half_w = 6
        half_h = 2
        # Four corners of the rect rotated around center
        pts = [
            (cx + cos_a * dx - sin_a * dy, cy + sin_a * dx + cos_a * dy)
            for dx, dy in [(-half_w, -half_h), (half_w, -half_h),
                            (half_w, half_h), (-half_w, half_h)]
        ]
        pygame.draw.polygon(surface, p.color, pts)
        # Outline
        pygame.draw.polygon(surface, (20, 20, 30), pts, width=1)

    def _draw_shard(self, surface: pygame.Surface, p: Projectile) -> None:
        # 3 small triangles fanning out (different angles ±15°)
        cx, cy = int(p.x), int(p.y)
        base_angle = math.atan2(p.y_end - p.y_start, p.x_end - p.x_start)
        for ang_offset, alpha in [(-0.26, 200), (0.0, 255), (0.26, 200)]:
            angle = base_angle + ang_offset
            tip_dx = math.cos(angle) * 8
            tip_dy = math.sin(angle) * 8
            side1 = (cx + math.cos(angle + 2.4) * 4, cy + math.sin(angle + 2.4) * 4)
            side2 = (cx + math.cos(angle - 2.4) * 4, cy + math.sin(angle - 2.4) * 4)
            tip = (cx + tip_dx, cy + tip_dy)
            tri_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
            tri_pts = [(tip[0] - cx + 10, tip[1] - cy + 10),
                        (side1[0] - cx + 10, side1[1] - cy + 10),
                        (side2[0] - cx + 10, side2[1] - cy + 10)]
            pygame.draw.polygon(tri_surface, (*p.color, alpha), tri_pts)
            surface.blit(tri_surface, (cx - 10, cy - 10))
