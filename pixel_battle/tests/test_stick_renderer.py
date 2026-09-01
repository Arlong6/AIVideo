"""Stick renderer draws a stick figure from a Character's physics state."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import draw_stick_figure
from pixel_battle.rl import scaled_pygame as _scaled_pygame

WIDTH, HEIGHT = 480, 854
RED = (220, 60, 60)
BLUE = (60, 130, 220)


@pytest.fixture(autouse=True)
def _unscaled_shim():
    """These assertions were written against unscaled (S=1.0) pixel
    positions/sizes; stick_renderer is now shimmed to default S=2.25
    (native hi-res). Force S=1.0 for each test and restore the production
    default afterward."""
    _scaled_pygame.set_scale(1.0)
    yield
    _scaled_pygame.set_scale(2.25)


@pytest.fixture
def surf():
    pygame.init()
    pygame.display.set_mode((1, 1))
    return pygame.Surface((WIDTH, HEIGHT))


def _has_nonzero_pixel_in_box(surf, cx, cy, half):
    """Check at least one non-background pixel exists in a square around (cx, cy)."""
    arr = pygame.surfarray.array3d(surf)
    x0 = max(0, cx - half)
    x1 = min(WIDTH, cx + half)
    y0 = max(0, cy - half)
    y1 = min(HEIGHT, cy + half)
    region = arr[x0:x1, y0:y1]
    return bool((region.sum(axis=-1) > 0).any())


def test_draw_writes_pixels_near_character_position(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0  # near ground
    draw_stick_figure(surf, c, RED)
    # Stick figure spans roughly cy - 90 (head top) to cy (feet)
    assert _has_nonzero_pixel_in_box(surf, 200, 580, 50)


def test_draw_uses_provided_color(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0
    draw_stick_figure(surf, c, RED)
    arr = pygame.surfarray.array3d(surf)
    # Find a non-background pixel
    nonbg = (arr.sum(axis=-1) > 0)
    assert nonbg.any()
    # Sample one and check it's red-ish (R channel dominant)
    ys, xs = nonbg.nonzero()[1], nonbg.nonzero()[0]
    sample_x, sample_y = xs[0], ys[0]
    r, g, b = arr[sample_x, sample_y]
    assert r > g and r > b, f"expected red-dominant pixel, got rgb=({r},{g},{b})"


def test_draw_does_not_crash_in_attack_pose(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0
    c.action_state = "attacking"
    c.attack_phase = "windup"
    c.attack_phase_t = 50
    draw_stick_figure(surf, c, RED)


def test_draw_does_not_crash_when_jumping(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 500.0
    c.on_ground = False
    c.vel_y = -5.0
    draw_stick_figure(surf, c, BLUE)


def test_left_and_right_chars_are_distinct_colors(surf):
    left = Character.load("brick_phone")
    left.reset_physics(initial_x=150.0, facing=1)
    left.pos_y = 600.0
    right = Character.load("glass_slab")
    right.reset_physics(initial_x=330.0, facing=-1)
    right.pos_y = 600.0
    draw_stick_figure(surf, left, RED)
    draw_stick_figure(surf, right, BLUE)
    arr = pygame.surfarray.array3d(surf)
    red_pixels = ((arr[:, :, 0] > 150) & (arr[:, :, 2] < 100)).sum()
    blue_pixels = ((arr[:, :, 2] > 150) & (arr[:, :, 0] < 100)).sum()
    assert red_pixels > 50, "left character should have visible red pixels"
    assert blue_pixels > 50, "right character should have visible blue pixels"


# ── New tests: smear, impact burst, landing dust ──────────────────────────────

def test_smear_drawn_when_velocity_high(surf):
    """When |vel_x| > threshold, additional ghost pixels appear behind char."""
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=300.0, facing=1)
    c.pos_y = 600.0
    c.vel_x = 5.0  # moving fast
    draw_stick_figure(surf, c, RED)
    # Pixels should exist BEHIND character (smaller x for facing=1, vel>0 means moving right
    # → trail is to the left). Ghost offset is -vel_x*{4,8} so trail sits at x~[248:285].
    arr = pygame.surfarray.array3d(surf)
    trail_region = arr[248:275, 450:600]  # box BEHIND main body (jointed skeleton geometry)
    assert (trail_region.sum(axis=-1) > 0).any(), "expected smear trail behind moving char"


def test_no_smear_when_stationary(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=300.0, facing=1)
    c.pos_y = 600.0
    c.vel_x = 0.0
    draw_stick_figure(surf, c, RED)
    arr = pygame.surfarray.array3d(surf)
    # Nothing should be drawn in the ghost zone (left of main body) when stationary
    trail_region = arr[248:275, 450:600]
    assert not (trail_region.sum(axis=-1) > 0).any(), "no smear expected at rest"


def test_spawn_impact_burst_draws_radial_lines(surf):
    from pixel_battle.rl.stick_renderer import spawn_impact_burst
    spawn_impact_burst(surf, 240, 400, (255, 200, 0), size=20)
    arr = pygame.surfarray.array3d(surf)
    # Check that pixels were drawn around the center
    region = arr[220:260, 380:420]
    assert (region.sum(axis=-1) > 0).any(), "burst should draw some pixels"


def test_spawn_landing_dust_draws_at_ground(surf):
    from pixel_battle.rl.stick_renderer import spawn_landing_dust
    spawn_landing_dust(surf, 200, 700, (180, 180, 180))
    arr = pygame.surfarray.array3d(surf)
    region = arr[170:230, 680:710]
    assert (region.sum(axis=-1) > 0).any(), "dust should produce visible pixels at ground level"
