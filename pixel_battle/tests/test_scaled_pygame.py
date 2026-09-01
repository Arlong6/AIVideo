"""scaled_pygame shim — coordinate/size scaling at the drawing boundary."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def _fresh(scale):
    """Import the shim and set its scale."""
    from pixel_battle.rl import scaled_pygame as sp
    sp.set_scale(scale)
    return sp


def test_scale_defaults_to_2_25():
    from pixel_battle.rl import scaled_pygame as sp
    sp.set_scale(2.25)
    assert sp.S == 2.25


def test_unknown_attributes_forward_to_real_pygame():
    import pygame
    sp = _fresh(2.25)
    assert sp.SRCALPHA == pygame.SRCALPHA
    assert sp.BLEND_RGB_ADD == pygame.BLEND_RGB_ADD


def test_length_scaling_never_vanishes():
    sp = _fresh(2.25)
    assert sp._len(1) == 2          # round(2.25) == 2
    assert sp._len(0.1) >= 1        # a hairline must stay visible
    assert sp._len(0) == 0          # 0 means "filled" in pygame — preserve it


def test_draw_line_scales_endpoints():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.draw.line(surf, (255, 0, 0), (5, 5), (5, 20), 1)
    # at S=2.0 the line runs from (10,10) to (10,40)
    assert surf.get_at((10, 12))[:3] == (255, 0, 0)
    assert surf.get_at((5, 6))[:3] != (255, 0, 0)


def test_scale_one_is_identity():
    import pygame
    sp = _fresh(1.0)
    a = pygame.Surface((60, 60))
    b = pygame.Surface((60, 60))
    sp.draw.line(a, (0, 255, 0), (3, 4), (40, 44), 3)
    pygame.draw.line(b, (0, 255, 0), (3, 4), (40, 44), 3)
    assert pygame.image.tostring(a, "RGB") == pygame.image.tostring(b, "RGB")


def test_draw_circle_scales_center_and_radius():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.draw.circle(surf, (0, 0, 255), (10, 10), 4)
    # centre moves to (20,20); radius becomes 8
    assert surf.get_at((20, 20))[:3] == (0, 0, 255)
    assert surf.get_at((20, 26))[:3] == (0, 0, 255)   # inside r=8
    assert surf.get_at((20, 32))[:3] != (0, 0, 255)   # outside


def test_draw_circle_preserves_filled_width_zero():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.draw.circle(surf, (255, 255, 0), (25, 25), 10, 0)
    assert surf.get_at((50, 50))[:3] == (255, 255, 0)  # filled, not a ring


def test_draw_rect_scales_rect():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.draw.rect(surf, (255, 0, 255), pygame.Rect(5, 5, 10, 10))
    assert surf.get_at((12, 12))[:3] == (255, 0, 255)   # inside 10,10..30,30
    assert surf.get_at((8, 8))[:3] != (255, 0, 255)


def test_draw_polygon_scales_points():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.draw.polygon(surf, (0, 255, 255), [(5, 5), (20, 5), (20, 20)])
    assert surf.get_at((30, 20))[:3] == (0, 255, 255)


def test_gfxdraw_scales():
    import pygame
    sp = _fresh(2.0)
    surf = pygame.Surface((100, 100))
    sp.gfxdraw.filled_circle(surf, 10, 10, 4, (255, 128, 0))
    assert surf.get_at((20, 20))[:3] == (255, 128, 0)


def test_draw_api_identity_at_scale_one():
    import pygame
    sp = _fresh(1.0)
    a, b = pygame.Surface((80, 80)), pygame.Surface((80, 80))
    for s, mod in ((a, sp.draw), (b, pygame.draw)):
        mod.circle(s, (10, 20, 30), (40, 40), 12, 2)
        mod.rect(s, (40, 50, 60), pygame.Rect(4, 4, 20, 10))
        mod.polygon(s, (70, 80, 90), [(1, 1), (30, 2), (20, 25)])
        mod.ellipse(s, (99, 10, 10), pygame.Rect(30, 40, 20, 12))
    assert pygame.image.tostring(a, "RGB") == pygame.image.tostring(b, "RGB")
