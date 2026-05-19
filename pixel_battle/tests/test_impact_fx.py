import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.impact_fx import ImpactRing, ImpactFXSystem


def test_impact_fx_starts_empty():
    sys = ImpactFXSystem()
    assert sys.rings == []


def test_spawn_ring_adds_to_list():
    sys = ImpactFXSystem()
    sys.spawn_ring(x=240, y=400, color=(80, 180, 255))
    assert len(sys.rings) == 1
    r = sys.rings[0]
    assert r.x == 240
    assert r.age == 0


def test_rings_age_and_drop_at_lifetime():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ImpactFXSystem()
    sys.spawn_ring(x=240, y=400, color=(80, 180, 255))
    for _ in range(ImpactRing.LIFETIME_DEFAULT + 2):
        sys.update_and_render(surface)
    assert sys.rings == []


def test_screen_flash_decays_over_frames():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ImpactFXSystem()
    sys.request_screen_flash(color=(80, 180, 255), alpha=80, frames=4)
    assert sys._flash_frames_remaining == 4
    for _ in range(4):
        sys.update_and_render(surface)
    assert sys._flash_frames_remaining == 0


def test_screen_flash_replaces_with_newer_request():
    sys = ImpactFXSystem()
    sys.request_screen_flash(color=(255, 0, 0), alpha=80, frames=2)
    sys.request_screen_flash(color=(0, 255, 0), alpha=120, frames=6)
    assert sys._flash_color == (0, 255, 0)
    assert sys._flash_alpha == 120
    assert sys._flash_frames_remaining == 6


def test_spawn_release_flash_creates_big_ring():
    """spawn_release_flash adds a ring with bigger max_radius and longer lifetime (P5)."""
    sys = ImpactFXSystem()
    sys.spawn_release_flash(x=240, y=400, color=(80, 180, 255))
    assert len(sys.rings) == 1
    r = sys.rings[0]
    assert r.max_radius == 120  # P5: was 80, bumped for visibility
    assert r.lifetime == 6      # P5: was 3, bumped for visibility
    assert r.color == (80, 180, 255)


def test_release_flash_is_longer_and_bigger_than_default_ring():
    """P5: release flash bumped to lifetime=6, max_radius=120 for visibility."""
    from pixel_battle.engine.impact_fx import ImpactFXSystem
    fx = ImpactFXSystem()
    fx.spawn_release_flash(100.0, 100.0, (80, 180, 255))
    assert len(fx.rings) == 1
    ring = fx.rings[0]
    assert ring.lifetime == 6, f"expected lifetime=6, got {ring.lifetime}"
    assert ring.max_radius == 120, f"expected max_radius=120, got {ring.max_radius}"
