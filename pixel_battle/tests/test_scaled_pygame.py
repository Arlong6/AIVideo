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


def test_surface_size_is_scaled():
    sp = _fresh(2.0)
    s = sp.Surface((30, 40))
    assert s.get_size() == (60, 80)


def test_canvas_size_maps_to_exact_output():
    """480x854 must land on exactly 1080x1920, not round(854*2.25)=1922."""
    sp = _fresh(2.25)
    s = sp.Surface(sp.CANVAS)
    assert s.get_size() == (1080, 1920)


def test_blit_dest_is_scaled():
    import pygame
    sp = _fresh(2.0)
    dst = sp.Surface((50, 50))
    src = pygame.Surface((4, 4))
    src.fill((255, 0, 0))
    dst.blit(src, (5, 5))
    assert dst.get_at((10, 10))[:3] == (255, 0, 0)
    assert dst.get_at((5, 5))[:3] != (255, 0, 0)


def test_blit_accepts_rect_dest():
    import pygame
    sp = _fresh(2.0)
    dst = sp.Surface((50, 50))
    src = pygame.Surface((4, 4))
    src.fill((0, 255, 0))
    dst.blit(src, pygame.Rect(5, 5, 4, 4))
    assert dst.get_at((10, 10))[:3] == (0, 255, 0)


def test_fill_with_rect_is_scaled():
    sp = _fresh(2.0)
    s = sp.Surface((50, 50))
    s.fill((0, 0, 0))
    s.fill((255, 255, 255), (5, 5, 10, 2))
    assert s.get_at((12, 12))[:3] == (255, 255, 255)
    assert s.get_at((6, 6))[:3] != (255, 255, 255)


def test_fill_without_rect_still_fills_everything():
    sp = _fresh(2.0)
    s = sp.Surface((20, 20))
    s.fill((7, 8, 9))
    assert s.get_at((0, 0))[:3] == (7, 8, 9)
    assert s.get_at((39, 39))[:3] == (7, 8, 9)


def test_derived_surfaces_keep_scaling_behaviour():
    import pygame
    sp = _fresh(2.0)
    s = sp.Surface((40, 40))
    assert isinstance(s.copy(), sp.ScaledSurface)
    assert isinstance(s.subsurface((0, 0, 10, 10)), sp.ScaledSurface)


def test_surface_identity_at_scale_one():
    import pygame
    sp = _fresh(1.0)
    a = sp.Surface((40, 40), pygame.SRCALPHA)
    b = pygame.Surface((40, 40), pygame.SRCALPHA)
    src = pygame.Surface((6, 6)); src.fill((1, 2, 3))
    a.blit(src, (7, 9)); b.blit(src, (7, 9))
    a.fill((4, 5, 6), (2, 2, 5, 5)); b.fill((4, 5, 6), (2, 2, 5, 5))
    assert a.get_size() == b.get_size() == (40, 40)
    assert pygame.image.tostring(a, "RGBA") == pygame.image.tostring(b, "RGBA")


def test_rect_is_scaled():
    sp = _fresh(2.0)
    r = sp.Rect(3, 4, 10, 20)
    assert (r.x, r.y, r.w, r.h) == (6, 8, 20, 40)


def test_font_size_is_scaled():
    import pygame
    pygame.font.init()
    sp = _fresh(2.0)
    scaled = sp.font.SysFont(None, 10)      # shim turns this into a real 20pt
    plain = pygame.font.SysFont(None, 20)   # genuinely 20pt, no shim
    assert scaled.size("Ag") == plain.size("Ag")


def test_smoothscale_target_is_scaled():
    import pygame
    sp = _fresh(2.0)
    src = pygame.Surface((10, 10))
    out = sp.transform.smoothscale(src, (5, 5))
    assert out.get_size() == (10, 10)


def test_rotate_is_not_scaled():
    import pygame
    sp = _fresh(2.0)
    src = pygame.Surface((10, 20))
    out = sp.transform.rotate(src, 90)
    assert out.get_size() == pygame.transform.rotate(src, 90).get_size()


def test_rect_font_transform_identity_at_scale_one():
    import pygame
    pygame.font.init()
    sp = _fresh(1.0)
    # Rect identity
    r = sp.Rect(3, 4, 10, 20)
    expected = pygame.Rect(3, 4, 10, 20)
    assert (r.x, r.y, r.w, r.h) == (expected.x, expected.y, expected.w, expected.h)
    # Font size identity
    scaled_font = sp.font.SysFont(None, 20)
    plain_font = pygame.font.SysFont(None, 20)
    assert scaled_font.size("Ag") == plain_font.size("Ag")
    # Transform smoothscale and scale identity
    src = pygame.Surface((7, 9))
    out_smoothscale = sp.transform.smoothscale(src, (7, 9))
    out_scale = sp.transform.scale(src, (7, 9))
    assert out_smoothscale.get_size() == (7, 9)
    assert out_scale.get_size() == (7, 9)


def test_flip_and_rotozoom_are_passthrough():
    import pygame
    sp = _fresh(2.0)
    src = pygame.Surface((10, 15))
    src.fill((42, 84, 126))
    # flip passthrough: same size and bytes
    flipped_sp = sp.transform.flip(src, True, False)
    flipped_pg = pygame.transform.flip(src, True, False)
    assert flipped_sp.get_size() == flipped_pg.get_size()
    assert pygame.image.tostring(flipped_sp, "RGB") == pygame.image.tostring(flipped_pg, "RGB")
    # rotozoom passthrough: zoom factor NOT scaled, size identity
    rotozoom_sp = sp.transform.rotozoom(src, 30, 1.0)
    rotozoom_pg = pygame.transform.rotozoom(src, 30, 1.0)
    assert rotozoom_sp.get_size() == rotozoom_pg.get_size()
