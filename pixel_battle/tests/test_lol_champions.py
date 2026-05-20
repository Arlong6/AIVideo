"""LoL champion characters load and render with distinct styles."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import draw_stick_figure, get_style


CHAMPS = ["garen", "lux", "yasuo", "ashe"]


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


@pytest.mark.parametrize("champ", CHAMPS)
def test_champion_loads(champ):
    c = Character.load(champ)
    assert c is not None
    # basic + cooldown + 2 special + ultimate = 5 skills
    assert len(c.skills) == 5


@pytest.mark.parametrize("champ", CHAMPS)
def test_champion_has_style(champ):
    s = get_style(champ)
    assert s["head_shape"] in ("square", "triangle", "circle", "diamond")


def test_champions_render_distinctly():
    """Each champion produces a visually different silhouette."""
    renders = []
    for champ in CHAMPS:
        c = Character.load(champ)
        c.pos_x = 240
        c.pos_y = 530
        surf = pygame.Surface((480, 854))
        surf.fill((0, 0, 0))
        draw_stick_figure(surf, c, (255, 0, 0))
        renders.append(pygame.surfarray.array3d(surf))
    # every pair of champions differs by > 100 pixels
    for i in range(len(renders)):
        for j in range(i + 1, len(renders)):
            diff = np.any(renders[i] != renders[j], axis=-1).sum()
            assert diff > 100, f"{CHAMPS[i]} vs {CHAMPS[j]} too similar ({diff})"


def test_diamond_head_shape_exists():
    assert get_style("lux")["head_shape"] == "diamond"
