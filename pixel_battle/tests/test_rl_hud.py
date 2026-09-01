"""Tests for pixel_battle.rl.hud — KOF-style top HUD."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
import pytest
pygame.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl.hud import HUD
from pixel_battle.engine.character import Character
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.rl import scaled_pygame as _scaled_pygame


@pytest.fixture(autouse=True)
def _unscaled_shim():
    """These assertions were written against unscaled (S=1.0) pixel
    positions/sizes; hud.py is now shimmed to default S=2.25 (native
    hi-res). Force S=1.0 for each test and restore the production default
    afterward."""
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(2.25)


def _battle():
    left = Character.load("garen")
    right = Character.load("lux")
    return Battle(left, right, rng=BattleRNG(seed=0))


def test_hud_draws_left_and_right_bars():
    b = _battle()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    HUD().draw(surf, b, elapsed_ms=0)
    # Top strip should now have non-zero pixels on both halves
    arr = pygame.surfarray.array3d(surf)
    assert arr[:240, :70].any(), "left half of HUD strip is empty"
    assert arr[240:, :70].any(), "right half of HUD strip is empty"


def test_hud_health_bar_drains_with_hp_loss():
    """Verify the brand-color bar fill shrinks when HP drops.

    The left bar is anchored on the RIGHT — full HP fills all 180px left of
    center-30, draining from the left edge.  We compare the brand-color pixel
    count in the bar strip between full and 1 HP.
    """
    from pixel_battle.rl.hud import BAR_Y, BAR_HEIGHT
    import numpy as np

    b = _battle()
    # Draw at full HP — get the brand color pixels in the bar row band
    hud_full = HUD()
    surf_full = pygame.Surface((480, 854))
    surf_full.fill((0, 0, 0))
    hud_full.draw(surf_full, b, elapsed_ms=0)
    arr_full = pygame.surfarray.array3d(surf_full)
    # Bar region: x in [0,240), y in [BAR_Y, BAR_Y+BAR_HEIGHT)
    bar_full = arr_full[:240, BAR_Y:BAR_Y + BAR_HEIGHT]
    # Count pixels that are clearly branded (high brightness non-grey)
    full_bright = int(np.any(bar_full > 80, axis=-1).sum())

    # Now drain HP to 1, let the lerp converge over many ticks
    b.left.hp = 1
    hud_drain = HUD()
    surf_drain = pygame.Surface((480, 854))
    for _ in range(120):
        surf_drain.fill((0, 0, 0))
        hud_drain.draw(surf_drain, b, elapsed_ms=2000)
    arr_drain = pygame.surfarray.array3d(surf_drain)
    bar_drain = arr_drain[:240, BAR_Y:BAR_Y + BAR_HEIGHT]
    drain_bright = int(np.any(bar_drain > 80, axis=-1).sum())

    assert drain_bright < full_bright, (
        f"left bar didn't shrink: full_bright={full_bright} drain_bright={drain_bright}")


def test_hud_timer_renders():
    b = _battle()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    HUD().draw(surf, b, elapsed_ms=12500)
    arr = pygame.surfarray.array3d(surf)
    # Center 80px wide column, rows 40-68 should have timer text
    assert arr[200:280, 40:68].any(), "timer region should have rendered text"
