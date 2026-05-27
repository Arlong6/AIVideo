"""Tests for the visual pass on Script 01:
  - Wider arena bounds
  - Pulsing shield glow ring
  - Lux per-character pose overrides
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
import numpy as np
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.engine.effects import StatusEffect, SHIELD
from pixel_battle.engine.physics import ARENA_LEFT, ARENA_RIGHT
from pixel_battle.rl.stick_renderer import draw_effect_indicators, get_style
from pixel_battle.rl.poses import IDLE_POSE, WALK_POSE, compute_figure


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ── 1. Arena bounds ────────────────────────────────────────────────────────────

def test_arena_widened():
    """Arena must span 10–470 (460 px usable width, widened in pacing pass)."""
    assert ARENA_LEFT == 10, f"Expected ARENA_LEFT=10, got {ARENA_LEFT}"
    assert ARENA_RIGHT == 470, f"Expected ARENA_RIGHT=470, got {ARENA_RIGHT}"


# ── 2. Shield pulsing ring ─────────────────────────────────────────────────────

def _lux_with_shield() -> Character:
    c = Character.load("lux")
    c.pos_x, c.pos_y = 240.0, 500.0
    c.effects.append(StatusEffect(kind=SHIELD, remaining_ms=2000, magnitude=25))
    return c


def _nonbg(surf: pygame.Surface) -> int:
    arr = pygame.surfarray.array3d(surf)
    return int(np.any(arr != 0, axis=-1).sum())


def test_shield_indicator_draws_pixels():
    """A SHIELD effect must produce visible pixels (the glow ring)."""
    c = _lux_with_shield()
    surf = pygame.Surface((480, 900)); surf.fill((0, 0, 0))
    draw_effect_indicators(surf, c, current_ms=0.0)
    assert _nonbg(surf) > 0, "Shield effect drew no pixels"


def test_shield_indicator_pulses():
    """The shield ring alpha must differ between frames 150 ms apart.

    With a 600 ms period, t=0 is at the sine trough (alpha MIN) and t=150 ms
    is at the sine peak (alpha MAX).  The pixel brightness sums must differ.
    """
    c = _lux_with_shield()

    surf0 = pygame.Surface((480, 900), pygame.SRCALPHA); surf0.fill((0, 0, 0, 0))
    surf1 = pygame.Surface((480, 900), pygame.SRCALPHA); surf1.fill((0, 0, 0, 0))

    # t=0 → phase=0 → sin(0)=0 → alpha = ALPHA_MIN
    # t=150 → phase=0.25 → sin(π/2)=1 → alpha = ALPHA_MAX
    draw_effect_indicators(surf0, c, current_ms=0.0)
    draw_effect_indicators(surf1, c, current_ms=150.0)

    # Sum of alpha channel in each frame; expect a meaningful difference.
    a0 = pygame.surfarray.array_alpha(surf0)
    a1 = pygame.surfarray.array_alpha(surf1)
    diff = abs(int(a0.sum()) - int(a1.sum()))
    assert diff > 0, (
        "Shield alpha sum is identical at t=0 and t=150 ms — pulse is not working"
    )


def test_shield_ring_not_drawn_when_no_shield():
    """Without a SHIELD effect, no ring pixels should appear."""
    c = Character.load("lux")
    c.pos_x, c.pos_y = 240.0, 500.0
    surf = pygame.Surface((480, 900)); surf.fill((0, 0, 0))
    draw_effect_indicators(surf, c, current_ms=0.0)
    assert _nonbg(surf) == 0, "Ring was drawn even though no SHIELD effect is active"


# ── 3. Lux pose overrides ──────────────────────────────────────────────────────

def test_lux_pose_override_applied():
    """Lux's idle_weapon_deg must differ from the default IDLE_POSE weapon_deg."""
    lux_style = get_style("lux")
    overrides = lux_style.get("pose_overrides", {})
    assert "idle_weapon_deg" in overrides, (
        "pose_overrides['idle_weapon_deg'] not found in Lux style"
    )
    assert overrides["idle_weapon_deg"] != IDLE_POSE.weapon_deg, (
        f"Lux idle_weapon_deg={overrides['idle_weapon_deg']} matches default "
        f"IDLE_POSE.weapon_deg={IDLE_POSE.weapon_deg} — override has no effect"
    )


def test_lux_walk_weapon_deg_differs_from_default():
    """Lux's walk_weapon_deg must differ from the default WALK_POSE weapon_deg."""
    overrides = get_style("lux").get("pose_overrides", {})
    assert "walk_weapon_deg" in overrides
    assert overrides["walk_weapon_deg"] != WALK_POSE.weapon_deg, (
        "Lux walk_weapon_deg matches default — override has no effect"
    )


def _lux_idle() -> Character:
    c = Character.load("lux")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0
    return c


def test_lux_weapon_deg_geometry_differs_from_garen():
    """Rendered Lux idle geometry weapon_deg must differ from rendered Garen idle
    weapon_deg — confirms the override feeds all the way through compute_figure."""
    lux_style = get_style("lux")
    garen_style = get_style("garen")

    lux = _lux_idle()
    garen = Character.load("garen")
    garen.pos_x, garen.pos_y = 240.0, 720.0
    garen.facing = 1
    garen.action_state = "idle"
    garen.on_ground = True
    garen.vel_x = 0.0

    lux_geo = compute_figure(lux, lux_style)
    garen_geo = compute_figure(garen, garen_style)
    assert lux_geo.weapon_deg != garen_geo.weapon_deg, (
        "Lux and Garen idle weapon_deg are identical — pose override not applied"
    )
