import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.projectile import Projectile, ProjectileSystem


def test_projectile_system_starts_empty():
    sys = ProjectileSystem()
    assert len(sys.projectiles) == 0


def test_spawn_creates_projectile():
    sys = ProjectileSystem()
    sys.spawn(x_start=100, y_start=400, x_end=300, y_end=400,
              shape="screw", color=(80, 180, 255), lifetime=8)
    assert len(sys.projectiles) == 1
    p = sys.projectiles[0]
    assert p.x == 100
    assert p.y == 400
    assert p.shape == "screw"
    assert p.lifetime == 8
    assert p.age == 0


def test_projectile_lerps_position():
    sys = ProjectileSystem()
    sys.spawn(x_start=100, y_start=400, x_end=300, y_end=440,
              shape="screw", color=(80, 180, 255), lifetime=4)
    # After 1 update, position should be roughly 1/4 of the way from start to end
    sys.update()
    p = sys.projectiles[0]
    assert 140 <= p.x <= 160
    assert 405 <= p.y <= 415


def test_on_land_callback_fires_once_at_lifetime():
    sys = ProjectileSystem()
    landed = []

    def cb():
        landed.append(True)

    sys.spawn(x_start=0, y_start=0, x_end=100, y_end=0,
              shape="screw", color=(80, 180, 255), lifetime=3, on_land=cb)
    for _ in range(5):
        sys.update()
    # Callback fired exactly once
    assert landed == [True]
    # Aged-out projectile is removed
    assert len(sys.projectiles) == 0


def test_render_does_not_crash_for_both_shapes():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ProjectileSystem()
    sys.spawn(x_start=50, y_start=50, x_end=200, y_end=200,
              shape="screw", color=(80, 180, 255), lifetime=8)
    sys.spawn(x_start=400, y_start=50, x_end=200, y_end=200,
              shape="shard", color=(80, 180, 255), lifetime=8)
    sys.render(surface)
