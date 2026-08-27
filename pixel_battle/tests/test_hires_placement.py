"""Native hi-res placement tests — one per shim-mounted render module.

WHY THIS FILE EXISTS
    Every other render test runs at S=1.0 (see conftest), where the shim is
    an exact identity — so a call site that mixes REAL pixel sizes (what
    `get_size()` / `get_width()` / `get_rect()` always report) with FIGHT
    coordinates is invisible. These tests force the production scale
    (S=2.25) and assert that what gets drawn still lands inside the real
    canvas, which is exactly what that mixing breaks.

    Assertions are deliberately behavioural (pixels landed here) rather than
    "this call site uses `pygame.fight_width`", so they stay honest if the
    fix strategy ever changes.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

pygame.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl import scaled_pygame as sp


@pytest.fixture
def native():
    """Production scale for the duration of one test (overrides conftest)."""
    sp.set_scale(2.25)
    yield sp
    sp.set_scale(1.0)


def _canvas():
    surf = sp.Surface(sp.CANVAS, pygame.SRCALPHA)
    surf.fill((0, 0, 0, 255))
    return surf


def _lit_columns(surf, y0, y1, threshold=80):
    """Real-pixel x indices with any bright pixel in the real row band."""
    arr = pygame.surfarray.array3d(surf)
    band = arr[:, y0:y1]
    return np.nonzero(np.any(band > threshold, axis=(1, 2)))[0]


# ---------------------------------------------------------------- hud.py


def _battle():
    from pixel_battle.engine.character import Character
    from pixel_battle.engine.battle import Battle
    from pixel_battle.engine.rng import BattleRNG
    return Battle(Character.load("garen"), Character.load("lux"),
                  rng=BattleRNG(seed=0))


def test_hud_bars_and_names_stay_on_canvas_at_native_scale(native):
    """hud.py:71/147/148/158 — `W = surf.get_width()` fed the bar layout.

    At S=2.25 that is 1080, so the right-hand bar was laid out at fight-x
    570 and the shim pushed it to real-x 1282 — off a 1080px canvas.
    """
    from pixel_battle.rl.hud import BAR_Y, BAR_HEIGHT, BAR_WIDTH

    surf = _canvas()
    surf.fill((0, 0, 0, 255))
    from pixel_battle.rl.hud import HUD
    HUD().draw(surf, _battle(), elapsed_ms=12_500)

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED

    y0 = round(BAR_Y * sp.S)
    y1 = round((BAR_Y + BAR_HEIGHT) * sp.S)
    cols = _lit_columns(surf, y0, y1)
    assert cols.size, "no HP bar pixels drawn at all"

    centre = real_w // 2
    assert (cols < centre).any(), "left HP bar missing"
    assert (cols > centre).any(), "right HP bar missing"
    # Both bars complete: the right bar's far edge is fight-x
    # 240 + 30 + BAR_WIDTH, and it must not be clipped by the canvas edge.
    right_edge = round((sp.CANVAS[0] // 2 + 30 + BAR_WIDTH) * sp.S)
    assert cols.max() >= right_edge - 4, (
        f"right HP bar clipped: rightmost lit column {cols.max()}, "
        f"expected to reach ~{right_edge}")
    assert cols.max() < real_w, "HP bar ran past the canvas"

    # Name plates sit just above the bars and must also be on-canvas.
    name_cols = _lit_columns(surf, round(4 * sp.S), y0 - 2)
    assert name_cols.size, "no name plate pixels"
    assert (name_cols > centre).any(), "right name plate pushed off canvas"

    # Timer sits under the MP bar, centred.
    from pixel_battle.rl.hud import MP_BAR_GAP, MP_BAR_HEIGHT
    ty = round((BAR_Y + BAR_HEIGHT + MP_BAR_GAP + MP_BAR_HEIGHT + 3) * sp.S)
    timer_cols = _lit_columns(surf, ty, min(real_h, ty + round(20 * sp.S)))
    assert timer_cols.size, "match timer vanished at native scale"
    assert abs(int(timer_cols.mean()) - centre) < round(60 * sp.S), (
        "match timer is not centred")
