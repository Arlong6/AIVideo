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


class _Draw:
    """Scaled counterparts of the pygame.draw functions we use."""

    @staticmethod
    def line(surface, color, start_pos, end_pos, width=1):
        return _pg.draw.line(surface, color, _pt(start_pos), _pt(end_pos),
                             _len(width))


draw = _Draw()


def __getattr__(name):
    """Forward anything we do not override to the real pygame."""
    return getattr(_pg, name)
