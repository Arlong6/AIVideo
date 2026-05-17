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
