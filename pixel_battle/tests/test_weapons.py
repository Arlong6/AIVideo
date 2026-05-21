# pixel_battle/tests/test_weapons.py
"""Weapon registry + drawing."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.rl.weapons import Weapon, get_weapon, draw_weapon


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def test_champions_have_weapons():
    for cid, kind in (("garen", "greatsword"), ("lux", "staff"),
                       ("yasuo", "katana"), ("ashe", "bow")):
        w = get_weapon(cid)
        assert isinstance(w, Weapon)
        assert w.kind == kind


def test_phone_characters_are_unarmed():
    assert get_weapon("brick_phone") is None
    assert get_weapon("glass_slab") is None
    assert get_weapon("unknown_id") is None


def test_draw_weapon_marks_the_surface():
    surf = pygame.Surface((200, 200))
    surf.fill((0, 0, 0))
    w = get_weapon("garen")
    draw_weapon(surf, w, grip_xy=(100, 100), angle_deg=0.0,
                line_width=8, color=(200, 200, 200), accent=(255, 255, 255))
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()


from pixel_battle.rl.weapons import draw_swing_smear


def test_swing_smear_draws_faded_copies():
    surf = pygame.Surface((300, 300))
    surf.fill((0, 0, 0))
    w = get_weapon("garen")
    draw_swing_smear(surf, w, grip_xy=(150, 150), angle_from=250.0,
                     angle_to=20.0, line_width=8, color=(200, 80, 80))
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()


def test_swing_smear_noop_when_angles_equal():
    surf = pygame.Surface((300, 300))
    surf.fill((0, 0, 0))
    w = get_weapon("garen")
    draw_swing_smear(surf, w, grip_xy=(150, 150), angle_from=30.0,
                     angle_to=30.0, line_width=8, color=(200, 80, 80))
    arr = pygame.surfarray.array3d(surf)
    assert not (arr > 0).any()
