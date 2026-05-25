"""Tests for pixel_battle.rl.ko_sequence — KO slow-mo state machine."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl.ko_sequence import KOSequence


def test_starts_inactive_returns_normal_dt():
    seq = KOSequence()
    out = seq.tick(ko_active=False, ko_loser_x=240, dt_ms=16)
    assert out.dt_scale == 1.0
    assert out.zoom == 1.0
    assert out.splash_alpha == 0


def test_impact_state_flashes_and_spawns_splash():
    seq = KOSequence()
    out = seq.tick(ko_active=True, ko_loser_x=240, dt_ms=16)
    assert out.spawn_flash, "first KO tick should request a screen flash"
    assert out.spawn_splash, "first KO tick should request K.O. text"


def test_slowmo_returns_reduced_dt_scale():
    seq = KOSequence()
    # consume impact (0-200 ms): 13 ticks × 16ms = 208ms
    for _ in range(13):
        seq.tick(ko_active=True, ko_loser_x=240, dt_ms=16)
    out = seq.tick(ko_active=True, ko_loser_x=240, dt_ms=16)
    assert out.dt_scale < 0.5, (
        f"slow-mo dt_scale should be small, got {out.dt_scale}")
    assert out.zoom > 1.0, f"camera should be zooming, got {out.zoom}"


def test_hold_state_freezes_engine():
    seq = KOSequence()
    # run through impact + slow-mo (~1.2 s total): 75 × 16ms = 1200ms
    for _ in range(75):
        seq.tick(ko_active=True, ko_loser_x=240, dt_ms=16)
    out = seq.tick(ko_active=True, ko_loser_x=240, dt_ms=16)
    assert out.dt_scale == 0.0, "hold state should fully freeze the engine"
    assert out.splash_alpha == 255, "K.O. splash should hold full opacity"
