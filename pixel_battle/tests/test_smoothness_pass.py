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
    geo_half = compute_figure(c, _STYLE, time_ms=600.0)  # half-cycle = peak bob

    delta_y = abs(geo0.head_center[1] - geo_half.head_center[1])
    assert delta_y > 0.5, (
        f"Idle bob: head y difference at 0ms vs 600ms is {delta_y:.3f}px, expected > 0.5px"
    )


# ── T4: Walk cycle alternates (bob changes y over time) ──────────────────────

def test_walk_cycle_alternates_feet():
    """At t=0 and t=400ms, the head y of a walking character must differ (walk bob).

    The walk bob has a 400ms half-period, so at t=0 and t=400ms the sin phase
    differs by π — head y should be at opposite extremes (difference > 1px).
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
    # Bootstrap — first call with walk pose
    geo0 = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    # Drive walk_phase_t to ~400ms by ticking 400/8.333 ≈ 48 frames.
    ticks_400ms = int(400 / 8.333)
    for _ in range(ticks_400ms):
        geo_400 = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    delta_y = abs(geo0.head_center[1] - geo_400.head_center[1])
    assert delta_y > 1.0, (
        f"Walk bob: head y diff at t=0 vs t=400ms is {delta_y:.3f}px, expected > 1px"
    )
