import os
import pygame
from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import Renderer
from pixel_battle.engine.cinematic import (
    play_cinematic_frame, CINEMATICS, CinematicEvent,
)


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()


def test_brick_throw_cinematic_registered():
    assert "indestructible_throw" in CINEMATICS
    spec = CINEMATICS["indestructible_throw"]
    assert spec.total_frames == 180


def test_play_cinematic_frame_runs_without_error():
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    for f in range(180):
        play_cinematic_frame(r.surface, "indestructible_throw", f, attacker=left, defender=right)


def test_cinematic_events_at_correct_frames():
    spec = CINEMATICS["indestructible_throw"]
    event_frames = [e.frame for e in spec.events]
    assert any(60 <= f <= 100 for f in event_frames)
    types = [e.type for e in spec.events]
    assert "caption" in types
