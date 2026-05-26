"""Tests for the VFX-richness + hit-feel pass (Script 01 scope).

Five tests:
  1. test_buff_pillar_spawns_particles
  2. test_beam_paints_horizontal_strip
  3. test_camera_shake_decays
  4. test_hit_ring_expands
  5. test_ultimate_event_spawns_burst
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


def setup_function(_fn=None):
    """Re-initialise pygame before every test.

    Some other tests in the suite call pygame.quit(), which shuts the font
    subsystem.  Re-initialising here makes each test self-contained.
    """
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))


# Ensure at least initial init for module-level imports
setup_function()

from pixel_battle.rl.impact_fx import ImpactFX, CameraShake


# ── 1. Buff pillar ────────────────────────────────────────────────────────────

def test_buff_pillar_spawns_particles():
    """spawn_buff_pillar must add ≥10 active spark particles."""
    fx = ImpactFX()
    fx.spawn_buff_pillar(x=240, y=400, color=(255, 220, 80))
    assert len(fx._active) >= 10, (
        f"expected ≥10 particles, got {len(fx._active)}")


# ── 2. Beam paints horizontal strip ──────────────────────────────────────────

def test_beam_paints_horizontal_strip():
    """spawn_beam_fx followed by update_and_draw should mark pixels along the beam path."""
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    # Beam from x=50 to x=430 at y=300
    fx.spawn_beam_fx(x1=50, x2=430, y=300, color=(255, 230, 100))
    fx.update_and_draw(surf, dt_ms=1)   # first tick — beam alpha is near max

    # Sample pixels along the beam path
    arr = pygame.surfarray.array3d(surf)
    # Check a horizontal strip at y=297..303, x=100..380
    strip = arr[100:380, 297:303]
    bright = (strip.max(axis=2) > 50).sum()
    assert bright > 0, "beam should have painted bright pixels along the horizontal path"


# ── 3. Camera shake decays ────────────────────────────────────────────────────

def test_camera_shake_decays():
    """CameraShake returns a non-zero offset during the shake window and (0,0) after."""
    shake = CameraShake()
    shake.trigger(magnitude_px=10.0, duration_ms=100.0)

    # During the shake we should see non-zero (stochastic — run a few ticks)
    offsets_during = [shake.update(dt_ms=10) for _ in range(5)]
    any_nonzero = any(dx != 0 or dy != 0 for dx, dy in offsets_during)
    assert any_nonzero, "expected at least one non-zero offset while shaking"

    # After duration elapses (already consumed 50 ms above; consume the rest)
    for _ in range(6):          # 6 × 10 ms = 60 ms → total 110 ms > 100 ms
        shake.update(dt_ms=10)

    # Now the shake should be expired
    dx, dy = shake.update(dt_ms=16)
    assert dx == 0 and dy == 0, (
        f"expected (0, 0) after shake expires, got ({dx}, {dy})")


# ── 4. Hit ring expands ───────────────────────────────────────────────────────

def test_hit_ring_expands():
    """spawn_hit_ring: at t=0 small; at mid-duration larger; at full duration gone."""
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    from pixel_battle.rl.impact_fx import HIT_RING_MS, _HitRing

    fx.spawn_hit_ring(x=240, y=400, color=(255, 255, 100))
    assert len(fx._hit_rings) == 1

    ring = fx._hit_rings[0]
    r0 = ring.min_r  # initial radius (before any update)
    assert r0 < ring.max_r, "initial ring radius should be less than max"

    # Advance to mid-duration
    half_ms = HIT_RING_MS // 2
    fx.update_and_draw(surf, dt_ms=half_ms)
    assert len(fx._hit_rings) == 1, "ring should still be alive at mid-duration"
    ring_mid = fx._hit_rings[0]
    mid_frac = ring_mid.age_ms / ring_mid.life_ms
    r_mid = int(ring_mid.min_r + (ring_mid.max_r - ring_mid.min_r) * mid_frac)
    assert r_mid > r0, f"ring should have grown: r_mid={r_mid} vs r0={r0}"

    # Advance past full duration
    fx.update_and_draw(surf, dt_ms=HIT_RING_MS + 20)
    assert len(fx._hit_rings) == 0, "ring should be gone after full duration"


# ── 5. Ultimate event spawns burst ───────────────────────────────────────────

def test_ultimate_event_spawns_burst():
    """spawn_ultimate_burst adds ≥30 sparks, sets flash, activates camera shake, adds text."""
    fx = ImpactFX()
    initial_sparks = len(fx._active)

    color = (255, 200, 50)
    fx.spawn_ultimate_burst(x=240, y=300, color=color, surf_size=(480, 854))

    # ≥30 radial sparks
    assert len(fx._active) - initial_sparks >= 30, (
        f"expected ≥30 sparks, got {len(fx._active) - initial_sparks}")

    # Flash was requested
    assert fx._flash_alpha > 0, "flash_alpha should be >0 after ultimate burst"

    # Camera shake is active
    assert fx.camera_shake.active, "camera_shake should be active after ultimate burst"

    # "ULTIMATE!" floating text was added
    texts = [t.text for t in fx._texts]
    assert "ULTIMATE!" in texts, f"expected 'ULTIMATE!' text, got {texts}"
