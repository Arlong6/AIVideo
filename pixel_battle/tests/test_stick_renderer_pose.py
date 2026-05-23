# pixel_battle/tests/test_stick_renderer_pose.py
"""Jointed stick-figure rendering + the projectile layer."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import (
    draw_stick_figure, get_style, ProjectileLayer, _swing_smear_start_angle,
)
from pixel_battle.rl.poses import cocked_weapon_deg, ARCHETYPE_POSES


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


def _char(char_id, hint="jab", phase="strike", phase_t=40, vfx=None):
    c = Character.load(char_id)
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "attacking"
    c.attack_phase = phase
    c.attack_phase_t = phase_t
    c.attack_anim_hint = hint
    if vfx is not None:
        class _Sk:
            pass
        s = _Sk()
        s.vfx = vfx
        c.attack_used_kind = s
    return c


def _nonbg(surf):
    arr = pygame.surfarray.array3d(surf)
    return int(np.any(arr != 0, axis=-1).sum())


def test_every_style_has_split_limb_lengths():
    for cid in ("brick_phone", "glass_slab", "garen", "lux", "yasuo", "ashe"):
        st = get_style(cid)
        for key in ("upper_arm", "forearm", "thigh", "shin",
                    "torso_length", "head_size", "line_width",
                    "hand_radius", "foot_length", "head_shape"):
            assert key in st, f"{cid} style missing {key}"


def test_draw_stick_figure_marks_surface():
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))
    draw_stick_figure(surf, _char("garen", vfx="melee"), (90, 205, 115))
    assert _nonbg(surf) > 200


def test_armed_character_draws_more_than_unarmed():
    """Garen (greatsword) should paint more pixels than brick_phone in the
    same pose — the weapon adds ink."""
    armed = pygame.Surface((480, 854)); armed.fill((0, 0, 0))
    unarmed = pygame.Surface((480, 854)); unarmed.fill((0, 0, 0))
    draw_stick_figure(armed, _char("garen", vfx="slam"), (90, 205, 115))
    draw_stick_figure(unarmed, _char("brick_phone", vfx="slam"), (225, 95, 80))
    assert _nonbg(armed) > _nonbg(unarmed)


def test_projectile_layer_spawn_and_decay():
    layer = ProjectileLayer()
    surf = pygame.Surface((200, 200))
    layer.spawn((10, 10), (190, 10), (255, 0, 0), current_ms=0, duration_ms=300)
    assert len(layer._items) == 1
    surf.fill((0, 0, 0))
    layer.draw(surf, 100)
    arr = pygame.surfarray.array3d(surf)
    assert (arr > 0).any()
    layer.draw(surf, 500)
    assert len(layer._items) == 0


def test_get_style_applies_figure_scale():
    from pixel_battle.rl.stick_renderer import get_style, _STYLES, _FIGURE_SCALE
    raw = _STYLES["garen"]
    scaled = get_style("garen")
    # head_shape (a string) is untouched; size fields are scaled down.
    assert scaled["head_shape"] == raw["head_shape"]
    assert scaled["torso_length"] == max(1, int(raw["torso_length"] * _FIGURE_SCALE))
    assert _FIGURE_SCALE < 1.0


def test_swing_smear_start_angle_regression():
    """Regression lock: smear start angle must differ from strike-end angle (facing +1)."""
    cocked = cocked_weapon_deg("slam")
    # Facing +1: start angle equals the cocked angle.
    assert _swing_smear_start_angle("slam", 1) == cocked
    # Facing -1: start angle is the mirror.
    assert _swing_smear_start_angle("slam", -1) == 180.0 - cocked
    # The smear must genuinely sweep — start != end for facing +1.
    strike_end = ARCHETYPE_POSES["slam"]["extended"].weapon_deg
    assert _swing_smear_start_angle("slam", 1) != strike_end, (
        "Smear start angle equals strike-end angle for facing +1 — zero-delta bug regressed"
    )
