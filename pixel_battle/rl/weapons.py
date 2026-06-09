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
    # ── New 10 — each a distinct silhouette ──
    "bulwark":     Weapon("shield",     length=60,  grip="two_hand", width=2.0),
    "ironfist":    Weapon("gauntlets",  length=22,  grip="one_hand", width=1.6),
    "reaver":      Weapon("scythe",     length=124, grip="two_hand", width=1.0),
    "deadeye":     Weapon("pistols",    length=30,  grip="one_hand", width=1.3),
    "cyclone":     Weapon("bo",         length=124, grip="two_hand", width=0.9),
    "wrecker":     Weapon("flail",      length=96,  grip="two_hand", width=1.7),
    "quarrel":     Weapon("crossbow",   length=72,  grip="two_hand", width=1.1),
    "cleaver":     Weapon("axe",        length=96,  grip="two_hand", width=1.4),
    "pyre":        Weapon("fire_staff", length=108, grip="one_hand", width=0.8),
    "venom":       Weapon("kunai",      length=34,  grip="one_hand", width=0.9),
    "outlaw":      Weapon("revolver",   length=30,  grip="one_hand", width=1.4),
    "warlock":     Weapon("staff",      length=112, grip="one_hand", width=0.8),
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

    elif weapon.kind == "shield":
        # Tall slab presented broadside + a short stub sword — a defensive wall.
        perp = angle_deg + 90
        ctr = _pt(grip_xy, angle_deg, weapon.length * 0.22)
        halfw, halft = weapon.length * 0.46, w * 1.2
        s1 = _pt(_pt(ctr, perp, halfw), angle_deg, halft)
        s2 = _pt(_pt(ctr, perp, -halfw), angle_deg, halft)
        s3 = _pt(_pt(ctr, perp, -halfw), angle_deg, -halft)
        s4 = _pt(_pt(ctr, perp, halfw), angle_deg, -halft)
        pygame.draw.polygon(surf, accent, [s1, s2, s3, s4])
        pygame.draw.polygon(surf, color, [s1, s2, s3, s4], 2)
        pygame.draw.circle(surf, color, (int(ctr[0]), int(ctr[1])), max(2, int(w * 0.8)))
        sw_tip = _pt(grip_xy, angle_deg - 32, weapon.length * 0.7)
        pygame.draw.line(surf, color, (gx, gy), (int(sw_tip[0]), int(sw_tip[1])), max(2, w - 2))

    elif weapon.kind == "gauntlets":
        # Heavy knuckle blocks on both hands — no blade, just fists.
        for origin in (grip_xy, off_hand_xy or grip_xy):
            ox, oy = int(origin[0]), int(origin[1])
            pygame.draw.circle(surf, accent, (ox, oy), max(2, int(w * 1.5)))
            pygame.draw.circle(surf, color, (ox, oy), max(2, int(w * 1.5)), 2)

    elif weapon.kind == "scythe":
        # Long snath + a curved blade hooking forward off the tip.
        pygame.draw.line(surf, color, (gx, gy), tip_i, max(2, w))
        bpts = [tip]
        for i in range(1, 7):
            f = i / 6
            bpts.append(_pt(tip, angle_deg - 95 * f, weapon.length * 0.46 * (0.35 + 0.65 * f)))
        pygame.draw.lines(surf, accent, False,
                          [(int(p[0]), int(p[1])) for p in bpts], max(2, w + 1))

    elif weapon.kind == "pistols":
        # Twin short-barrel pistols, one per hand, grips angled down.
        for origin in (grip_xy, off_hand_xy or grip_xy):
            ox, oy = int(origin[0]), int(origin[1])
            bt = _pt(origin, angle_deg, weapon.length)
            pygame.draw.line(surf, color, (ox, oy), (int(bt[0]), int(bt[1])), max(2, w))
            gd = _pt(origin, angle_deg + 105, weapon.length * 0.55)
            pygame.draw.line(surf, color, (ox, oy), (int(gd[0]), int(gd[1])), max(2, w))
            pygame.draw.circle(surf, accent, (int(bt[0]), int(bt[1])), max(1, int(w * 0.6)))

    elif weapon.kind == "bo":
        # Long staff gripped at center — extends equally both ways, capped ends.
        back_end = _pt(grip_xy, angle_deg + 180, weapon.length * 0.5)
        fwd_end = _pt(grip_xy, angle_deg, weapon.length * 0.5)
        pygame.draw.line(surf, color, (int(back_end[0]), int(back_end[1])),
                         (int(fwd_end[0]), int(fwd_end[1])), max(2, w))
        for e in (back_end, fwd_end):
            pygame.draw.circle(surf, accent, (int(e[0]), int(e[1])), max(1, int(w * 0.8)))

    elif weapon.kind == "flail":
        # Short handle + segmented chain + a spiked ball at the end.
        handle_end = _pt(grip_xy, angle_deg, weapon.length * 0.42)
        pygame.draw.line(surf, color, (gx, gy), (int(handle_end[0]), int(handle_end[1])), max(2, w))
        ball = _pt(grip_xy, angle_deg, weapon.length)
        for i in range(1, 4):
            cp = _pt(handle_end, angle_deg, (weapon.length * 0.58) * (i / 4))
            pygame.draw.circle(surf, color, (int(cp[0]), int(cp[1])), max(1, int(w * 0.4)))
        bx, by = int(ball[0]), int(ball[1])
        r = max(3, int(w * 1.7))
        for a in range(0, 360, 45):
            sp = _pt(ball, a, r * 1.7)
            pygame.draw.line(surf, color, (bx, by), (int(sp[0]), int(sp[1])), 2)
        pygame.draw.circle(surf, accent, (bx, by), r)
        pygame.draw.circle(surf, color, (bx, by), r, 2)

    elif weapon.kind == "crossbow":
        # Horizontal stock + perpendicular limbs near the fore, drawn string.
        pygame.draw.line(surf, color, (gx, gy), tip_i, max(2, w))
        perp = angle_deg + 90
        fore = _pt(grip_xy, angle_deg, weapon.length * 0.72)
        l1 = _pt(fore, perp, weapon.length * 0.42)
        l2 = _pt(fore, perp, -weapon.length * 0.42)
        pygame.draw.line(surf, color, (int(l1[0]), int(l1[1])), (int(l2[0]), int(l2[1])), max(2, w - 1))
        pygame.draw.line(surf, (230, 230, 230), (int(l1[0]), int(l1[1])), (gx, gy), 1)
        pygame.draw.line(surf, (230, 230, 230), (int(l2[0]), int(l2[1])), (gx, gy), 1)

    elif weapon.kind == "axe":
        # Haft + a one-sided wedge head near the tip.
        pygame.draw.line(surf, color, (gx, gy), tip_i, max(2, w))
        perp = angle_deg + 90
        neck = _pt(grip_xy, angle_deg, weapon.length * 0.72)
        a1 = _pt(neck, angle_deg, -weapon.length * 0.08)
        a2 = _pt(neck, angle_deg, weapon.length * 0.24)
        blade = _pt(_pt(neck, perp, weapon.length * 0.36), angle_deg, weapon.length * 0.08)
        pygame.draw.polygon(surf, accent, [a1, a2, (int(blade[0]), int(blade[1]))])
        pygame.draw.polygon(surf, color, [a1, a2, (int(blade[0]), int(blade[1]))], 2)

    elif weapon.kind == "fire_staff":
        # Staff with a flame orb at the tip + a flame tongue.
        pygame.draw.line(surf, color, (gx, gy), tip_i, max(2, w))
        pygame.draw.circle(surf, (255, 140, 40), tip_i, w + 5)
        pygame.draw.circle(surf, (255, 235, 160), tip_i, w + 1)
        fl = _pt(tip, angle_deg - 90, w + 9)
        pygame.draw.polygon(surf, (255, 120, 30),
                            [_pt(tip, angle_deg - 60, w + 2),
                             _pt(tip, angle_deg - 120, w + 2),
                             (int(fl[0]), int(fl[1]))])

    elif weapon.kind == "revolver":
        # Short barrel + cylinder bulge + down grip — a heavy handcannon used to
        # shoot AND to pistol-whip up close.
        bt = _pt(grip_xy, angle_deg, weapon.length)
        pygame.draw.line(surf, color, (gx, gy), (int(bt[0]), int(bt[1])), max(3, w))
        cyl = _pt(grip_xy, angle_deg, weapon.length * 0.42)
        pygame.draw.circle(surf, accent, (int(cyl[0]), int(cyl[1])), max(2, int(w * 0.9)))
        pygame.draw.circle(surf, color, (int(cyl[0]), int(cyl[1])), max(2, int(w * 0.9)), 1)
        gd = _pt(grip_xy, angle_deg + 110, weapon.length * 0.6)
        pygame.draw.line(surf, color, (gx, gy), (int(gd[0]), int(gd[1])), max(2, w))
        pygame.draw.circle(surf, accent, (int(bt[0]), int(bt[1])), max(1, int(w * 0.5)))

    elif weapon.kind == "kunai":
        # Twin throwing knives with ring pommels, off-hand fanned.
        for origin, ang in ((grip_xy, angle_deg), (off_hand_xy or grip_xy, angle_deg + 15)):
            bt = _pt(origin, ang, weapon.length)
            perp = ang + 90
            b1 = _pt(origin, perp, w * 0.8)
            b2 = _pt(origin, perp, -w * 0.8)
            pygame.draw.polygon(surf, accent, [b1, b2, (int(bt[0]), int(bt[1]))])
            pygame.draw.polygon(surf, color, [b1, b2, (int(bt[0]), int(bt[1]))], 1)
            rp = _pt(origin, ang + 180, w * 1.6)
            pygame.draw.circle(surf, color, (int(rp[0]), int(rp[1])), max(1, int(w * 0.7)), 1)


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
