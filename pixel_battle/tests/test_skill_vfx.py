"""Per-skill VFX helper smoke tests."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _nonbg_pixels(surf):
    arr = pygame.surfarray.array3d(surf)
    return int(np.any(arr != 0, axis=-1).sum())


def test_draw_beam_renders():
    from pixel_battle.rl.play import _draw_beam
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    _draw_beam(surf, 100, 400, 380, 400, (255, 220, 80), age=2, life=10)
    assert _nonbg_pixels(surf) > 200


def test_draw_spin_renders():
    from pixel_battle.rl.play import _draw_spin
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    _draw_spin(surf, 240, 400, (90, 205, 115), age=4, life=16)
    assert _nonbg_pixels(surf) > 100


def test_draw_aura_renders():
    from pixel_battle.rl.play import _draw_aura
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    _draw_aura(surf, 240, 400, (95, 170, 245), age=4, life=18)
    assert _nonbg_pixels(surf) > 100


def test_effects_expire():
    """At age >= life the effect draws nothing."""
    from pixel_battle.rl.play import _draw_beam, _draw_spin, _draw_aura
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    _draw_beam(surf, 100, 400, 380, 400, (255, 220, 80), age=10, life=10)
    _draw_spin(surf, 240, 400, (90, 205, 115), age=16, life=16)
    _draw_aura(surf, 240, 400, (95, 170, 245), age=18, life=18)
    assert _nonbg_pixels(surf) == 0
