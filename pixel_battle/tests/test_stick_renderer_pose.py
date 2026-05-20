"""Per-skill pose variations + projectile layer."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import (
    draw_stick_figure, ProjectileLayer, _arm_offsets, _leg_offsets,
)


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _make_char_attacking(hint, phase, phase_t=0):
    c = Character.load("brick_phone")
    c.pos_x = 240
    c.pos_y = 720
    c.facing = 1
    c.action_state = "attacking"
    c.attack_phase = phase
    c.attack_phase_t = phase_t
    c.attack_anim_hint = hint
    return c


def test_jab_arm_offsets_differ_per_phase():
    c_w = _make_char_attacking("jab", "windup", 30)
    c_s = _make_char_attacking("jab", "strike", 20)
    a_w = _arm_offsets(c_w, 22)
    a_s = _arm_offsets(c_s, 22)
    assert a_w != a_s


def test_kick_leg_offsets_differ_from_idle_leg():
    c_kick = _make_char_attacking("kick", "strike", 30)
    c_idle = Character.load("brick_phone")
    c_idle.pos_x = 240; c_idle.pos_y = 720; c_idle.facing = 1
    c_idle.on_ground = True
    legs_kick = _leg_offsets(c_kick, 26)
    legs_idle = _leg_offsets(c_idle, 26)
    assert legs_kick != legs_idle


def test_special_pose_differs_from_jab():
    c_sp = _make_char_attacking("special", "strike", 50)
    c_jab = _make_char_attacking("jab", "strike", 20)
    a_sp = _arm_offsets(c_sp, 22)
    a_jab = _arm_offsets(c_jab, 22)
    assert a_sp != a_jab


def test_cooldown_pose_differs_from_jab():
    c_cd = _make_char_attacking("cooldown", "strike", 40)
    c_jab = _make_char_attacking("jab", "strike", 20)
    a_cd = _arm_offsets(c_cd, 22)
    a_jab = _arm_offsets(c_jab, 22)
    assert a_cd != a_jab


def test_projectile_layer_spawn_and_decay():
    layer = ProjectileLayer()
    surf = pygame.Surface((200, 200))
    layer.spawn((10, 10), (190, 10), (255, 0, 0), current_ms=0, duration_ms=300)
    assert len(layer._items) == 1
    surf.fill((0, 0, 0))
    layer.draw(surf, 100)  # mid-flight
    # Should have drawn something
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()
    # After duration, projectile should be culled
    layer.draw(surf, 500)
    assert len(layer._items) == 0
