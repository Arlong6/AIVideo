import os
import pygame
from pixel_battle.video.captions import draw_caption, CaptionStyle
from pixel_battle.engine.renderer import WIDTH, HEIGHT


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    pygame.font.init()


def test_draw_caption_paints_pixels():
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    draw_caption(surf, "CRITICAL HIT!", style=CaptionStyle.CRIT, frame_in_anim=10)
    found = False
    for y in range(HEIGHT // 3, HEIGHT // 2):
        for x in range(WIDTH // 4, WIDTH * 3 // 4):
            if surf.get_at((x, y))[:3] != (0, 0, 0):
                found = True
                break
        if found:
            break
    assert found, "Expected caption pixels in upper-middle region"


def test_caption_fades_out_after_duration():
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    draw_caption(surf, "GONE", style=CaptionStyle.HIT, frame_in_anim=100)
    px = surf.get_at((WIDTH // 2, HEIGHT // 2 - 50))
    assert px[:3] == (0, 0, 0)


def test_long_caption_clamps_to_canvas_width():
    surf = pygame.Surface((WIDTH, HEIGHT))
    surf.fill((0, 0, 0))
    long_text = "INDESTRUCTIBLE THROW SUPER"  # forced overflow at size 72
    draw_caption(surf, long_text, style=CaptionStyle.ULTIMATE, frame_in_anim=20)
    # No pixels should be set outside the canvas — i.e., this just verifies no crash
    # and that the function returns normally
    # Better assertion: render onto a larger canvas and check actual width of painted region
    big = pygame.Surface((1000, HEIGHT))
    big.fill((0, 0, 0))
    draw_caption(big, long_text, style=CaptionStyle.ULTIMATE, frame_in_anim=20)
    # Find horizontal extent of non-black pixels
    arr = pygame.surfarray.pixels3d(big)
    nonblack = arr.sum(axis=2) > 0  # (W, H) — note pygame surfarray is (W, H, 3)
    del arr
    cols_with_content = nonblack.any(axis=1).nonzero()[0]
    if len(cols_with_content) > 0:
        text_width = cols_with_content[-1] - cols_with_content[0]
        # After auto-clamp, text width should be <= WIDTH (with margin)
        assert text_width <= WIDTH, f"Text width {text_width} > canvas width {WIDTH}"
