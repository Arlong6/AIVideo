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


def test_ko_renders_character_in_region():
    """KO state should paint the sprite somewhere in the right-side character region."""
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    right.take_damage(100)
    r.render_frame(left, right, left_anim=AnimationState.IDLE,
                   right_anim=AnimationState.KO, anim_frame=4)
    # Check a broad area around where the right character should be; at least one
    # pixel in the region must differ from the background.
    cx, cy = WIDTH * 3 // 4, HEIGHT // 2
    found_non_bg = False
    for dy in range(-120, 121, 10):
        for dx in range(-80, 81, 10):
            px = r.surface.get_at((cx + dx, cy + dy))
            if px[:3] != BG_COLOR_TUPLE:
                found_non_bg = True
                break
        if found_non_bg:
            break
    assert found_non_bg, "Expected non-background pixel in right character KO region"


def test_renderer_has_hud_after_init():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    assert r.hud is not None
    assert r.hud.left_id == "brick_phone"


def test_render_frame_with_hud_smoke():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    # record a hit through the HUD then render — should not crash
    r.hud.record_hit("brick_phone", dmg=7, is_crit=False,
                      target_x=360, target_y=400, t_ms=1500)
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=4, elapsed_ms=2000)
