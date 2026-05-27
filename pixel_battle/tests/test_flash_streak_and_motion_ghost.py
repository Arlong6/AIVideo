"""Tests for Flash streak ghost trail and motion afterimage effects."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import numpy as np
import pytest

from pixel_battle.rl.impact_fx import ImpactFX, FLASH_STREAK_MS


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ── Flash streak ──────────────────────────────────────────────────────────────

def test_flash_streak_spawns_ghosts():
    """spawn_flash_streak(0, 100, 200, white, n_ghosts=5) must add 5 ghost entries."""
    fx = ImpactFX()
    fx.spawn_flash_streak(from_x=0.0, to_x=100.0, hip_y=200.0,
                          color=(255, 255, 255), n_ghosts=5)
    assert len(fx._streaks) == 1
    streak = fx._streaks[0]
    assert len(streak.ghost_pts) == 5
    assert len(streak.ghost_base_alphas) == 5


def test_flash_streak_ghost_alphas_decay_along_path():
    """First ghost (near from_x) must have higher alpha than last (near to_x)."""
    fx = ImpactFX()
    fx.spawn_flash_streak(from_x=0.0, to_x=400.0, hip_y=300.0,
                          color=(100, 200, 255), n_ghosts=5)
    alphas = fx._streaks[0].ghost_base_alphas
    assert alphas[0] > alphas[-1], "Alpha should be higher near from_x than near to_x"


def test_flash_streak_draws_pixels():
    """update_and_draw with an active streak must paint non-zero pixels."""
    fx = ImpactFX()
    surf = pygame.Surface((480, 854), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))
    fx.spawn_flash_streak(from_x=50.0, to_x=400.0, hip_y=480.0,
                          color=(255, 200, 50), n_ghosts=5)
    fx.update_and_draw(surf, dt_ms=16)
    arr = pygame.surfarray.array_alpha(surf)
    assert arr.sum() > 0, "Flash streak drew no pixels"


def test_flash_streak_expires_after_lifetime():
    """After FLASH_STREAK_MS ms the streak must be removed."""
    fx = ImpactFX()
    fx.spawn_flash_streak(from_x=0.0, to_x=200.0, hip_y=300.0,
                          color=(255, 255, 255), n_ghosts=3)
    surf = pygame.Surface((480, 854), pygame.SRCALPHA)
    elapsed = 0
    while elapsed < FLASH_STREAK_MS + 32:
        fx.update_and_draw(surf, dt_ms=16)
        elapsed += 16
    assert len(fx._streaks) == 0, "Streak should have been culled after its lifetime"


# ── Motion ghosts are tested indirectly via the renderer ─────────────────────
# (draw_stick_figure already renders motion-smear ghosts when |vel_x| > threshold)

def test_draw_stick_figure_produces_ghosts_at_high_velocity():
    """draw_stick_figure with |vel_x| > SMEAR_VEL_THRESHOLD must paint more pixels
    than the same figure at rest (the ghost smear adds ink)."""
    from pixel_battle.engine.character import Character
    from pixel_battle.rl.stick_renderer import draw_stick_figure, SMEAR_VEL_THRESHOLD

    surf_fast = pygame.Surface((480, 854))
    surf_fast.fill((0, 0, 0))
    surf_idle = pygame.Surface((480, 854))
    surf_idle.fill((0, 0, 0))

    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 530.0
    c.facing = 1
    c.action_state = "walking"
    c.on_ground = True

    # Fast (smear threshold exceeded)
    c.vel_x = SMEAR_VEL_THRESHOLD + 2.0
    draw_stick_figure(surf_fast, c, (90, 205, 115))

    # Idle (no smear)
    c.vel_x = 0.0
    c.action_state = "idle"
    draw_stick_figure(surf_idle, c, (90, 205, 115))

    fast_px = int(np.any(pygame.surfarray.array3d(surf_fast) != 0, axis=-1).sum())
    idle_px = int(np.any(pygame.surfarray.array3d(surf_idle) != 0, axis=-1).sum())
    assert fast_px > idle_px, (
        f"Fast-movement figure ({fast_px} px) should have more pixels than idle "
        f"({idle_px} px) due to ghost smear"
    )


# ── Motion ghost snapshot queue ───────────────────────────────────────────────

def test_motion_ghost_spawns_during_fast_movement():
    """RenderState must accumulate motion ghosts when |vel_x| > threshold
    and the character is on the ground.  After MOTION_GHOST_INTERVAL_FRAMES
    render calls we expect at least 1 ghost in the queue."""
    from pixel_battle.engine.character import Character
    from pixel_battle.rl.stick_renderer import (
        RenderState, MOTION_GHOST_VEL_THRESHOLD, MOTION_GHOST_INTERVAL_FRAMES,
        get_style,
    )

    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 530.0
    c.facing = 1
    c.action_state = "walking"
    c.on_ground = True
    c.vel_x = MOTION_GHOST_VEL_THRESHOLD + 1.0   # fast enough to trigger

    style = get_style("garen")
    rs = RenderState()
    surf = pygame.Surface((480, 854))

    # Drive 10 render frames — should spawn at least floor(10/INTERVAL) ghosts
    for _ in range(10):
        rs.resolve(c, style, dt_ms=16.0)
        rs.update_motion_ghosts(c, style, dt_ms=16.0)

    expected_min = 10 // MOTION_GHOST_INTERVAL_FRAMES
    assert len(rs._motion_ghosts) >= expected_min, (
        f"Expected ≥{expected_min} motion ghost(s) after 10 fast frames, "
        f"got {len(rs._motion_ghosts)}"
    )


def test_motion_ghost_max_capped():
    """Queue must not exceed MOTION_GHOST_MAX entries."""
    from pixel_battle.engine.character import Character
    from pixel_battle.rl.stick_renderer import (
        RenderState, MOTION_GHOST_VEL_THRESHOLD, MOTION_GHOST_MAX, get_style,
    )

    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 530.0
    c.facing = 1
    c.action_state = "walking"
    c.on_ground = True
    c.vel_x = MOTION_GHOST_VEL_THRESHOLD + 3.0

    style = get_style("garen")
    rs = RenderState()

    # Drive enough frames to saturate the queue (well over MOTION_GHOST_MAX * INTERVAL)
    for _ in range(50):
        rs.resolve(c, style, dt_ms=16.0)
        rs.update_motion_ghosts(c, style, dt_ms=16.0)

    assert len(rs._motion_ghosts) <= MOTION_GHOST_MAX, (
        f"Motion ghost queue exceeded max: {len(rs._motion_ghosts)} > {MOTION_GHOST_MAX}"
    )
