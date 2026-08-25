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
"""
from __future__ import annotations

import pygame as _pg

try:
    import pygame.gfxdraw  # noqa: F401  (registers _pg.gfxdraw)
except ImportError:
    pass

# The simulation's coordinate system, and the canvas it maps onto.
CANVAS = (480, 854)
CANVAS_SCALED = (1080, 1920)

S: float = 2.25


def set_scale(s: float) -> None:
    """Set the global draw scale. 1.0 reproduces pre-hi-res output exactly."""
    global S
    S = float(s)


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


gfxdraw = _GfxDraw()


def __getattr__(name):
    """Forward anything we do not override to the real pygame."""
    return getattr(_pg, name)
