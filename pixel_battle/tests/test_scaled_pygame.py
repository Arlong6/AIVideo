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
