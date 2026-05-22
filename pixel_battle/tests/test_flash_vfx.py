# pixel_battle/tests/test_flash_vfx.py
"""Flash blink VFX."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.rl.stick_renderer import spawn_flash_puff


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_flash_puff_marks_the_surface():
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    spawn_flash_puff(surf, 240, 530, (180, 210, 255))
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()
