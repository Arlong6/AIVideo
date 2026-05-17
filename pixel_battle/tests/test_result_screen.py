import os
import pygame
import pytest


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()


def test_result_pop_scale_starts_zero():
    from pixel_battle.episodes.ep01_brick_vs_glass import _result_pop_scale
    assert _result_pop_scale(0) == 0.0


def test_result_pop_scale_peaks():
    from pixel_battle.episodes.ep01_brick_vs_glass import _result_pop_scale
    peak = _result_pop_scale(8, peak_frame=8)
    assert peak > 1.0  # overshoots


def test_result_pop_scale_settles():
    from pixel_battle.episodes.ep01_brick_vs_glass import _result_pop_scale
    settled = _result_pop_scale(20, peak_frame=8)
    assert abs(settled - 1.0) < 0.01
