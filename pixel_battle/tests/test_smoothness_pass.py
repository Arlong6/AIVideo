# pixel_battle/tests/test_smoothness_pass.py
"""Tests for 120-fps render, idle bob, walk cycle, motion blur alpha."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
import pygame
import pytest

from pixel_battle.engine.character import Character


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ── T1: Motion blur alpha ─────────────────────────────────────────────────────

def test_motion_blur_uses_higher_alpha():
    """MOTION_BLUR_ALPHA must be >= 80 (35% of 255 ≈ 89)."""
    from pixel_battle.rl.play import MOTION_BLUR_ALPHA
    assert MOTION_BLUR_ALPHA >= 80, (
        f"Expected MOTION_BLUR_ALPHA >= 80, got {MOTION_BLUR_ALPHA}"
    )


# ── T2a: Recorder is constructed at 120 fps ───────────────────────────────────

def test_render_runs_at_120fps():
    """RENDER_FPS constant must be 120."""
    from pixel_battle.rl.play import RENDER_FPS
    assert RENDER_FPS == 120, f"Expected RENDER_FPS=120, got {RENDER_FPS}"


# ── T2b: Engine ticks at 60 Hz during render ─────────────────────────────────

def test_engine_ticks_at_60hz_during_render():
    """In 1 simulated second of render frames the engine must have ticked exactly 60 times.

    We simulate the accumulator logic manually without running the full renderer.
    """
    from pixel_battle.rl.play import RENDER_FPS, RENDER_MS, ENGINE_MS

    total_render_frames = RENDER_FPS   # 1 second worth
    accum = 0.0
    engine_ticks = 0
    for _ in range(total_render_frames):
        accum += RENDER_MS
        if accum >= ENGINE_MS:
            accum -= ENGINE_MS
            engine_ticks += 1
    assert engine_ticks == 60, (
        f"Expected 60 engine ticks in 1s of render, got {engine_ticks}"
    )


# ── T3: Idle bob changes y over time ─────────────────────────────────────────

def test_idle_bob_changes_y_over_time():
    """Render an idle character at t=0 and t=600ms; head joint y must differ by > 0.5px."""
    from pixel_battle.rl.poses import compute_figure

    _STYLE = {
        "head_shape": "circle", "head_size": 14, "torso_length": 52,
        "upper_arm": 18, "forearm": 18, "thigh": 20, "shin": 20,
        "line_width": 3, "hand_radius": 3, "foot_length": 8,
        "pose_overrides": {},
    }

    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0

    geo0 = compute_figure(c, _STYLE, time_ms=0.0)
    geo_peak = compute_figure(c, _STYLE, time_ms=300.0)  # quarter-cycle = peak bob

    delta_y = abs(geo0.head_center[1] - geo_peak.head_center[1])
    assert delta_y > 0.5, (
        f"Idle bob: head y difference at 0ms vs 300ms is {delta_y:.3f}px, expected > 0.5px"
    )


# ── T4: Walk cycle alternates (bob changes y over time) ──────────────────────

def test_walk_cycle_alternates_feet():
    """At t=0 and t=200ms (half-period), the head y of a walking character must differ.

    The walk bob has a 400ms period; at t=0 sin=0 and at t=100ms (quarter-period)
    sin=1 (peak). Comparing t=0 vs t=100ms gives the full amplitude difference (~2px).
    """
    from pixel_battle.rl.stick_renderer import RenderState, get_style

    _STYLE = get_style("garen")
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 4.0   # walk

    rs = RenderState()
    # Bootstrap — first call with walk pose; walk_phase_t starts at 0.
    geo0 = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    # Drive walk_phase_t to ~100ms (quarter-period = sin peak) by ticking frames.
    # 100ms / 8.333ms ≈ 12 frames
    ticks_100ms = int(100 / 8.333)
    geo_peak = None
    for _ in range(ticks_100ms):
        geo_peak = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    delta_y = abs(geo0.head_center[1] - geo_peak.head_center[1])
    assert delta_y > 1.0, (
        f"Walk bob: head y diff at t=0 vs t=100ms is {delta_y:.3f}px, expected > 1px"
    )


# ── T5: Idle breathing bobs figure vertically ────────────────────────────────

def test_idle_breathing_bobs_figure_vertically():
    """Two idle renders 375ms apart (quarter-period of 1500ms) must differ in hip_y by ~2px.

    At t=0 sin=0; at t=375ms sin(2π*375/1500) = sin(π/2) = 1.0 → bob_y=2px.
    So hip_y should differ by approximately 2px (within ±0.2px tolerance).
    """
    from pixel_battle.rl.poses import compute_figure
    from pixel_battle.rl.stick_renderer import get_style

    style = get_style("garen")
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0

    geo0 = compute_figure(c, style, time_ms=0.0)
    geo_peak = compute_figure(c, style, time_ms=375.0)   # quarter-period, sin=1 → peak

    delta_hip_y = abs(geo0.hip[1] - geo_peak.hip[1])
    assert 1.5 <= delta_hip_y <= 2.5, (
        f"Idle breathing: hip_y diff at 0ms vs 375ms = {delta_hip_y:.3f}px, expected ~2px"
    )


# ── T6: Walk pelvis sways (hip_x and hip_y both vary) ────────────────────────

def test_walk_pelvis_sways():
    """Over a walk cycle, hip_x must vary (horizontal sway) AND hip_y must vary (bob).

    Sample 3 time points within one 400ms period and assert both axes show variation.
    """
    from pixel_battle.rl.stick_renderer import RenderState, get_style

    style = get_style("garen")
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 4.0  # walk

    rs = RenderState()
    # Collect hip positions at 3 walk-phase moments: 0, ~100ms, ~200ms
    dt = 8.333
    hip_xs, hip_ys = [], []

    geo = rs.resolve(c, style, dt_ms=dt, time_ms=0.0)
    hip_xs.append(geo.hip[0])
    hip_ys.append(geo.hip[1])

    for _ in range(int(100 / dt)):
        geo = rs.resolve(c, style, dt_ms=dt, time_ms=0.0)
    hip_xs.append(geo.hip[0])
    hip_ys.append(geo.hip[1])

    for _ in range(int(100 / dt)):
        geo = rs.resolve(c, style, dt_ms=dt, time_ms=0.0)
    hip_xs.append(geo.hip[0])
    hip_ys.append(geo.hip[1])

    x_range = max(hip_xs) - min(hip_xs)
    y_range = max(hip_ys) - min(hip_ys)
    assert x_range > 0.3, f"Walk sway: hip_x range {x_range:.3f}px, expected > 0.3px"
    assert y_range > 1.0, f"Walk bob: hip_y range {y_range:.3f}px, expected > 1px"


# ── T7: Lux idle quirk — staff oscillates ────────────────────────────────────

def test_idle_quirk_lux_staff_oscillates():
    """Lux idle at two different time values must produce different weapon_deg.

    The Lux staff oscillates ±8° over 3000ms. At t=0 delta=0, at t=750ms
    sin(π/2)=1 → delta=+8°. So weapon_deg must differ by at least 4°.
    """
    from pixel_battle.rl.poses import compute_figure
    from pixel_battle.rl.stick_renderer import get_style

    style = get_style("lux")
    c = Character.load("lux")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0

    geo0 = compute_figure(c, style, time_ms=0.0)
    geo_750 = compute_figure(c, style, time_ms=750.0)   # quarter-period, sin=1 → peak

    delta_deg = abs(geo0.weapon_deg - geo_750.weapon_deg)
    assert delta_deg > 4.0, (
        f"Lux staff: weapon_deg diff at 0ms vs 750ms = {delta_deg:.3f}°, expected > 4°"
    )


# ── T8: STATE_TRANSITION_MS is 55 ────────────────────────────────────────────

def test_state_transition_ms_tightened():
    """STATE_TRANSITION_MS must equal 55 for snappier combat feel."""
    from pixel_battle.rl.stick_renderer import STATE_TRANSITION_MS
    assert STATE_TRANSITION_MS == 55, (
        f"Expected STATE_TRANSITION_MS=55, got {STATE_TRANSITION_MS}"
    )
