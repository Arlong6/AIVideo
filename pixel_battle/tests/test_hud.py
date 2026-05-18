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
