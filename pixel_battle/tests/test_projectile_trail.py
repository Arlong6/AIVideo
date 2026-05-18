import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.projectile import ProjectileSystem


def test_no_trails_when_no_projectiles():
    sys = ProjectileSystem()
    assert sys.trails == []


def test_trail_spawns_during_projectile_flight():
    sys = ProjectileSystem()
    sys.spawn(x_start=0, y_start=100, x_end=200, y_end=100,
              shape="screw", color=(80, 180, 255), lifetime=10)
    sys.update()
    assert len(sys.trails) >= 1
    t = sys.trails[0]
    assert t.color == (80, 180, 255)


def test_trail_particles_age_and_drop():
    sys = ProjectileSystem()
    sys.spawn(x_start=0, y_start=100, x_end=200, y_end=100,
              shape="screw", color=(80, 180, 255), lifetime=4)
    for _ in range(20):
        sys.update()
    assert sys.trails == []


def test_render_with_trails_does_not_crash():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ProjectileSystem()
    sys.spawn(x_start=0, y_start=100, x_end=200, y_end=100,
              shape="screw", color=(80, 180, 255), lifetime=10)
    sys.update()
    sys.render(surface)
