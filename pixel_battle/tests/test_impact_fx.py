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


def test_spawn_release_flash_creates_short_lived_big_ring():
    """spawn_release_flash adds a ring with bigger max_radius and shorter lifetime than default."""
    sys = ImpactFXSystem()
    sys.spawn_release_flash(x=240, y=400, color=(80, 180, 255))
    assert len(sys.rings) == 1
    r = sys.rings[0]
    assert r.max_radius == 80   # bigger than default 60
    assert r.lifetime == 3      # shorter than default 8
    assert r.color == (80, 180, 255)
