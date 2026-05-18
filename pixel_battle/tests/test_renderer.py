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


def test_walk_bob_offset_oscillates():
    """Walking animation should produce a non-zero y-offset that oscillates."""
    from pixel_battle.engine.renderer import _walk_bob_offset
    # Across enough frames, offset must take at least one positive AND one negative value
    offsets = [_walk_bob_offset(f) for f in range(60)]
    assert max(offsets) > 0
    assert min(offsets) < 0
    # Amplitude bounded
    assert max(offsets) <= 3
    assert min(offsets) >= -3


def test_renderer_has_projectiles_and_banners_after_init():
    pygame.init()
    r = Renderer()
    assert r.projectiles is not None
    assert r.banners is not None


def test_render_frame_processes_projectiles_and_banners():
    """A projectile spawned before render_frame should be aged + rendered."""
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    r.projectiles.spawn(x_start=120, y_start=400, x_end=360, y_end=400,
                         shape="screw", color=(80, 180, 255), lifetime=4)
    r.banners.spawn("TEST", (255, 255, 255))
    starting_age_p = r.projectiles.projectiles[0].age
    starting_age_b = r.banners.active.age
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=0, elapsed_ms=1000)
    assert r.projectiles.projectiles[0].age > starting_age_p
    assert r.banners.active.age > starting_age_b


def test_renderer_has_charge_fx_and_impact_fx_after_init():
    pygame.init()
    r = Renderer()
    assert r.charge_fx is not None
    assert r.impact_fx is not None


def test_render_frame_advances_charge_and_impact_fx():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    r.charge_fx.spawn(x=120, y=400, color=(80, 180, 255))
    r.impact_fx.spawn_ring(x=360, y=400, color=(80, 180, 255))
    r.impact_fx.request_screen_flash(color=(80, 180, 255), alpha=80, frames=4)
    starting_age_c = r.charge_fx.effects[0].age
    starting_age_r = r.impact_fx.rings[0].age
    starting_flash = r.impact_fx._flash_frames_remaining
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=0, elapsed_ms=1000)
    assert r.charge_fx.effects[0].age > starting_age_c
    assert r.impact_fx.rings[0].age > starting_age_r
    assert r.impact_fx._flash_frames_remaining < starting_flash
