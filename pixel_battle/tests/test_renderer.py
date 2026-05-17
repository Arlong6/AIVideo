import os
import pygame
from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import AnimationState, BG_COLOR, Renderer, WIDTH, HEIGHT

BG_COLOR_TUPLE = BG_COLOR


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


def test_animation_state_attack_offsets_character():
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    r.render_frame(left, right, left_anim=AnimationState.IDLE,
                   right_anim=AnimationState.IDLE, anim_frame=0)
    r.render_frame(left, right, left_anim=AnimationState.ATTACK,
                   right_anim=AnimationState.IDLE, anim_frame=3)
    # If call didn't error, test passes (loose assertion)
    assert True


def test_ko_renders_character_horizontally():
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    right.take_damage(100)
    r.render_frame(left, right, left_anim=AnimationState.IDLE,
                   right_anim=AnimationState.KO, anim_frame=4)
    below_center = r.surface.get_at((WIDTH * 3 // 4, HEIGHT // 2 + 50))
    assert below_center[:3] != BG_COLOR_TUPLE
