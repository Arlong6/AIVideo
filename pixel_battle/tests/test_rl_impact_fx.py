"""Tests for pixel_battle.rl.impact_fx — big sparks, screen flash, floating text."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
import pytest
pygame.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl.impact_fx import ImpactFX
from pixel_battle.rl import scaled_pygame as _scaled_pygame


@pytest.fixture(autouse=True)
def _unscaled_shim():
    """These assertions were written against unscaled (S=1.0) pixel
    positions/sizes; impact_fx is now shimmed to default S=2.25 (native
    hi-res). Force S=1.0 for each test and restore the production default
    afterward."""
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(2.25)


def test_spark_burst_marks_pixels():
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    fx.spawn_hit_spark(x=240, y=400, damage=5, color=(255, 220, 100))
    fx.update_and_draw(surf, dt_ms=16)
    arr = pygame.surfarray.array3d(surf)
    # Sparks radiate outward — check a generous region around the spawn point
    near = arr[190:290, 360:440]
    assert near.any(), "spark should mark pixels near the hit point"


def test_spark_count_scales_with_damage():
    fx_small = ImpactFX()
    fx_big = ImpactFX()
    fx_small.spawn_hit_spark(x=240, y=400, damage=1, color=(255, 255, 255))
    fx_big.spawn_hit_spark(x=240, y=400, damage=20, color=(255, 255, 255))
    assert len(fx_big._active) > len(fx_small._active), (
        f"damage=20 should spawn more particles than damage=1: "
        f"small={len(fx_small._active)} big={len(fx_big._active)}")


def test_screen_flash_overlays_color():
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    fx.flash_screen(color=(255, 0, 0), alpha=180)
    fx.update_and_draw(surf, dt_ms=16)
    arr = pygame.surfarray.array3d(surf)
    # Some red should have made it through onto the whole frame
    red_pixels = (arr[:, :, 0] > 100).sum()
    assert red_pixels > 1000, f"red flash didn't paint enough pixels: {red_pixels}"


def test_floating_text_rises_and_expires():
    fx = ImpactFX()
    fx.spawn_floating_text(x=240, y=400, text="HIT!", color=(255, 255, 0))
    assert len(fx._texts) == 1
    # advance 500 ms — past the default lifetime (400 ms)
    for _ in range(35):
        surf = pygame.Surface((480, 854))
        fx.update_and_draw(surf, dt_ms=16)
    assert len(fx._texts) == 0, "floating text should have expired"
