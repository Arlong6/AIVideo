"""Per-character visual styling for stick figures."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import draw_stick_figure, get_style


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_brick_style_is_square_chunky():
    s = get_style("brick_phone")
    assert s["head_shape"] == "square"
    assert s["line_width"] >= 4


def test_glass_style_is_triangle_thin():
    s = get_style("glass_slab")
    assert s["head_shape"] == "triangle"
    assert s["line_width"] <= 2


def test_unknown_char_falls_back_to_default():
    s = get_style("unknown_char")
    assert s["head_shape"] == "circle"


def test_draw_uses_different_pixels_per_character():
    """Render both characters at the same screen position; pixel diffs must be substantial."""
    b = Character.load("brick_phone")
    g = Character.load("glass_slab")
    b.pos_x = g.pos_x = 240
    b.pos_y = g.pos_y = 700

    surf_b = pygame.Surface((480, 854))
    surf_g = pygame.Surface((480, 854))
    surf_b.fill((0, 0, 0))
    surf_g.fill((0, 0, 0))

    draw_stick_figure(surf_b, b, (255, 0, 0))
    draw_stick_figure(surf_g, g, (255, 0, 0))

    arr_b = pygame.surfarray.array3d(surf_b)
    arr_g = pygame.surfarray.array3d(surf_g)
    diff = np.any(arr_b != arr_g, axis=-1).sum()
    assert diff > 100, f"Expected >100 pixel diffs, got {diff}"
