# pixel_battle/rl/weapons.py
"""Held weapons for the renderer — registry + drawing.

Weapon appearance is renderer-side visual data, keyed by char.id, exactly
like stick_renderer._STYLES. Gameplay data stays in characters.json.
Angles use the poses.py convention (degrees, 0=right, 90=down).
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Tuple
import pygame

Vec = Tuple[float, float]


@dataclass
class Weapon:
    kind: str          # greatsword|staff|katana|bow|hammer|spear|daggers|cannon
    length: float      # tip distance from the grip, px
    grip: str          # "one_hand" | "two_hand"
    width: float       # blade/shaft thickness multiplier (x line_width)


# Renderer-side registry. Each champion's silhouette is dominated by its weapon,
# so distinct kinds matter more for "who is this" than body build does.
_WEAPONS = {
    "garen":       Weapon("greatsword", length=104, grip="two_hand", width=1.7),
    "lux":         Weapon("staff",      length=110, grip="one_hand", width=0.8),
    "yasuo":       Weapon("katana",     length=92,  grip="one_hand", width=0.7),
    "ashe":        Weapon("bow",        length=84,  grip="one_hand", width=0.7),
    "mordekaiser": Weapon("hammer",     length=98,  grip="two_hand", width=2.3),
    "pantheon":    Weapon("spear",      length=134, grip="one_hand", width=0.9),
    "katarina":    Weapon("daggers",    length=44,  grip="one_hand", width=0.9),
    "jinx":        Weapon("cannon",     length=78,  grip="two_hand", width=2.2),
}


def get_weapon(char_id: str) -> Optional[Weapon]:
    return _WEAPONS.get(char_id)


def _vec(deg: float) -> Vec:
    r = math.radians(deg)
    return math.cos(r), math.sin(r)


def _pt(origin: Vec, deg: float, dist: float) -> Vec:
    c, s = _vec(deg)
    return (origin[0] + c * dist, origin[1] + s * dist)


def draw_weapon(surf: pygame.Surface, weapon: Weapon, grip_xy: Vec, angle_deg: float,
                line_width: int, color, accent,
                off_hand_xy: Optional[Vec] = None) -> None:
    """Draw `weapon` gripped at `grip_xy`, pointing along `angle_deg`."""
    gx, gy = int(grip_xy[0]), int(grip_xy[1])
    tip = _pt(grip_xy, angle_deg, weapon.length)
    tip_i = (int(tip[0]), int(tip[1]))
    w = max(2, int(line_width * weapon.width))

    if weapon.kind == "greatsword":
        # Blade as a tapered quad + crossguard + stub grip.
        guard = _pt(grip_xy, angle_deg, weapon.length * 0.18)
        perp = angle_deg + 90
        half = w
        p1 = _pt(guard, perp, half)
        p2 = _pt(guard, perp, -half)
        pygame.draw.polygon(surf, accent, [p1, p2, tip_i])
        pygame.draw.polygon(surf, color, [p1, p2, tip_i], 2)
        cg1 = _pt(guard, perp, half * 2.4)
        cg2 = _pt(guard, perp, -half * 2.4)
        pygame.draw.line(surf, color, cg1, cg2, w)
        butt = _pt(grip_xy, angle_deg + 180, weapon.length * 0.16)
        pygame.draw.line(surf, color, butt, guard, w)

    elif weapon.kind == "staff":
        pygame.draw.line(surf, color, (gx, gy), tip_i, w)
        pygame.draw.circle(surf, accent, tip_i, w + 5)
        pygame.draw.circle(surf, (255, 255, 255), tip_i, w + 1)

    elif weapon.kind == "katana":
        # Slightly curved: a 3-point polyline bowed toward the back edge.
        mid = _pt(grip_xy, angle_deg, weapon.length * 0.55)
        mid = _pt(mid, angle_deg + 90, w * 1.6)
        pygame.draw.lines(surf, color, False,
                          [(gx, gy), mid, tip_i], w)
        guard = _pt(grip_xy, angle_deg, weapon.length * 0.1)
        perp = angle_deg + 90
        pygame.draw.line(surf, color, _pt(guard, perp, w * 2),
                         _pt(guard, perp, -w * 2), max(2, w - 1))

    elif weapon.kind == "bow":
        # Bow stave as an arc of points; string from tip to tip (or off-hand).
        perp = angle_deg + 90
        n = 9
        pts = []
        for i in range(n):
            f = i / (n - 1)
            along = _pt(grip_xy, angle_deg, (f - 0.5) * weapon.length)
            bow = math.sin(f * math.pi) * weapon.length * 0.22
            pts.append(_pt(along, perp, bow))
        pygame.draw.lines(surf, color, False, pts, w)
        string_anchor = off_hand_xy if off_hand_xy is not None else \
            _pt(grip_xy, angle_deg + 90, 0)
        pygame.draw.line(surf, (235, 235, 235), pts[0], string_anchor, 1)
        pygame.draw.line(surf, (235, 235, 235), pts[-1], string_anchor, 1)

    elif weapon.kind == "hammer":
        # Long haft + a heavy blocky head near the tip — reads as a brute maul.
        neck = _pt(grip_xy, angle_deg, weapon.length * 0.74)
        pygame.draw.line(surf, color, (gx, gy), neck, max(2, w - 2))
        perp = angle_deg + 90
        hw, hl = w * 1.7, weapon.length * 0.18      # head half-width / half-length
        c1 = _pt(_pt(neck, angle_deg, -hl), perp, hw)
        c2 = _pt(_pt(neck, angle_deg, hl + weapon.length * 0.16), perp, hw)
        c3 = _pt(_pt(neck, angle_deg, hl + weapon.length * 0.16), perp, -hw)
        c4 = _pt(_pt(neck, angle_deg, -hl), perp, -hw)
        pygame.draw.polygon(surf, accent, [c1, c2, c3, c4])
        pygame.draw.polygon(surf, color, [c1, c2, c3, c4], 2)

    elif weapon.kind == "spear":
        # Long thin shaft, small leaf tip, short butt — a reaching polearm.
        butt = _pt(grip_xy, angle_deg + 180, weapon.length * 0.16)
        neck = _pt(grip_xy, angle_deg, weapon.length * 0.86)
        pygame.draw.line(surf, color, butt, neck, max(2, w))
        perp = angle_deg + 90
        t1 = _pt(neck, perp, w * 1.5)
        t2 = _pt(neck, perp, -w * 1.5)
        pygame.draw.polygon(surf, accent, [t1, t2, tip_i])
        pygame.draw.polygon(surf, color, [t1, t2, tip_i], 1)

    elif weapon.kind == "daggers":
        # Dual short blades — one per hand, the off-hand reversed for an X read.
        for origin, ang in ((grip_xy, angle_deg),
                            (off_hand_xy or grip_xy, angle_deg + 18)):
            bt = _pt(origin, ang, weapon.length)
            perp = ang + 90
            b1 = _pt(origin, perp, w)
            b2 = _pt(origin, perp, -w)
            pygame.draw.polygon(surf, accent, [b1, b2, (int(bt[0]), int(bt[1]))])
            pygame.draw.polygon(surf, color, [b1, b2, (int(bt[0]), int(bt[1]))], 1)

    elif weapon.kind == "cannon":
        # Chunky barrel block + muzzle ring — a hip-fired rocket gun.
        perp = angle_deg + 90
        bw = w * 1.4
        base = _pt(grip_xy, angle_deg + 180, weapon.length * 0.12)
        b1 = _pt(base, perp, bw); b2 = _pt(base, perp, -bw)
        m1 = _pt(tip, perp, bw * 1.25); m2 = _pt(tip, perp, -bw * 1.25)
        pygame.draw.polygon(surf, color, [b1, b2, m2, m1])
        pygame.draw.polygon(surf, accent, [b1, b2, m2, m1], 2)
        pygame.draw.circle(surf, accent, tip_i, int(bw * 1.3), 2)


def _smear_delta(angle_from: float, angle_to: float) -> float:
    """Shortest-arc signed delta in degrees, range (-180, 180]."""
    return (angle_to - angle_from + 180) % 360 - 180


def draw_swing_smear(surf: pygame.Surface, weapon: Weapon, grip_xy: Vec,
                     angle_from: float, angle_to: float,
                     line_width: int, color) -> None:
    """Draw 3 faded weapon ghosts fanned between angle_from and angle_to,
    suggesting the blade's motion blur during a strike. No-op if the
    weapon did not sweep."""
    delta = _smear_delta(angle_from, angle_to)
    if abs(delta) < 1.0:
        return
    w = max(2, int(line_width * weapon.width))
    sw, sh = surf.get_size()
    for i, alpha in ((0.25, 60), (0.5, 95), (0.75, 140)):
        deg = angle_from + delta * i
        c, s = _vec(deg)
        tip = (grip_xy[0] + c * weapon.length,
               grip_xy[1] + s * weapon.length)
        ghost = pygame.Surface((sw, sh), pygame.SRCALPHA)
        pygame.draw.line(ghost, (color[0], color[1], color[2], alpha),
                         grip_xy, tip, w)
        surf.blit(ghost, (0, 0))
