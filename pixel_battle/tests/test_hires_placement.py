"""Native hi-res placement tests — one per shim-mounted render module.

WHY THIS FILE EXISTS
    Every other render test runs at S=1.0 (see conftest), where the shim is
    an exact identity — so a call site that mixes REAL pixel sizes (what
    `get_size()` / `get_width()` / `get_rect()` always report) with FIGHT
    coordinates is invisible. These tests force the production scale
    (S=2.25) and assert that what gets drawn still lands inside the real
    canvas, which is exactly what that mixing breaks.

    Assertions are deliberately behavioural (pixels landed here) rather than
    "this call site uses `pygame.fight_width`", so they stay honest if the
    fix strategy ever changes.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

pygame.init()
pygame.font.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl import scaled_pygame as sp


@pytest.fixture
def native():
    """Production scale for the duration of one test (overrides conftest).

    Several sibling test files in this suite call `pygame.quit()` in a
    module-scoped teardown fixture; when pytest collects/runs this whole
    directory, one of those can run between this file's tests and tear
    down the font subsystem this file initialized once at import time.
    Defensively re-init here (idempotent when already initialized) so this
    file's tests are correct in isolation AND when swept up in a full-
    directory run regardless of sibling test order.
    """
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    if not pygame.display.get_init():
        pygame.display.set_mode((1, 1))
    sp.set_scale(2.25)
    yield sp
    sp.set_scale(1.0)


def _canvas():
    surf = sp.Surface(sp.CANVAS, pygame.SRCALPHA)
    surf.fill((0, 0, 0, 255))
    return surf


def _lit_columns(surf, y0, y1, threshold=80):
    """Real-pixel x indices with any bright pixel in the real row band."""
    arr = pygame.surfarray.array3d(surf)
    band = arr[:, y0:y1]
    return np.nonzero(np.any(band > threshold, axis=(1, 2)))[0]


# ---------------------------------------------------------------- hud.py


def _battle():
    from pixel_battle.engine.character import Character
    from pixel_battle.engine.battle import Battle
    from pixel_battle.engine.rng import BattleRNG
    return Battle(Character.load("garen"), Character.load("lux"),
                  rng=BattleRNG(seed=0))


def test_hud_bars_and_names_stay_on_canvas_at_native_scale(native):
    """hud.py:71/147/148/158 — `W = surf.get_width()` fed the bar layout.

    At S=2.25 that is 1080, so the right-hand bar was laid out at fight-x
    570 and the shim pushed it to real-x 1282 — off a 1080px canvas.
    """
    from pixel_battle.rl.hud import BAR_Y, BAR_HEIGHT, BAR_WIDTH

    surf = _canvas()
    surf.fill((0, 0, 0, 255))
    from pixel_battle.rl.hud import HUD
    HUD().draw(surf, _battle(), elapsed_ms=12_500)

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED

    y0 = round(BAR_Y * sp.S)
    y1 = round((BAR_Y + BAR_HEIGHT) * sp.S)
    cols = _lit_columns(surf, y0, y1)
    assert cols.size, "no HP bar pixels drawn at all"

    centre = real_w // 2
    assert (cols < centre).any(), "left HP bar missing"
    assert (cols > centre).any(), "right HP bar missing"
    # Both bars complete: the right bar's far edge is fight-x
    # 240 + 30 + BAR_WIDTH, and it must not be clipped by the canvas edge.
    right_edge = round((sp.CANVAS[0] // 2 + 30 + BAR_WIDTH) * sp.S)
    assert cols.max() >= right_edge - 4, (
        f"right HP bar clipped: rightmost lit column {cols.max()}, "
        f"expected to reach ~{right_edge}")
    assert cols.max() < real_w, "HP bar ran past the canvas"

    # Name plates sit just above the bars and must also be on-canvas.
    name_cols = _lit_columns(surf, round(4 * sp.S), y0 - 2)
    assert name_cols.size, "no name plate pixels"
    assert (name_cols > centre).any(), "right name plate pushed off canvas"

    # Timer sits under the MP bar, centred.
    from pixel_battle.rl.hud import MP_BAR_GAP, MP_BAR_HEIGHT
    ty = round((BAR_Y + BAR_HEIGHT + MP_BAR_GAP + MP_BAR_HEIGHT + 3) * sp.S)
    timer_cols = _lit_columns(surf, ty, min(real_h, ty + round(20 * sp.S)))
    assert timer_cols.size, "match timer vanished at native scale"
    assert abs(int(timer_cols.mean()) - centre) < round(60 * sp.S), (
        "match timer is not centred")


# ---------------------------------------------------------------- impact_fx.py


def test_blit_vfx_glow_centers_correctly_at_native_scale(native):
    """impact_fx.py:476 (was `scaled.get_rect(center=(cx, cy))`).

    `scaled` is a REAL Surface (transform.smoothscale product, already at
    real-px size); its raw `.get_rect(center=...)` mixed that real size with
    the fight-coord (cx, cy) center, and the shim then scaled the resulting
    rect a second time on blit — pushing the glow off-center exactly like
    the spin-pose bug in play.py.
    """
    from pixel_battle.rl.impact_fx import ImpactFX

    surf = _canvas()
    fx = ImpactFX()
    cx, cy = 240.0, 400.0
    assert fx._blit_vfx(surf, "light_burst", cx=cx, cy=cy, w=80, h=80)

    arr = pygame.surfarray.array3d(surf)
    mask = np.any(arr > 40, axis=2)
    xs_idx, ys_idx = np.nonzero(mask)
    assert xs_idx.size, "no glow pixels drawn"
    centroid_x = xs_idx.mean()
    centroid_y = ys_idx.mean()
    expect_x, expect_y = cx * sp.S, cy * sp.S
    assert abs(centroid_x - expect_x) < 15 * sp.S, (
        f"glow x centroid {centroid_x:.1f}, expected ~{expect_x:.1f}")
    assert abs(centroid_y - expect_y) < 15 * sp.S, (
        f"glow y centroid {centroid_y:.1f}, expected ~{expect_y:.1f}")


def test_skill_banner_stays_centered_at_native_scale(native):
    """impact_fx.py:~1127-1128 — banner rx/ry mixed a font.render() REAL-px
    glyph width/height with fight-coord screen_cx/screen_cy, shifting the
    banner left and oversizing it (gap list #3)."""
    from pixel_battle.rl.impact_fx import ImpactFX

    surf = _canvas()
    fx = ImpactFX()
    fx.spawn_skill_banner("BANNER", (255, 255, 255), surf_size=sp.CANVAS)
    fx.update_and_draw(surf, dt_ms=50)

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED
    mask = pygame.surfarray.array3d(surf) > 40
    cols = np.nonzero(np.any(mask, axis=(1, 2)))[0]
    assert cols.size, "no banner pixels drawn"
    centre = real_w // 2
    mid = (int(cols.min()) + int(cols.max())) / 2
    assert abs(mid - centre) < 0.15 * real_w, (
        f"banner not centered: mid={mid}, centre={centre}")


def test_floating_text_lands_at_native_scale(native):
    """impact_fx.py:~1415-1416 — floating text blit mixed a font.render()
    REAL-px glyph size with fight-coord (t.x, t.y)."""
    from pixel_battle.rl.impact_fx import ImpactFX

    surf = _canvas()
    fx = ImpactFX()
    fx.spawn_floating_text(x=240, y=400, text="12345", color=(255, 255, 0),
                            font_size=60)
    fx.update_and_draw(surf, dt_ms=10)

    mask = pygame.surfarray.array3d(surf) > 40
    xs_idx, ys_idx = np.nonzero(np.any(mask, axis=2))
    assert xs_idx.size, "no floating text pixels drawn"
    centroid_x = xs_idx.mean()
    expect_x = 240 * sp.S
    assert abs(centroid_x - expect_x) < 20 * sp.S, (
        f"floating text x centroid {centroid_x:.1f}, expected ~{expect_x:.1f}")


# ---------------------------------------------------------------- play.py


def _char(char_id="garen"):
    from pixel_battle.engine.character import Character
    return Character.load(char_id)


@pytest.fixture(autouse=True)
def _clear_hud_font_cache():
    """play.py's `_HUD_FONT_CACHE` is a plain module-level dict, so a Font
    object it caches outlives this file's `native` fixture and the SDL
    context it was built under. Other test modules' module-scoped fixtures
    call `pygame.quit()`/`pygame.init()` between test files; if we leave a
    cached Font behind, a later file can get a cache HIT on a now-dangling
    handle and segfault on `.render()`. Clear before AND after so this
    file's S=2.25 fonts never leak into — or inherit staleness from —
    neighboring test files."""
    import pixel_battle.rl.play as play_mod
    play_mod._HUD_FONT_CACHE.clear()
    yield
    play_mod._HUD_FONT_CACHE.clear()


def test_draw_banner_stays_centered_at_native_scale(native):
    """play.py:~1107-1111 `_draw_banner` — text_surf.get_rect(center=...) is
    native (unshimmed) pygame, mixing the real-px glyph size with the
    fight-coord center (WIDTH // 2, 70); same bug class as impact_fx's
    `_blit_vfx`."""
    from pixel_battle.rl.play import _draw_banner, WIDTH

    surf = _canvas()
    _draw_banner(surf, "ULTIMATE!")

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED
    mask = pygame.surfarray.array3d(surf) > 60
    xs_idx, ys_idx = np.nonzero(np.any(mask, axis=2))
    assert xs_idx.size, "no banner pixels drawn"
    centroid_x = xs_idx.mean()
    expect_x = (WIDTH // 2) * sp.S
    assert abs(centroid_x - expect_x) < 20 * sp.S, (
        f"banner x centroid {centroid_x:.1f}, expected ~{expect_x:.1f}")
    assert xs_idx.max() < real_w and ys_idx.max() < real_h, (
        "banner plate ran past the canvas")


def _quiet_background(monkeypatch, play_mod):
    """Stub out background/figure drawing so only the text/plate under test
    lights up pixels — arena art and stick figures are otherwise bright
    enough to swamp the column-mask signal these tests measure."""
    noop = lambda *a, **k: None
    monkeypatch.setattr(play_mod, "_draw_back_wall", noop)
    monkeypatch.setattr(play_mod, "_draw_floor", noop)
    monkeypatch.setattr(play_mod, "_draw_shadow", noop)
    monkeypatch.setattr(play_mod, "draw_stick_figure", noop)


def test_vs_intro_names_and_vs_text_stay_on_canvas_at_native_scale(native, monkeypatch):
    """play.py:1213-1214 (names) and 1222/1226-1228 (VS plate) — font.render()
    real-px widths/heights mixed with fight-coord positions (lx_final/
    rx_final/cx/cy)."""
    import pixel_battle.rl.play as play_mod
    _quiet_background(monkeypatch, play_mod)

    surf = _canvas()
    left_char, right_char = _char("garen"), _char("lux")
    play_mod._draw_vs_intro(surf, left_char, right_char, frame=100, total=100)

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED
    arr = pygame.surfarray.array3d(surf)
    mask = np.any(arr > 60, axis=2)
    centre = real_w // 2

    # Name row (y=300..330 fight): left name centred near lx_final=150,
    # right name centred near rx_final=330 (both * S).
    name_band = mask[:, round(300 * sp.S):round(330 * sp.S)]
    name_cols = np.nonzero(np.any(name_band, axis=1))[0]
    assert name_cols.size, "no VS-intro name pixels drawn"
    left_cols = name_cols[name_cols < centre]
    right_cols = name_cols[name_cols > centre]
    assert left_cols.size, "left champion name missing/off-canvas"
    assert right_cols.size, "right champion name missing/off-canvas"
    left_mid = (int(left_cols.min()) + int(left_cols.max())) / 2
    right_mid = (int(right_cols.min()) + int(right_cols.max())) / 2
    assert abs(left_mid - 150 * sp.S) < 20 * sp.S, (
        f"left name mid {left_mid}, expected ~{150 * sp.S}")
    assert abs(right_mid - 330 * sp.S) < 20 * sp.S, (
        f"right name mid {right_mid}, expected ~{330 * sp.S}")
    assert name_cols.max() < real_w, "a name ran past the canvas"

    # "VS" plate (cx=240, cy=250 fight) should be centred at real x=540.
    vs_band = mask[:, round(230 * sp.S):round(270 * sp.S)]
    vs_cols = np.nonzero(np.any(vs_band, axis=1))[0]
    assert vs_cols.size, "no VS plate pixels drawn"
    vs_mid = (int(vs_cols.min()) + int(vs_cols.max())) / 2
    assert abs(vs_mid - centre) < 20 * sp.S, (
        f"VS plate not centered: mid={vs_mid}, centre={centre}")


def test_ko_result_text_stays_centered_at_native_scale(native, monkeypatch):
    """play.py:1258-1259 (K.O.) and 1268/1272/1275-1276 (WINNER plate) —
    font.render() real-px sizes mixed with fight-coord WIDTH//2 and fixed
    y offsets."""
    import pixel_battle.rl.play as play_mod
    _quiet_background(monkeypatch, play_mod)
    WIDTH = play_mod.WIDTH

    winner = _char("garen")
    centre_scaled = (WIDTH // 2) * sp.S

    # Phase 1: "K.O." banner. frame=15/total=100 -> t=0.15: past the 0.09
    # cutoff for the full-screen flash (which would swamp the mask) but
    # still within the t < 0.26 K.O. phase.
    surf_ko = _canvas()
    play_mod._draw_ko_result(surf_ko, winner, frame=15, total=100)
    real_w, real_h = surf_ko.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED
    ko_cols = _lit_columns(surf_ko, round(150 * sp.S), round(280 * sp.S),
                            threshold=60)
    assert ko_cols.size, "no K.O. pixels drawn"
    ko_mid = (int(ko_cols.min()) + int(ko_cols.max())) / 2
    assert abs(ko_mid - centre_scaled) < 20 * sp.S, (
        f"K.O. text not centered: mid={ko_mid}, expected ~{centre_scaled}")

    # Phase 2: WINNER + name plate (t >= 0.26)
    surf_win = _canvas()
    play_mod._draw_ko_result(surf_win, winner, frame=50, total=100)
    win_cols = _lit_columns(surf_win, round(140 * sp.S), round(220 * sp.S),
                             threshold=60)
    assert win_cols.size, "no WINNER/name plate pixels drawn"
    win_mid = (int(win_cols.min()) + int(win_cols.max())) / 2
    assert abs(win_mid - centre_scaled) < 20 * sp.S, (
        f"winner plate not centered: mid={win_mid}, expected ~{centre_scaled}")
    assert win_cols.max() < real_w, "winner plate ran past the canvas"


def test_player_hud_name_stays_on_canvas_at_native_scale(native):
    """play.py:1080 `_draw_player_hud` (right_align path) — name_surf is a
    font.render() real-px glyph surface; x/bar_w are fight coords. The
    right-aligned name's right edge should land at (WIDTH - 12) * S."""
    from pixel_battle.rl.play import _draw_hud, WIDTH

    class _Env:
        pass

    env = _Env()
    env.left = _char("garen")
    env.right = _char("lux")
    env.right.display_name = "VERYLONGNAME"

    surf = _canvas()
    _draw_hud(surf, env)

    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED
    # Right-aligned name row sits at y=0 fight (y - 16 with y=16), height ~14pt.
    name_cols = _lit_columns(surf, 0, round(14 * sp.S), threshold=60)
    assert name_cols.size, "no right-player name pixels drawn"
    expect_right_edge = (WIDTH - 12) * sp.S
    assert abs(int(name_cols.max()) - expect_right_edge) < 30, (
        f"right-aligned HUD name right edge {name_cols.max()}, "
        f"expected ~{expect_right_edge}")
    assert name_cols.max() < real_w, (
        f"right-aligned HUD name ran past canvas: max col {name_cols.max()}, "
        f"canvas width {real_w}")


# ---------------------------------------------------------------- stick_renderer.py


def test_stick_renderer_overlay_sized_correctly_at_native_scale(native, monkeypatch):
    """stick_renderer.py:304 (`draw_trail`) and its 4 siblings (393 motion
    ghosts, 783 `_draw_ghost`, 907 rim glow, 1237 bullet tracer) all built a
    per-frame overlay via `pygame.Surface(surf.get_size(), SRCALPHA)`.
    `surf.get_size()` is REAL px; feeding it back into the shim's `Surface`
    factory scales it a SECOND time (gap list #6 — `fight_size(surf)` fixes
    this). The overlay is always blitted at (0, 0), so the bug was
    invisible on screen — assert on the allocated size instead of pixels.
    """
    import types
    from pixel_battle.rl import scaled_pygame as sp_mod
    import pixel_battle.rl.stick_renderer as sr_mod

    surf = _canvas()
    real_w, real_h = surf.get_size()
    assert (real_w, real_h) == sp.CANVAS_SCALED

    sizes_seen = []
    orig_surface = sp_mod.Surface

    def _spy(size, *a, **k):
        sizes_seen.append(tuple(size))
        return orig_surface(size, *a, **k)

    monkeypatch.setattr(sp_mod, "Surface", _spy)

    rs = sr_mod.RenderState()
    rs._trail = [(100.0, 400.0), (120.0, 410.0), (140.0, 420.0)]
    char = types.SimpleNamespace(attack_used_kind=None, attack_anim_hint="jab")
    rs.draw_trail(surf, char, (200, 60, 60), weapon=None)

    assert sizes_seen, "draw_trail did not allocate an overlay surface"
    for sz in sizes_seen:
        assert sz == sp.CANVAS, (
            f"overlay allocated with size {sz}; expected fight-coord "
            f"{sp.CANVAS} (a real-px size here gets scaled a second time "
            f"by the shim's Surface factory)")

    # Sanity: the trail itself still lands at the right real-scaled spot —
    # the overlay's own size never affected visual placement (blit at 0,0),
    # only its memory footprint.
    arr = pygame.surfarray.array3d(surf)
    mask = np.any(arr > 40, axis=2)
    xs_idx, ys_idx = np.nonzero(mask)
    assert xs_idx.size, "no trail pixels drawn"
    assert abs(xs_idx.mean() - 120 * sp.S) < 40 * sp.S
    assert abs(ys_idx.mean() - 410 * sp.S) < 40 * sp.S
