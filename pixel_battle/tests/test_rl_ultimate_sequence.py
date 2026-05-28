"""Tests for UltimateSequence — 3-phase cinematic state machine."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl.ultimate_sequence import UltimateSequence, Phase


def test_ultimate_sequence_phases():
    """ULTIMATE_START event → ANTICIPATION → RELEASE → AFTERMATH at correct ms."""
    seq = UltimateSequence()
    # Before trigger: inactive
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase is None

    # Trigger
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.ANTICIPATION

    # Advance to just before RELEASE boundary (1500ms - 16ms elapsed)
    for _ in range(93):          # 93 × 16ms = 1488ms total elapsed (still in ANTICIPATION)
        r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.ANTICIPATION

    # One more tick crosses 1500ms → RELEASE
    r = seq.tick(triggered=False, dt_ms=16)   # now at 1504ms
    assert r.phase == Phase.RELEASE

    # Advance through RELEASE (200ms) → should enter AFTERMATH
    for _ in range(13):          # 13 × 16ms = 208ms
        r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.AFTERMATH

    # Advance through AFTERMATH (1000ms)
    for _ in range(63):          # 63 × 16ms = 1008ms
        r = seq.tick(triggered=False, dt_ms=16)
    # After AFTERMATH: phase returns to None
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase is None


def test_ultimate_sequence_freezes_engine():
    """dt_scale == 0.0 during ANTICIPATION phase."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.dt_scale == 0.0, f"Expected dt_scale=0.0 during ANTICIPATION, got {r.dt_scale}"


def test_caster_aura_grows():
    """Aura radius at t=200ms < t=1400ms (grows through anticipation)."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))

    # Tick to t≈200ms (12 ticks × 16ms = 192ms)
    r_early = None
    for _ in range(12):
        r_early = seq.tick(triggered=False, dt_ms=16)

    # Tick to t≈1400ms (another 75 ticks × 16ms = 1200ms → total ≈1392ms)
    r_late = None
    for _ in range(75):
        r_late = seq.tick(triggered=False, dt_ms=16)

    assert r_early is not None and r_late is not None
    assert r_early.caster_aura_radius < r_late.caster_aura_radius, (
        f"Aura radius should grow: early={r_early.caster_aura_radius} "
        f"late={r_late.caster_aura_radius}"
    )


def test_release_flash_alpha_decays():
    """Release flash alpha at t=0 (just entered RELEASE) > alpha at t=200ms (end of RELEASE)."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))

    # Fast-forward to RELEASE phase (advance 1500ms in large steps)
    for _ in range(94):          # 94 × 16ms = 1504ms → enters RELEASE
        seq.tick(triggered=False, dt_ms=16)

    r_start = seq.tick(triggered=False, dt_ms=16)
    assert r_start.phase == Phase.RELEASE
    alpha_start = r_start.release_flash_alpha

    # Advance to end of RELEASE (200ms = 12 more ticks × 16ms = 192ms)
    r_end = None
    for _ in range(12):
        r_end = seq.tick(triggered=False, dt_ms=16)

    assert r_end is not None
    assert alpha_start > r_end.release_flash_alpha, (
        f"Flash alpha should decay: start={alpha_start} end={r_end.release_flash_alpha}"
    )


def test_smoke_cloud_drifts_upward():
    """Smoke particles at t=500ms have lower y (higher on screen) than at t=0."""
    from pixel_battle.rl.impact_fx import ImpactFX
    import pygame
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    fx.spawn_smoke_cloud(x=240.0, y=600.0, color=(180, 180, 180))

    # Record initial y positions of smoke particles
    initial_ys = [p.y for p in fx._smoke_clouds]

    # Advance 500ms (31 × 16ms = 496ms)
    for _ in range(31):
        fx.update_and_draw(surf, dt_ms=16)

    # Record final y positions
    final_ys = [p.y for p in fx._smoke_clouds]

    assert len(initial_ys) > 0, "spawn_smoke_cloud should create particles"
    if final_ys:
        avg_initial = sum(initial_ys) / len(initial_ys)
        avg_final = sum(final_ys) / len(final_ys)
        assert avg_final < avg_initial, (
            f"Smoke should drift upward (lower y): initial_avg={avg_initial:.1f} "
            f"final_avg={avg_final:.1f}"
        )
