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


def _size(w, h):
    """Scale a (w, h) target size, honoring the CANVAS -> CANVAS_SCALED exact
    mapping (see Surface's docstring) so anything sized/scaled to the full
    fight canvas lands on the same pixel dimensions as a CANVAS Surface —
    not the 1921.5-rounds-to-1922 a per-component scale would give.
    """
    if (round(w), round(h)) == CANVAS:
        return CANVAS_SCALED
    return (max(1, round(w * S)), max(1, round(h * S)))


_CLAMP_TOLERANCE = 3  # real px; absorbs the <=2px full-canvas rounding artifact


def _clamp_overflow(pos, size, bound):
    """Absorb only a small (<= _CLAMP_TOLERANCE) rounding overflow past
    `bound` — the artifact from x/y/w/h each being rounded independently
    (see `_rect`/`ScaledSurface.subsurface`). Anything larger is a genuinely
    out-of-bounds rect and is left untouched so pygame still raises for it,
    exactly as it would with no shim involved (this also restores identical
    behavior at S=1.0, where there is no rounding artifact to begin with).
    """
    overflow = pos + size - bound
    if 0 < overflow <= _CLAMP_TOLERANCE:
        return size - overflow
    return size


def _rect(r):
    """Scale a rect-like (pygame.Rect or a 4-tuple) into a scaled Rect.

    w/h go through `_size` (not a bare per-axis round) so a rect spanning the
    full fight canvas — e.g. a full-frame camera crop — lands on exactly
    CANVAS_SCALED, matching any Surface built from the same (w, h).
    """
    x, y, w, h = r
    sw, sh = _size(w, h)
    return _pg.Rect(round(x * S), round(y * S), sw, sh)


def _inv(v):
    """Invert `_len`-style scaling for a coordinate/size component.

    Returns an int when the division is exact (always the case at S=1.0), so
    identity at S=1.0 stays bit-for-bit and int-for-int.
    """
    q = v / S
    r = round(q)
    return r if abs(q - r) < 1e-9 else q


def fight_size(surface):
    """A Surface's size expressed in FIGHT coordinates.

    WHY THIS EXISTS
        `surface.get_size()` (and get_width/get_height/get_rect) is real
        pygame and always reports REAL pixels. That is correct for anything
        that touches the pixel buffer (surfarray, image.tostring, the frame
        recorder) — but wrong when the value is fed back into a shim call,
        because the shim will scale it a second time.

        Use `fight_size` whenever the answer is consumed as a fight-coord
        quantity: a size handed to `pygame.Surface(...)`, a blit dest, a
        draw coordinate. Use plain `get_size()` when you need real pixels.

        This is a free function rather than a ScaledSurface method on
        purpose: `pygame.font.Font.render` and every `pygame.transform.*`
        return PLAIN `pygame.Surface` objects (verified — a C type cannot be
        re-classed in place), so a method would silently not exist on
        exactly the surfaces that caused the worst placement bugs.

    The full canvas is special-cased so it inverts `_size` exactly
    (1080/2.25 == 480 but 1920/2.25 == 853.33, not 854).
    """
    w, h = surface.get_size()
    if (w, h) == CANVAS_SCALED:
        return CANVAS
    return (_inv(w), _inv(h))


def fight_width(surface):
    """`surface.get_width()` in fight coordinates. See `fight_size`."""
    return fight_size(surface)[0]


def fight_height(surface):
    """`surface.get_height()` in fight coordinates. See `fight_size`."""
    return fight_size(surface)[1]


def fight_rect(surface, **kwargs):
    """`surface.get_rect(**kwargs)` in fight coordinates. See `fight_size`.

    The keyword arguments (center=, topleft=, ...) are fight coords too, so
    the returned Rect can be passed straight to a shim blit/draw call.
    """
    w, h = fight_size(surface)
    rect = _pg.Rect(0, 0, round(w), round(h))
    for key, value in kwargs.items():
        setattr(rect, key, value)
    return rect


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
        r = _rect(rect)
        # x/y/w/h are each rounded independently, so a rect whose fight-coord
        # edge sits exactly on the canvas boundary (e.g. y + h == CANVAS[1])
        # can scale to 1-2px past this surface's real edge even though the
        # source rect was in-bounds. Absorb only that small rounding
        # artifact; anything bigger is a real out-of-bounds rect and must
        # still raise, same as plain pygame (including at S=1.0).
        sw, sh = self.get_size()
        r.width = _clamp_overflow(r.x, r.width, sw)
        r.height = _clamp_overflow(r.y, r.height, sh)
        return super().subsurface(r)


def Surface(size, flags=0, *args, **kwargs):
    """Create a scaled surface.

    The fight canvas (480x854) maps to exactly 1080x1920 rather than the
    1921.5 that 2.25x would give; the 1.5px overflow falls off the bottom,
    where nothing is drawn (GROUND_Y scales to 1575).
    """
    w, h = size
    sw, sh = _size(w, h)
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
        sz = _size(size[0], size[1])
        if dest_surface is not None:
            return _pg.transform.smoothscale(surface, sz, dest_surface)
        return _pg.transform.smoothscale(surface, sz)

    @staticmethod
    def scale(surface, size, dest_surface=None):
        sz = _size(size[0], size[1])
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


gfxdraw = _GfxDraw()


def __getattr__(name):
    """Forward anything we do not override to the real pygame."""
    return getattr(_pg, name)
