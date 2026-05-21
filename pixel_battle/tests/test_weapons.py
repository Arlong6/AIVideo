# pixel_battle/tests/test_weapons.py
"""Weapon registry + drawing."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pixel_battle.rl.weapons import Weapon, get_weapon, draw_weapon, draw_swing_smear, _smear_delta


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


@pytest.mark.parametrize("char_id", ["garen", "lux", "yasuo", "ashe"])
def test_draw_weapon_marks_the_surface(char_id):
    surf = pygame.Surface((200, 200))
    surf.fill((0, 0, 0))
    w = get_weapon(char_id)
    draw_weapon(surf, w, grip_xy=(100, 100), angle_deg=0.0,
                line_width=8, color=(200, 200, 200), accent=(255, 255, 255))
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()


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


def test_smear_delta_cross_zero_positive():
    # 250 → 20: shortest arc is +130° (through 0°/360°)
    assert abs(_smear_delta(250, 20) - 130) < 1e-9


def test_smear_delta_cross_zero_negative():
    # 20 → 250: shortest arc is -130°
    assert abs(_smear_delta(20, 250) - (-130)) < 1e-9


def test_smear_delta_same_angle():
    assert _smear_delta(45, 45) == 0


def test_smear_delta_cross_zero_small():
    # 350 → 10: shortest arc is +20°
    assert abs(_smear_delta(350, 10) - 20) < 1e-9
