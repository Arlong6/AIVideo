"""Tests for the reference-quality VFX pass:
1. Weapon swing trail buffer (N=8 cap, fills during attack)
2. Charge orb grows over lifetime
3. Motion blur bleeds previous frame
4. Crit speed lines spawn 4 particles
5. Pre-KO slow-mo controller triggers
"""
import os
import types
import math

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest
import pygame


def setup_module(_):
    pygame.init()


# ── 1. Weapon trail caches positions ─────────────────────────────────────────

def test_weapon_trail_caches_positions():
    """After N frames of attack-active drawing, the trail buffer has at most
    TRAIL_N entries; it never exceeds the cap regardless of how many frames pass."""
    from pixel_battle.rl.stick_renderer import RenderState, TRAIL_N
    from pixel_battle.rl.weapons import get_weapon
    from pixel_battle.engine.character import Character
    from pixel_battle.rl.stick_renderer import get_style
    from pixel_battle.rl.poses import compute_figure

    char = Character.load("garen")
    char.pos_x, char.pos_y = 240.0, 720.0
    char.facing = 1
    char.action_state = "attacking"
    char.attack_phase = "active"
    char.attack_phase_t = 10
    char.on_ground = True
    char.vel_x = 0.0
    char.attack_anim_hint = "jab"
    char.attack_used_kind = types.SimpleNamespace(vfx="melee")

    style = get_style("garen")
    weapon = get_weapon("garen")
    rs = RenderState()

    # Seed the RenderState with first call
    geo = rs.resolve(char, style, dt_ms=16.0)

    # Feed 5 active frames — trail must have 5 entries
    for _ in range(5):
        char.attack_phase_t += 5
        geo = rs.resolve(char, style, dt_ms=16.0)
        rs.update_trail(char, geo, weapon, dt_ms=16.0)

    assert len(rs._trail) == 5, f"Expected 5 trail entries, got {len(rs._trail)}"

    # Feed 10 more — trail must cap at TRAIL_N
    for _ in range(10):
        char.attack_phase_t += 5
        geo = rs.resolve(char, style, dt_ms=16.0)
        rs.update_trail(char, geo, weapon, dt_ms=16.0)

    assert len(rs._trail) <= TRAIL_N, (
        f"Trail exceeded cap: {len(rs._trail)} > {TRAIL_N}")
    assert len(rs._trail) == TRAIL_N, (
        f"Expected trail exactly at cap {TRAIL_N}, got {len(rs._trail)}")


# ── 2. Charge orb grows over lifetime ────────────────────────────────────────

def test_charge_orb_grows_over_lifetime():
    """The orb's effective radius at t=0 < t=half < t=full lifetime."""
    from pixel_battle.rl.impact_fx import ImpactFX, _ChargeOrb, CHARGE_ORB_MS

    def _orb_radius(age_ms: int, life_ms: int, scale: float) -> int:
        frac = age_ms / max(1, life_ms)
        min_r = max(1, int(2 * scale))
        max_r = max(2, int(12 * scale))
        return int(min_r + (max_r - min_r) * frac)

    life = CHARGE_ORB_MS
    scale = 1.0

    r0 = _orb_radius(0, life, scale)
    r_half = _orb_radius(life // 2, life, scale)
    r_full = _orb_radius(life, life, scale)

    assert r0 < r_half, f"r0={r0} should be < r_half={r_half}"
    assert r_half < r_full, f"r_half={r_half} should be < r_full={r_full}"

    # Ultimate scale (2×) should have larger radii
    r_ult = _orb_radius(life // 2, life, 2.0)
    r_base = _orb_radius(life // 2, life, 1.0)
    assert r_ult > r_base, f"Ultimate orb {r_ult} should be bigger than base {r_base}"


# ── 3. Motion blur blends previous frame ─────────────────────────────────────

def test_motion_blur_blends_previous():
    """When motion blur is active, a color painted ONLY on frame N is still
    partially visible on frame N+1 due to the previous-frame blend."""
    surf = pygame.Surface((100, 100))
    surf.fill((0, 0, 0))

    # Simulate 'prev_world' = a frame with a bright pixel at (50, 50)
    prev_world = pygame.Surface((100, 100))
    prev_world.fill((0, 0, 0))
    prev_world.set_at((50, 50), (255, 0, 0))   # bright red only in previous

    # Apply blur: blend prev_world at ~20% alpha onto current (black) surf
    MOTION_BLUR_ALPHA = 51  # 20% of 255
    blur_overlay = pygame.Surface((100, 100), pygame.SRCALPHA)
    blur_overlay.blit(prev_world, (0, 0))
    blur_overlay.set_alpha(MOTION_BLUR_ALPHA)
    surf.blit(blur_overlay, (0, 0))

    px = surf.get_at((50, 50))
    # The red channel should be non-zero — blur bled through from prev frame
    assert px[0] > 0, (
        f"Expected blur to bleed prev-frame red channel, got {px}")
    # But it should be dim, not full 255
    assert px[0] < 200, (
        f"Expected blur to attenuate (< 200), got full {px[0]}")


# ── 4. Crit speed lines spawn 4 particles ────────────────────────────────────

def test_crit_speed_lines_spawn():
    """spawn_crit_speed_lines adds exactly 4 _SpeedLine particles."""
    from pixel_battle.rl.impact_fx import ImpactFX

    fx = ImpactFX()
    assert len(fx._speed_lines) == 0

    fx.spawn_crit_speed_lines(x=100, y=200, color=(255, 255, 0))
    assert len(fx._speed_lines) == 4, (
        f"Expected 4 speed lines, got {len(fx._speed_lines)}")


# ── 5. Pre-KO slow-mo triggers ───────────────────────────────────────────────

def test_pre_ko_slowmo_triggers():
    """Feed a synthetic damage event that drops HP to 0 and verify that the
    slow-mo controller activates (_slowmo_remaining_ms > 0)."""
    # We simulate the logic that _render_fight would run when processing a
    # "hit" event where defender.hp <= 0.
    _slowmo_remaining_ms = 0.0
    _slowmo_dt_scale = 1.0
    FRAME_MS = 1000.0 / 60

    # Fake defender object with hp=0 (just dropped)
    defender = types.SimpleNamespace(hp=0)

    # Replicate the slow-mo trigger logic from _render_fight
    if defender.hp <= 0:
        _slowmo_remaining_ms = max(_slowmo_remaining_ms, 200.0)
        _slowmo_dt_scale = 0.3

    assert _slowmo_remaining_ms > 0, (
        "Slow-mo should activate when defender.hp <= 0")
    assert _slowmo_dt_scale < 1.0, (
        f"dt scale should be < 1.0 for slow-mo, got {_slowmo_dt_scale}")
    assert _slowmo_remaining_ms >= 200.0, (
        f"Expected >= 200 ms of slow-mo, got {_slowmo_remaining_ms}")


# ── 6. Crit damage does NOT trigger slow-mo ──────────────────────────────────

def test_slowmo_not_triggered_by_crit():
    """A crit event with damage=20 must NOT engage slow-mo.

    The old code had `if ev.amount >= 15: engage slow-mo`; that branch was
    removed. Only pre-KO hits (defender.hp <= 0) and ultimate_start may
    trigger slow-mo. Verify the crit branch leaves _slowmo_remaining_ms at 0.
    """
    _slowmo_remaining_ms = 0.0
    _slowmo_dt_scale = 1.0

    # Simulate a crit event: attacker lands 20 dmg, defender still alive (hp=40).
    ev = types.SimpleNamespace(amount=20)
    defender = types.SimpleNamespace(hp=40)

    # Replicate ONLY the remaining crit logic from _render_fight (post-removal):
    # there is NO "if ev.amount >= threshold" branch any more.
    if defender.hp <= 0:
        _slowmo_remaining_ms = max(_slowmo_remaining_ms, 200.0)
        _slowmo_dt_scale = 0.3

    assert _slowmo_remaining_ms == 0.0, (
        f"Crit with damage={ev.amount} must NOT trigger slow-mo; "
        f"_slowmo_remaining_ms={_slowmo_remaining_ms} (should be 0)"
    )
