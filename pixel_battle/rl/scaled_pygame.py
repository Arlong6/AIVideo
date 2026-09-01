"""Drop-in pygame replacement that scales drawing to a larger canvas.

WHY THIS EXISTS
    The fight simulates in a 480x854 coordinate system. Rendering natively at
    1080x1920 used to mean multiplying every spatial constant in the engine —
    and missing one would silently change fight outcomes. Instead, physics is
    left completely alone and only the DRAWING boundary is scaled.

HOW TO USE IT
    In a render module, replace the pygame import:

        from pixel_battle.rl import scaled_pygame as pygame

    Call sites stay untouched. This IS an implicit substitution: if you are
    debugging a render module and `pygame` behaves oddly, check its import.

WHAT IS NOT SCALED
    Physics and game logic never import this module. See the plan/spec at
    docs/superpowers/specs/2026-08-24-pixel-battle-native-hires-design.md

THE CONTRACT
    Every surface handed to a shimmed draw function must itself come from
    this shim (built at the same S) — a draw call and its target surface
    must agree on scale. A caller that draws onto a surface built with real,
    unscaled pygame (e.g. a one-off script's `pygame.Surface((480, 854))`)
    must pin `set_scale(1.0)` before drawing, or its coordinates land at the
    wrong pixels (or off-surface entirely).
"""
from __future__ import annotations

import pygame as _pg

try:
    import pygame.gfxdraw  # noqa: F401  (registers _pg.gfxdraw)
    _HAS_REAL_GFXDRAW = True
except ImportError:
    _HAS_REAL_GFXDRAW = False

# The simulation's coordinate system, and the canvas it maps onto.
CANVAS = (480, 854)
CANVAS_SCALED = (1080, 1920)

S: float = 2.25


def set_scale(s: float) -> None:
    """Set the global draw scale. 1.0 reproduces pre-hi-res output exactly."""
    global S, CANVAS_SCALED
    S = float(s)
    if S == 2.25:
        CANVAS_SCALED = (1080, 1920)
    else:
        CANVAS_SCALED = (max(1, round(CANVAS[0] * S)),
                         max(1, round(CANVAS[1] * S)))


def _pt(p):
    """Scale a point. Accepts any (x, y) sequence."""
    return (p[0] * S, p[1] * S)


def _pts(seq):
    """Scale a sequence of points."""
    return [_pt(p) for p in seq]


def _len(v):
    """Scale a length (line width, radius).

    pygame treats width=0 as "filled", so 0 must survive untouched. Any
    positive length floors at 1 so hairlines never round away to nothing.
    """
    if v is None:
        return None
    if v <= 0:
        return v
    return max(1, round(v * S))


def _rect(r):
    """Scale a rect-like (pygame.Rect or a 4-tuple) into a scaled Rect."""
    x, y, w, h = r
    return _pg.Rect(round(x * S), round(y * S),
                    max(1, round(w * S)), max(1, round(h * S)))


class ScaledSurface(_pg.Surface):
    """A Surface whose blit/fill/subsurface arguments live in fight coords.

    Sizes are already scaled at construction (see the Surface factory), so
    these overrides only translate the *arguments* callers pass in.
    """

    def blit(self, source, dest, area=None, special_flags=0):
        if dest is not None:
            if isinstance(dest, _pg.Rect):
                dest = _rect(dest)
            else:
                dest = _pt(dest)
        if area is not None:
            area = _rect(area)
        return super().blit(source, dest, area, special_flags)

    def fill(self, color, rect=None, special_flags=0):
        # No rect means "the whole surface" — already scaled, leave it alone.
        if rect is not None:
            rect = _rect(rect)
        return super().fill(color, rect, special_flags)

    def subsurface(self, *args):
        rect = args[0] if len(args) == 1 else args
        # `_rect` scales x/y/w/h independently, so a fight-coord rect that
        # spans the full CANVAS height (e.g. (0, 0, 480, 854)) scales to
        # height 1922 (round(854*2.25)), 2px taller than this surface's
        # actual height (1920 — see `_scaled_wh`'s CANVAS special case: the
        # 1.5px overflow deliberately falls off the bottom). blit/fill/draw
        # clip out-of-bounds rects silently, but Surface.subsurface() raises;
        # clip() makes the documented "falls off the bottom" behaviour real
        # for this one strict call site instead of crashing.
        return super().subsurface(_rect(rect).clip(self.get_rect()))


def _scaled_wh(size):
    """Scale a (w, h) target size the same way everywhere.

    The fight canvas (480x854) maps to exactly CANVAS_SCALED (1080x1920)
    rather than the 1921.5 (-> banker's-rounds to 1922) that the generic
    w*S/h*S formula gives; the 1.5px overflow falls off the bottom, where
    nothing is drawn (GROUND_Y scales to 1575). Every call site that scales
    a WIDTH x HEIGHT target — Surface() and the transform.*scale helpers —
    must share this so a full-canvas surface and a full-canvas rescale
    always agree on size (mismatched sizes make pygame raise on
    dest_surface writes).
    """
    w, h = size
    if (round(w), round(h)) == CANVAS:
        return CANVAS_SCALED
    return (max(1, round(w * S)), max(1, round(h * S)))


def Surface(size, flags=0, *args, **kwargs):
    """Create a scaled surface. See `_scaled_wh` for the CANVAS special case."""
    sw, sh = _scaled_wh(size)
    return ScaledSurface((sw, sh), flags, *args, **kwargs)


def Rect(*args):
    """Create a scaled Rect from fight coordinates."""
    if len(args) == 1:
        return _rect(args[0])
    if len(args) == 2:      # (pos, size)
        (x, y), (w, h) = args
        return _rect((x, y, w, h))
    return _rect(args)


class _Font:
    """Font factory with scaled point sizes."""

    @staticmethod
    def SysFont(name, size, bold=False, italic=False):
        return _pg.font.SysFont(name, max(1, round(size * S)), bold, italic)

    @staticmethod
    def Font(name, size):
        return _pg.font.Font(name, max(1, round(size * S)))

    @staticmethod
    def init():
        return _pg.font.init()

    @staticmethod
    def get_init():
        return _pg.font.get_init()

    @staticmethod
    def get_default_font():
        return _pg.font.get_default_font()


font = _Font()


class _Transform:
    """Transforms. Target SIZES are in fight coords; angles are not."""

    @staticmethod
    def smoothscale(surface, size, dest_surface=None):
        sz = _scaled_wh(size)
        if dest_surface is not None:
            return _pg.transform.smoothscale(surface, sz, dest_surface)
        return _pg.transform.smoothscale(surface, sz)

    @staticmethod
    def scale(surface, size, dest_surface=None):
        sz = _scaled_wh(size)
        if dest_surface is not None:
            return _pg.transform.scale(surface, sz, dest_surface)
        return _pg.transform.scale(surface, sz)

    @staticmethod
    def rotate(surface, angle):
        return _pg.transform.rotate(surface, angle)

    @staticmethod
    def flip(surface, flip_x, flip_y):
        return _pg.transform.flip(surface, flip_x, flip_y)

    @staticmethod
    def rotozoom(surface, angle, scale):
        return _pg.transform.rotozoom(surface, angle, scale)


transform = _Transform()


class _Draw:
    """Scaled counterparts of the pygame.draw functions we use."""

    @staticmethod
    def line(surface, color, start_pos, end_pos, width=1):
        return _pg.draw.line(surface, color, _pt(start_pos), _pt(end_pos),
                             _len(width))

    @staticmethod
    def lines(surface, color, closed, points, width=1):
        return _pg.draw.lines(surface, color, closed, _pts(points),
                              _len(width))

    @staticmethod
    def circle(surface, color, center, radius, width=0, **kwargs):
        return _pg.draw.circle(surface, color, _pt(center), _len(radius),
                               _len(width), **kwargs)

    @staticmethod
    def polygon(surface, color, points, width=0):
        return _pg.draw.polygon(surface, color, _pts(points), _len(width))

    @staticmethod
    def rect(surface, color, rect, width=0, **kwargs):
        return _pg.draw.rect(surface, color, _rect(rect), _len(width),
                             **kwargs)

    @staticmethod
    def ellipse(surface, color, rect, width=0):
        return _pg.draw.ellipse(surface, color, _rect(rect), _len(width))

    @staticmethod
    def arc(surface, color, rect, start_angle, stop_angle, width=1):
        return _pg.draw.arc(surface, color, _rect(rect), start_angle,
                            stop_angle, _len(width))

    @staticmethod
    def aaline(surface, color, start_pos, end_pos, blend=1):
        return _pg.draw.aaline(surface, color, _pt(start_pos), _pt(end_pos),
                               blend)


draw = _Draw()


class _GfxDraw:
    """Scaled gfxdraw. Takes ints for x/y/r rather than point tuples."""

    @staticmethod
    def aacircle(surface, x, y, r, color):
        return _pg.gfxdraw.aacircle(surface, round(x * S), round(y * S),
                                    max(1, round(r * S)), color)

    @staticmethod
    def filled_circle(surface, x, y, r, color):
        return _pg.gfxdraw.filled_circle(surface, round(x * S), round(y * S),
                                         max(1, round(r * S)), color)


if _HAS_REAL_GFXDRAW:
    gfxdraw = _GfxDraw()
# else: leave `gfxdraw` undefined so `pygame.gfxdraw` falls through to
# __getattr__ below, which forwards to real pygame and raises the same
# AttributeError a gfxdraw-less pygame build would — callers (see
# stick_renderer's try/except AttributeError) degrade to draw.circle
# instead of crashing inside _GfxDraw.


def __getattr__(name):
    """Forward anything we do not override to the real pygame."""
    return getattr(_pg, name)
