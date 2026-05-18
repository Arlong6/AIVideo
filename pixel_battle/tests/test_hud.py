import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.hud import DamagePopupLayer


def test_damage_popup_layer_starts_empty():
    layer = DamagePopupLayer()
    assert len(layer.popups) == 0


def test_spawn_adds_popup():
    layer = DamagePopupLayer()
    layer.spawn(x=240, y=400, dmg=12, is_crit=False)
    assert len(layer.popups) == 1
    p = layer.popups[0]
    assert p.dmg == 12
    assert p.is_crit is False
    assert p.age == 0


def test_popup_ages_out_after_lifetime():
    layer = DamagePopupLayer()
    pygame.init()
    surface = pygame.Surface((480, 854))
    layer.spawn(x=240, y=400, dmg=5, is_crit=False)
    # Tick through full lifetime
    for _ in range(DamagePopupLayer.LIFETIME_FRAMES + 2):
        layer.update_and_render(surface)
    assert len(layer.popups) == 0


def test_popup_drifts_upward_over_lifetime():
    layer = DamagePopupLayer()
    pygame.init()
    surface = pygame.Surface((480, 854))
    layer.spawn(x=240, y=400, dmg=5, is_crit=False)
    starting_y = layer.popups[0].y
    # Tick half lifetime
    for _ in range(DamagePopupLayer.LIFETIME_FRAMES // 2):
        layer.update_and_render(surface)
    assert layer.popups[0].y < starting_y, "popup should drift upward (y decreases)"


from pixel_battle.engine.hud import DPSCounter


def test_dps_counter_empty_is_zero():
    c = DPSCounter()
    assert c.current_dps(now_ms=10_000) == 0.0


def test_dps_counter_single_hit():
    c = DPSCounter()
    c.record_hit(10, t_ms=5_000)
    # Window is 3s. Total dmg = 10, dps = 10/3 ≈ 3.33
    assert abs(c.current_dps(now_ms=5_100) - (10.0 / 3.0)) < 0.01


def test_dps_counter_drops_old_entries():
    c = DPSCounter()
    c.record_hit(10, t_ms=0)
    c.record_hit(20, t_ms=4_000)  # 4s later
    # At t=5_000, the first hit (t=0) is 5s old, outside 3s window
    dps = c.current_dps(now_ms=5_000)
    # Only the 20-dmg hit counts → 20/3 ≈ 6.67
    assert abs(dps - (20.0 / 3.0)) < 0.01


def test_dps_counter_multiple_hits_in_window():
    c = DPSCounter()
    c.record_hit(5, t_ms=2_000)
    c.record_hit(7, t_ms=3_000)
    c.record_hit(8, t_ms=4_000)
    # At t=4_500, all three within 3s window. Sum=20, dps=20/3 ≈ 6.67
    dps = c.current_dps(now_ms=4_500)
    assert abs(dps - (20.0 / 3.0)) < 0.01


from pixel_battle.engine.character import Character
from pixel_battle.engine.hud import SkillIconBar, MPChargeRing


def test_skill_icon_bar_renders_without_error():
    pygame.init()
    pygame.font.init()
    surface = pygame.Surface((480, 854))
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    bar = SkillIconBar(c)
    bar.render(surface, x=10, y=750, now_ms=1000)
    # Smoke test: doesn't crash; bar has 2 slots (basic + cd)
    assert bar.num_slots == 2


def test_skill_icon_bar_cd_arc_progresses():
    """When skill is on cooldown, fill_ratio should be between 0 and 1."""
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    c.skill_cd_ready_at["screw_dart"] = 5000
    bar = SkillIconBar(c)
    # At now_ms=3000, 2000ms remain of 4000 cd, so fill = 2/4 = 0.5
    assert abs(bar._cd_fill_ratio("screw_dart", now_ms=3000) - 0.5) < 0.02
    # At now_ms=5000, no CD remaining
    assert bar._cd_fill_ratio("screw_dart", now_ms=5000) == 0.0


def test_mp_charge_ring_renders_when_mp_full():
    pygame.init()
    surface = pygame.Surface((480, 854))
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    c.mp = c.mp_max
    ring = MPChargeRing()
    # Smoke test
    ring.render(surface, c, char_x=120, char_y=500, t_ms=2000)
    # When mp not full, render should no-op (no error)
    c.mp = 50
    ring.render(surface, c, char_x=120, char_y=500, t_ms=2000)
