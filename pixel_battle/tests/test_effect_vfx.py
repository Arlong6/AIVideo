# pixel_battle/tests/test_effect_vfx.py
"""Status-effect visual indicators."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.engine.effects import StatusEffect, ROOT, SHIELD
from pixel_battle.rl.stick_renderer import draw_effect_indicators
from pixel_battle.rl import scaled_pygame as _scaled_pygame


@pytest.fixture(autouse=True)
def _unscaled_shim():
    """These assertions were written against unscaled (S=1.0) pixel
    positions/sizes; stick_renderer is now shimmed to default S=2.25
    (native hi-res). Force S=1.0 for each test and restore the production
    default afterward."""
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(2.25)


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _nonbg(surf):
    arr = pygame.surfarray.array3d(surf)
    return int(np.any(arr != 0, axis=-1).sum())


def test_no_indicator_when_no_effects():
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 500.0
    surf = pygame.Surface((480, 854)); surf.fill((0, 0, 0))
    draw_effect_indicators(surf, c)
    assert _nonbg(surf) == 0


def test_indicator_drawn_for_active_effect():
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 500.0
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=1000))
    surf = pygame.Surface((480, 854)); surf.fill((0, 0, 0))
    draw_effect_indicators(surf, c)
    assert _nonbg(surf) > 0


def test_more_effects_draw_more_pixels():
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 500.0
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=1000))
    one = pygame.Surface((480, 854)); one.fill((0, 0, 0))
    draw_effect_indicators(one, c)
    c.effects.append(StatusEffect(kind=SHIELD, remaining_ms=1000, magnitude=20))
    two = pygame.Surface((480, 854)); two.fill((0, 0, 0))
    draw_effect_indicators(two, c)
    assert _nonbg(two) > _nonbg(one)
