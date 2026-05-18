import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.banner import Banner, BannerSystem


def test_banner_system_starts_empty():
    sys = BannerSystem()
    assert sys.active is None


def test_spawn_replaces_previous_banner():
    sys = BannerSystem()
    sys.spawn("FIRST", (255, 255, 255))
    sys.spawn("SECOND", (0, 0, 255))
    assert sys.active is not None
    assert sys.active.text == "SECOND"


def test_banner_ages_and_clears_after_lifetime():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = BannerSystem()
    sys.spawn("HELLO", (255, 255, 255))
    for _ in range(BannerSystem.LIFETIME_FRAMES + 2):
        sys.update_and_render(surface)
    assert sys.active is None


def test_banner_x_position_lerps_phase_1():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = BannerSystem()
    sys.spawn("HI", (255, 255, 255))
    # At frame 5 (mid phase-1 slide-in), x should be between x_start and x_end
    for _ in range(5):
        sys.update_and_render(surface)
    assert sys.active is not None
    assert BannerSystem.X_START < sys.active.x < BannerSystem.X_END
