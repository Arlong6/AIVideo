import os
import pygame


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()


def test_draw_pop_text_skips_when_alpha_zero():
    from pixel_battle.episodes.ep01_brick_vs_glass import _draw_pop_text
    surf = pygame.Surface((100, 100))
    surf.fill((0, 0, 0))
    _draw_pop_text(surf, "test", (50, 50), alpha=0)
    # Should be untouched
    assert surf.get_at((50, 50))[:3] == (0, 0, 0)


def test_draw_pop_text_renders_when_alpha_nonzero():
    from pixel_battle.episodes.ep01_brick_vs_glass import _draw_pop_text
    surf = pygame.Surface((200, 200))
    surf.fill((0, 0, 0))
    _draw_pop_text(surf, "HELLO", (100, 100), size=40, color=(255, 255, 255), alpha=255)
    # At least one pixel near center should be non-black
    found = False
    for x in range(70, 130):
        for y in range(85, 115):
            if surf.get_at((x, y))[:3] != (0, 0, 0):
                found = True
                break
        if found:
            break
    assert found


def test_draw_intro_screen_runs_at_various_frames():
    from pixel_battle.engine.character import Character
    from pixel_battle.engine.renderer import Renderer
    from pixel_battle.episodes.ep01_brick_vs_glass import _draw_intro_screen
    r = Renderer()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    for f in [0, 30, 60, 90, 120, 150, 179]:
        _draw_intro_screen(r, left, right, f)  # should not raise
