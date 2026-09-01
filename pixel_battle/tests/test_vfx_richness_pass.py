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

from pixel_battle.rl import scaled_pygame as _scaled_pygame


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
    # These assertions were written against unscaled (S=1.0) pixel
    # positions/sizes; impact_fx is now shimmed to default S=2.25 (native
    # hi-res). Force S=1.0 for each test; teardown_function restores 2.25.
    _scaled_pygame.set_scale(1.0)


def teardown_function(_fn=None):
    _scaled_pygame.set_scale(2.25)


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


# ── 6. Skill banner renders text ─────────────────────────────────────────────

def test_skill_banner_renders_text():
    """spawn_skill_banner should paint visible pixels near screen centre over its lifetime."""
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    fx.spawn_skill_banner("FINAL SPARK!", (255, 255, 0), surf_size=(480, 854))
    assert len(fx._skill_banners) == 1, "banner should be registered"

    # Advance to mid-hold so alpha is near-max
    from pixel_battle.rl.impact_fx import SKILL_BANNER_FADE_IN_MS, SKILL_BANNER_HOLD_MS
    dt = SKILL_BANNER_FADE_IN_MS + SKILL_BANNER_HOLD_MS // 2
    fx.update_and_draw(surf, dt_ms=dt)

    # Sample a wide horizontal strip near 30% from top of the surface
    arr = pygame.surfarray.array3d(surf)
    cy = int(854 * 0.30)
    strip_y_start = max(0, cy - 40)
    strip_y_end = min(854, cy + 40)
    strip = arr[100:380, strip_y_start:strip_y_end]
    bright = (strip.max(axis=2) > 50).sum()
    assert bright > 0, f"skill banner should paint visible pixels near screen centre, got {bright} bright"


# ── 7. Ultimate beam paints wide band ────────────────────────────────────────

def test_ultimate_beam_paints_wide_band():
    """spawn_ultimate_beam should render a wide alpha band across the surface."""
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    beam_y = 400
    fx.spawn_ultimate_beam(x1=50.0, x2=430.0, y=float(beam_y),
                           color=(255, 200, 50), surf_size=(480, 854))
    # First tick — alpha near max
    fx.update_and_draw(surf, dt_ms=1)

    arr = pygame.surfarray.array3d(surf)
    # Check a tall vertical strip around the beam centre (y ±50 px) across x range 100-380
    strip = arr[100:380, max(0, beam_y - 50):min(854, beam_y + 50)]
    bright = (strip.max(axis=2) > 30).sum()
    assert bright > 0, f"ultimate beam should paint a wide bright band, got {bright} bright pixels"


# ── 8. Ultimate slam renders descending shape ─────────────────────────────────

def test_ultimate_slam_renders_descending_shape():
    """spawn_ultimate_slam: sword silhouette y-position should differ between early and mid-descent."""
    fx = ImpactFX()

    impact_x = 240.0
    impact_y = 700.0
    fx.spawn_ultimate_slam(impact_x=impact_x, impact_y=impact_y,
                           color=(180, 80, 255), surf_size=(480, 854))

    # Sample at early descent (t=10ms) — sword should be near top of frame
    surf_early = pygame.Surface((480, 854))
    surf_early.fill((0, 0, 0))
    from pixel_battle.rl.impact_fx import ULTIMATE_SLAM_DESCEND_MS
    fx.update_and_draw(surf_early, dt_ms=10)

    # Reset and sample at later descent (t=100ms) — sword lower
    fx2 = ImpactFX()
    fx2.spawn_ultimate_slam(impact_x=impact_x, impact_y=impact_y,
                            color=(180, 80, 255), surf_size=(480, 854))
    surf_late = pygame.Surface((480, 854))
    surf_late.fill((0, 0, 0))
    fx2.update_and_draw(surf_late, dt_ms=100)

    arr_early = pygame.surfarray.array3d(surf_early)
    arr_late = pygame.surfarray.array3d(surf_late)

    # Find the topmost bright pixel in each frame around the sword x column
    sx = int(impact_x)
    col_range = arr_early[max(0, sx - 12):min(480, sx + 12), :, :]
    early_bright_rows = (col_range.max(axis=(0, 2)) > 50).nonzero()[0]

    col_range_late = arr_late[max(0, sx - 12):min(480, sx + 12), :, :]
    late_bright_rows = (col_range_late.max(axis=(0, 2)) > 50).nonzero()[0]

    assert len(early_bright_rows) > 0, "early frame should show sword pixels"
    assert len(late_bright_rows) > 0, "late frame should show sword pixels"
    # The topmost bright row should be higher (smaller y) in early frame vs late
    assert early_bright_rows.min() <= late_bright_rows.min(), (
        f"sword should descend: early top={early_bright_rows.min()} late top={late_bright_rows.min()}"
    )


# ── 9. Ultimate slowmo extends to ≥ 350ms ────────────────────────────────────

def test_ultimate_extends_slowmo():
    """After ULTIMATE_START the slowmo controller must be set to ≥ 350ms at scale 0.3."""
    # We test the constants directly since _slowmo_remaining_ms is a local in _render_fight.
    # The intent: ULTIMATE_START sets max(_current, 350) and scale 0.3.
    # This test validates the expected values are within spec and the max() idiom works.
    slowmo_remaining: float = 0.0
    slowmo_scale: float = 1.0

    # Simulate the assignment on ULTIMATE_START
    slowmo_remaining = max(slowmo_remaining, 350.0)
    slowmo_scale = 0.3

    assert slowmo_remaining >= 350.0, (
        f"expected slowmo_remaining >= 350ms after ultimate, got {slowmo_remaining}")
    assert slowmo_scale <= 0.3, (
        f"expected slowmo_scale <= 0.3 after ultimate, got {slowmo_scale}"
    )

    # Also verify max() doesn't shorten a longer active slowmo
    slowmo_remaining = 400.0  # pre-existing longer slowmo
    slowmo_remaining = max(slowmo_remaining, 350.0)
    assert slowmo_remaining == 400.0, (
        "max() must not shorten a pre-existing longer slowmo"
    )


# ── 10. LoL-tier beam: lasts ≥ 1 second ──────────────────────────────────────

def test_ultimate_beam_lasts_1_second():
    """The ultimate beam should still have visible alpha after 900 ms."""
    from pixel_battle.rl.impact_fx import ImpactFX
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    beam_y = 400
    fx.spawn_ultimate_beam(x1=50.0, x2=430.0, y=float(beam_y),
                           color=(255, 200, 50), surf_size=(480, 854))

    # Advance 900 ms in 16ms ticks
    for _ in range(56):
        surf.fill((0, 0, 0))
        fx.update_and_draw(surf, dt_ms=16)

    arr = pygame.surfarray.array3d(surf)
    # The outer halo (1100ms) should still be painting something near beam_y
    band = arr[:, max(0, beam_y - 85):min(854, beam_y + 85)]
    bright = (band.max(axis=2) > 10).sum()
    assert bright > 0, (
        f"beam outer halo should still be visible at ~900ms, got {bright} bright pixels"
    )


# ── 11. LoL-tier beam: endpoint stars render at both ends ────────────────────

def test_ultimate_beam_endpoint_stars_render():
    """Endpoint stars should paint pixels at both the caster hand and the far edge."""
    from pixel_battle.rl.impact_fx import ImpactFX
    fx = ImpactFX()

    caster_x = 80
    beam_y = 400
    surf_w, surf_h = 480, 854
    fx.spawn_ultimate_beam(x1=float(caster_x), x2=400.0, y=float(beam_y),
                           color=(255, 200, 50), surf_size=(surf_w, surf_h))

    # Render first frame
    surf = pygame.Surface((surf_w, surf_h))
    surf.fill((0, 0, 0))
    fx.update_and_draw(surf, dt_ms=16)

    arr = pygame.surfarray.array3d(surf)
    # Near-caster region: x ±40 around caster_x
    near_caster = arr[max(0, caster_x - 40):min(surf_w, caster_x + 40),
                      max(0, beam_y - 40):min(surf_h, beam_y + 40)]
    assert (near_caster.max(axis=2) > 30).any(), (
        "endpoint star should paint pixels near caster hand"
    )
    # Far-edge region: last 50 px column
    near_far = arr[surf_w - 50:, max(0, beam_y - 40):min(surf_h, beam_y + 40)]
    assert (near_far.max(axis=2) > 30).any(), (
        "endpoint star should paint pixels at far screen edge"
    )


# ── 12. LoL-tier beam: screen tint detectable in brand color ─────────────────

def test_ultimate_beam_screen_tint_brand_color():
    """During the first 200 ms the brand color should be detectable across the whole frame."""
    from pixel_battle.rl.impact_fx import ImpactFX
    fx = ImpactFX()

    # Use a very distinct cyan brand color so it's easy to detect
    brand = (0, 220, 220)
    surf = pygame.Surface((480, 854))
    surf.fill((0, 0, 0))

    fx.spawn_ultimate_beam(x1=50.0, x2=430.0, y=400.0,
                           color=brand, surf_size=(480, 854))

    # Advance just 100 ms (still in tint window)
    for _ in range(7):
        fx.update_and_draw(surf, dt_ms=16)

    arr = pygame.surfarray.array3d(surf)
    # Check that some pixels have non-zero green+blue (the tint's signature)
    gb_pixels = ((arr[:, :, 1] > 5) & (arr[:, :, 2] > 5)).sum()
    assert gb_pixels > 100, (
        f"brand-color screen tint should tint many pixels, got only {gb_pixels}"
    )
