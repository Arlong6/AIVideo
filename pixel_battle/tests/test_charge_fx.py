import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.charge_fx import ChargeEffect, ChargeFXSystem


def test_charge_fx_starts_empty():
    sys = ChargeFXSystem()
    assert sys.effects == []


def test_spawn_adds_effect():
    sys = ChargeFXSystem()
    sys.spawn(x=240, y=400, color=(80, 180, 255))
    assert len(sys.effects) == 1
    eff = sys.effects[0]
    assert eff.x == 240
    assert eff.y == 400
    assert eff.age == 0
    assert eff.lifetime == 12


def test_effect_ages_and_drops_at_lifetime():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ChargeFXSystem()
    sys.spawn(x=100, y=100, color=(80, 180, 255))
    for _ in range(ChargeEffect.LIFETIME_DEFAULT + 2):
        sys.update_and_render(surface)
    assert sys.effects == []


def test_orbit_radius_shrinks_over_lifetime():
    """Sparkles converge inward over the effect's lifetime."""
    sys = ChargeFXSystem()
    sys.spawn(x=100, y=100, color=(80, 180, 255))
    eff = sys.effects[0]
    r0 = sys._current_orbit_radius(eff)
    assert r0 > 25
    eff.age = eff.lifetime - 1
    r_late = sys._current_orbit_radius(eff)
    assert r_late < r0
    assert r_late < 5


def test_on_complete_fires_once_at_lifetime():
    sys = ChargeFXSystem()
    fired = []
    sys.spawn(x=100, y=100, color=(80, 180, 255),
              on_complete=lambda: fired.append(True))
    pygame.init()
    surface = pygame.Surface((480, 854))
    for _ in range(ChargeEffect.LIFETIME_DEFAULT + 2):
        sys.update_and_render(surface)
    assert fired == [True]
