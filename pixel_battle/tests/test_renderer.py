import os
import pygame
from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import Renderer, WIDTH, HEIGHT


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()


def test_renderer_creates_surface_of_correct_size():
    r = Renderer()
    assert r.surface.get_size() == (WIDTH, HEIGHT)


def test_render_static_paints_both_characters():
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    r.render_static(left, right)
    px = r.surface.get_at((WIDTH // 4, HEIGHT // 2))
    assert px[:3] != (0, 0, 0), f"Expected non-black at left character, got {px}"


def test_render_static_shows_hp_bars():
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.take_damage(50)
    r.render_static(left, right)
    top_px = r.surface.get_at((WIDTH // 4, 30))
    assert top_px[:3] != (255, 255, 255)
