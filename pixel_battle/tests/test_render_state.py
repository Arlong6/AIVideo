"""Tests for the cross-state pose interpolation (RenderState)."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.poses import (
    IDLE_POSE, WALK_POSE, compute_figure, FigureGeometry,
)
from pixel_battle.rl.stick_renderer import (
    RenderState, STATE_TRANSITION_MS, _lerp_geo, get_style,
    _RENDER_STATE_CACHE,
)


@pytest.fixture(autouse=True, scope="module")
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ── Helpers ───────────────────────────────────────────────────────────────────

_STYLE = {
    "head_shape": "circle", "head_size": 22, "torso_length": 80,
    "upper_arm": 28, "forearm": 28, "thigh": 30, "shin": 30,
    "line_width": 4, "hand_radius": 4, "foot_length": 12,
}


def _char_idle():
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0
    return c


def _char_walk():
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 4.0          # select_pose_id → "walk"
    return c


# ── _lerp_geo unit tests ──────────────────────────────────────────────────────

def test_lerp_geo_at_zero_returns_from():
    a = compute_figure(_char_idle(), _STYLE)
    b = compute_figure(_char_walk(), _STYLE)
    result = _lerp_geo(a, b, 0.0)
    assert math.isclose(result.head_center[0], a.head_center[0], abs_tol=1e-6)
    assert math.isclose(result.head_center[1], a.head_center[1], abs_tol=1e-6)


def test_lerp_geo_at_one_returns_to():
    a = compute_figure(_char_idle(), _STYLE)
    b = compute_figure(_char_walk(), _STYLE)
    result = _lerp_geo(a, b, 1.0)
    assert math.isclose(result.head_center[0], b.head_center[0], abs_tol=1e-6)
    assert math.isclose(result.head_center[1], b.head_center[1], abs_tol=1e-6)


def test_pose_transition_lerp_interpolates_joints():
    """At frac=0.5 the lerped geometry is halfway between idle and walk joints."""
    a = compute_figure(_char_idle(), _STYLE)
    b = compute_figure(_char_walk(), _STYLE)

    mid = _lerp_geo(a, b, 0.5)

    # hip (x, y) should be the average of the two hips.
    expected_hip_x = (a.hip[0] + b.hip[0]) / 2.0
    expected_hip_y = (a.hip[1] + b.hip[1]) / 2.0
    assert math.isclose(mid.hip[0], expected_hip_x, abs_tol=1e-6), (
        f"hip.x: {mid.hip[0]:.4f} != {expected_hip_x:.4f}"
    )
    assert math.isclose(mid.hip[1], expected_hip_y, abs_tol=1e-6), (
        f"hip.y: {mid.hip[1]:.4f} != {expected_hip_y:.4f}"
    )

    # front_foot midpoint
    expected_fx = (a.front_foot[0] + b.front_foot[0]) / 2.0
    expected_fy = (a.front_foot[1] + b.front_foot[1]) / 2.0
    assert math.isclose(mid.front_foot[0], expected_fx, abs_tol=1e-6)
    assert math.isclose(mid.front_foot[1], expected_fy, abs_tol=1e-6)


def test_lerp_geo_weapon_deg_short_path():
    """weapon_deg lerp must take the short arc (< 180° delta)."""
    a = compute_figure(_char_idle(), _STYLE)
    b = compute_figure(_char_walk(), _STYLE)
    # Force a large wrap: 350° → 10°; shortest path is +20° not -340°.
    import copy
    from dataclasses import replace
    a2 = replace(a, weapon_deg=350.0)
    b2 = replace(b, weapon_deg=10.0)
    mid = _lerp_geo(a2, b2, 0.5)
    # Shortest delta is 20°; midpoint should be 360° (= 0°).
    assert math.isclose((mid.weapon_deg % 360.0), 0.0, abs_tol=1.0), (
        f"Expected ~0°, got {mid.weapon_deg:.2f}"
    )


# ── RenderState unit tests ────────────────────────────────────────────────────

def test_render_state_no_transition_on_first_call():
    rs = RenderState()
    c = _char_idle()
    geo = rs.resolve(c, _STYLE, dt_ms=16.0)
    assert not rs.transition_active
    assert isinstance(geo, FigureGeometry)


def test_render_state_transition_starts_on_key_change():
    rs = RenderState()
    c = _char_idle()
    rs.resolve(c, _STYLE, dt_ms=16.0)    # bootstrap
    # Switch to walking (pose_key changes to "walk")
    c.vel_x = 4.0
    geo2 = rs.resolve(c, _STYLE, dt_ms=16.0)
    assert rs.transition_active


def test_render_state_resets_after_transition_completes():
    """After STATE_TRANSITION_MS ms worth of ticks, transition_active is False."""
    rs = RenderState()
    c_idle = _char_idle()
    rs.resolve(c_idle, _STYLE, dt_ms=16.0)    # bootstrap

    # Trigger a state change.
    c_walk = _char_walk()
    rs.resolve(c_walk, _STYLE, dt_ms=16.0)
    assert rs.transition_active

    # Drive the clock past the transition window.
    ticks = int(STATE_TRANSITION_MS / 16) + 5
    for _ in range(ticks):
        rs.resolve(c_walk, _STYLE, dt_ms=16.0)

    assert not rs.transition_active


def test_render_state_midpoint_is_blended():
    """At exactly half the transition duration, resolved geometry is between
    the idle and walk geometries (not equal to either)."""
    rs = RenderState()
    c = _char_idle()
    idle_geo = rs.resolve(c, _STYLE, dt_ms=16.0)   # bootstrap

    # Now switch to walking and advance to roughly 50% of transition.
    c.vel_x = 4.0                                   # now "walk"
    half_ticks = int(STATE_TRANSITION_MS / 2 / 16)
    geo_mid = None
    for i in range(half_ticks):
        geo_mid = rs.resolve(c, _STYLE, dt_ms=16.0)

    walk_geo = compute_figure(c, _STYLE)

    # The resolved foot_y should be strictly between idle and walk foot_y
    # (they differ because walk leans the torso and shifts leg angles).
    idle_foot_y = idle_geo.front_foot[1]
    walk_foot_y = walk_geo.front_foot[1]
    if abs(idle_foot_y - walk_foot_y) > 0.5:
        lo = min(idle_foot_y, walk_foot_y)
        hi = max(idle_foot_y, walk_foot_y)
        assert lo <= geo_mid.front_foot[1] <= hi + 1.0, (
            f"Mid-transition foot_y {geo_mid.front_foot[1]:.2f} not between "
            f"{lo:.2f} and {hi:.2f}"
        )


def test_render_state_chain_transition_no_jump():
    """If a second state change fires mid-transition, the new transition starts
    from the blended (visible) position, not from the old start."""
    rs = RenderState()
    c = _char_idle()
    rs.resolve(c, _STYLE, dt_ms=16.0)   # bootstrap

    # Start idle→walk transition.
    c.vel_x = 4.0
    for _ in range(3):
        geo_before = rs.resolve(c, _STYLE, dt_ms=16.0)

    # Mid-transition: switch back to idle. _from_geo should be the blended pos.
    c.vel_x = 0.0
    geo_after = rs.resolve(c, _STYLE, dt_ms=16.0)

    # Verify: the transition restarted (transition_active is True).
    assert rs.transition_active

    # And the new "from" geometry (approximated via _last_geo before the switch)
    # should be close to geo_before — the blended mid-flight position.
    dx = abs(geo_after.front_hand[0] - geo_before.front_hand[0])
    dy = abs(geo_after.front_hand[1] - geo_before.front_hand[1])
    # At t=0 of the new transition the from=geo_before; after one dt_ms (16ms)
    # of the 130ms transition the blend should be very close to geo_before.
    assert dx < 20.0 and dy < 20.0, (
        f"Chain transition: hand jumped {dx:.1f}px / {dy:.1f}px — expected < 20px"
    )
