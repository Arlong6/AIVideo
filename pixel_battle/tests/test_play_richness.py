"""Smoke tests for run_one_match HUD / effects pipeline.

We don't run a full match (too slow); we test the helper functions
directly to confirm they draw without errors.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl import scaled_pygame as _scaled_pygame


@pytest.fixture(autouse=True)
def _unscaled_shim():
    """These assertions were written against unscaled (S=1.0) pixel
    positions/sizes; play.py's HUD/render helpers are now shimmed to
    default S=2.25 (native hi-res). Force S=1.0 for each test and restore
    the production default afterward."""
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(2.25)


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_helpers_importable():
    from pixel_battle.rl.play import (
        _draw_back_wall, _draw_floor, _draw_shadow, _draw_hud,
        _draw_player_hud, _draw_banner, _get_hud_font,
        run_one_match,
    )
    assert all(callable(f) for f in (
        _draw_back_wall, _draw_floor, _draw_shadow,
        _draw_hud, _draw_player_hud, _draw_banner,
    ))
    assert callable(_get_hud_font)
    assert callable(run_one_match)


def test_draw_hud_runs_without_error():
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.rl.play import _draw_hud, WIDTH, HEIGHT
    env = PixelBattleEnv(seed=1)
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((20, 20, 20))
    _draw_hud(surf, env)
    # Verify SOMETHING was drawn (non-bg pixels exist)
    import numpy as np
    arr = pygame.surfarray.array3d(surf)
    diff = np.any(arr != (20, 20, 20), axis=-1).sum()
    assert diff > 100


def test_draw_shadow_runs_without_error():
    from pixel_battle.rl.play import _draw_shadow, WIDTH, HEIGHT
    c = Character.load("brick_phone")
    c.pos_x = 240
    c.pos_y = 720
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    _draw_shadow(surf, c)
    import numpy as np
    arr = pygame.surfarray.array3d(surf)
    # Just confirm no exceptions and surface has same size
    assert arr.shape == (WIDTH, HEIGHT, 3)


def test_draw_banner_renders_text():
    from pixel_battle.rl.play import _draw_banner, WIDTH, HEIGHT
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    _draw_banner(surf, "TEST BANNER")
    import numpy as np
    arr = pygame.surfarray.array3d(surf)
    diff = np.any(arr > 50, axis=-1).sum()
    assert diff > 100  # text rendered


def test_draw_back_wall_and_floor():
    from pixel_battle.rl.play import _draw_back_wall, _draw_floor, WIDTH, HEIGHT, BG
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill(BG)
    _draw_back_wall(surf)
    _draw_floor(surf)
    import numpy as np
    arr = pygame.surfarray.array3d(surf)
    # Confirm pixels in the floor band differ from BG (we drew the ground rect)
    floor_band = arr[:, 720:, :]
    bg_arr = np.array(BG)
    differs = np.any(floor_band != bg_arr, axis=-1).sum()
    assert differs > 1000


def test_player_hud_right_align_drains_correctly():
    """Right-side HUD should drain HP from the LEFT (depleted-left appearance)."""
    from pixel_battle.rl.play import _draw_player_hud, WIDTH, HEIGHT
    BLUE = (60, 130, 220)
    c = Character.load("glass_slab")
    c.hp = 30
    c.mp = 0
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    x = WIDTH - 12 - 200
    _draw_player_hud(surf, c, BLUE, x=x, name="GLASS", right_align=True)
    import numpy as np
    arr = pygame.surfarray.array3d(surf)
    # HP fill rectangle is at y in [17, 29) (1px outline trims top/bottom);
    # right_align drains from the LEFT, so the LEFT pixels of the bar should
    # still be background and the right side (just inside the 1px outline)
    # should be BLUE.
    blue = np.array(BLUE)
    # Column just inside the right outline (outline at x+199, fill at x+198).
    right_col = arr[x + 198, 17:29, :]
    assert np.any(np.all(right_col == blue, axis=-1)), "right side of bar should be filled"
    # Left-most pixel of the bar (way past the 30% fill from the right)
    # should NOT be the blue fill.
    left_col = arr[x + 5, 17:29, :]
    assert not np.any(np.all(left_col == blue, axis=-1)), "left of bar should be empty"


def test_get_hud_font_caches():
    from pixel_battle.rl.play import _get_hud_font
    f1 = _get_hud_font(14)
    f2 = _get_hud_font(14)
    assert f1 is f2
    f3 = _get_hud_font(22)
    assert f3 is not f1
