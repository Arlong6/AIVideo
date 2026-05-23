"""Procedural stick figure draw — replaces sprite blits in RL pipeline.

Pose driven by Character.action_state, attack_phase, vel_x, on_ground.
Alan Becker-style polish: filled head, hands, feet, smear trails,
impact burst + landing dust helpers.
"""
from __future__ import annotations
import math
from typing import Tuple

import pygame

from pixel_battle.engine.character import Character
from pixel_battle.rl.poses import compute_figure, cocked_weapon_deg, select_pose_id
from pixel_battle.rl.weapons import get_weapon, draw_weapon, draw_swing_smear


# ── Constants ────────────────────────────────────────────────────────────────
SMEAR_VEL_THRESHOLD = 2.5  # motion-smear ghosts kick in at walk speed (3.0)


def _swing_smear_start_angle(pose_id: str, facing: int) -> float:
    """Weapon angle at the start of the strike sweep, in `facing` space.

    `cocked_weapon_deg` is authored for facing +1; mirror it for facing -1.
    """
    cocked = cocked_weapon_deg(pose_id)
    return cocked if facing >= 0 else 180.0 - cocked

# Per-character visual style. Limb lengths are split into two segments
# (upper_arm + forearm, thigh + shin) for the jointed skeleton.
_STYLES = {
    "brick_phone": {"head_shape": "square",   "head_size": 26,
                    "torso_length": 88, "upper_arm": 30, "forearm": 30,
                    "thigh": 32, "shin": 32, "line_width": 8,
                    "hand_radius": 7, "foot_length": 22},
    "glass_slab":  {"head_shape": "triangle", "head_size": 30,
                    "torso_length": 104, "upper_arm": 31, "forearm": 31,
                    "thigh": 35, "shin": 35, "line_width": 5,
                    "hand_radius": 4, "foot_length": 14},
    "garen":       {"head_shape": "square",   "head_size": 28,
                    "torso_length": 86, "upper_arm": 32, "forearm": 31,
                    "thigh": 31, "shin": 31, "line_width": 9,
                    "hand_radius": 8, "foot_length": 22},
    "lux":         {"head_shape": "diamond",  "head_size": 30,
                    "torso_length": 108, "upper_arm": 30, "forearm": 30,
                    "thigh": 36, "shin": 36, "line_width": 5,
                    "hand_radius": 4, "foot_length": 13},
    "yasuo":       {"head_shape": "circle",   "head_size": 27,
                    "torso_length": 94, "upper_arm": 33, "forearm": 32,
                    "thigh": 33, "shin": 33, "line_width": 6,
                    "hand_radius": 5, "foot_length": 15},
    "ashe":        {"head_shape": "triangle", "head_size": 27,
                    "torso_length": 96, "upper_arm": 34, "forearm": 33,
                    "thigh": 33, "shin": 33, "line_width": 5,
                    "hand_radius": 4, "foot_length": 13},
}

_DEFAULT_STYLE = {"head_shape": "circle", "head_size": 22,
                  "torso_length": 80, "upper_arm": 28, "forearm": 28,
                  "thigh": 30, "shin": 30, "line_width": 4,
                  "hand_radius": 4, "foot_length": 12}


_FIGURE_SCALE = 0.85       # shrink every figure ~15% — characters read smaller
_SCALED_KEYS = frozenset({"head_size", "torso_length", "upper_arm", "forearm",
                          "thigh", "shin", "line_width", "hand_radius", "foot_length"})


def get_style(char_id: str) -> dict:
    base = _STYLES.get(char_id, _DEFAULT_STYLE)
    return {k: (max(1, int(v * _FIGURE_SCALE)) if k in _SCALED_KEYS else v)
            for k, v in base.items()}


# ── Jointed skeleton draw helpers ─────────────────────────────────────────────

def _draw_limb(surf, color, root, joint, end, line_width, cap_radius):
    pygame.draw.line(surf, color, root, joint, line_width)
    pygame.draw.line(surf, color, joint, end, line_width)
    pygame.draw.circle(surf, color, (int(end[0]), int(end[1])), cap_radius)


def _draw_foot(surf, color, knee, foot, line_width, foot_length):
    dx, dy = foot[0] - knee[0], foot[1] - knee[1]
    n = math.hypot(dx, dy) or 1.0
    px, py = -dy / n, dx / n
    half = foot_length / 2
    pygame.draw.line(surf, color, knee, foot, line_width)
    pygame.draw.line(surf, color,
                     (foot[0] + px * half, foot[1] + py * half),
                     (foot[0] - px * half, foot[1] - py * half), line_width)


def _draw_head(surf, color, geo, style):
    cx, cy = int(geo.head_center[0]), int(geo.head_center[1])
    hs = style["head_size"]
    shape = style["head_shape"]
    if shape == "square":
        rect = pygame.Rect(cx - hs, cy - hs, hs * 2, hs * 2)
        pygame.draw.rect(surf, color, rect)
        pygame.draw.rect(surf, (0, 0, 0), rect, 2)
    elif shape == "triangle":
        pts = [(cx, cy + hs), (cx - hs, cy - hs), (cx + hs, cy - hs)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (0, 0, 0), pts, 2)
    elif shape == "diamond":
        pts = [(cx, cy - hs), (cx + hs, cy), (cx, cy + hs), (cx - hs, cy)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (0, 0, 0), pts, 2)
    else:
        pygame.draw.circle(surf, color, (cx, cy), hs)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), hs, 2)


# ── Ghost (smear) drawing ─────────────────────────────────────────────────────

def _draw_ghost(surf, char, color, offset_x, alpha, style):
    """Faded torso + front-arm ghost for fast-movement smear."""
    w, h = surf.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)
    orig_x = char.pos_x
    char.pos_x = orig_x + offset_x
    try:
        geo = compute_figure(char, style)
    finally:
        char.pos_x = orig_x
    gc = (color[0], color[1], color[2], alpha)
    lw = style["line_width"]
    pygame.draw.line(ghost, gc, geo.hip, geo.shoulder, lw)
    pygame.draw.line(ghost, gc, geo.shoulder, geo.front_elbow, lw)
    pygame.draw.line(ghost, gc, geo.front_elbow, geo.front_hand, lw)
    surf.blit(ghost, (0, 0))


# ── Main draw function ────────────────────────────────────────────────────────

def draw_stick_figure(surf, char, color):
    """Draw a jointed stick figure for `char` onto `surf` in `color`."""
    style = get_style(char.id)
    lw = style["line_width"]

    if abs(char.vel_x) > SMEAR_VEL_THRESHOLD:
        _draw_ghost(surf, char, color, -int(char.vel_x * 8), 64, style)
        _draw_ghost(surf, char, color, -int(char.vel_x * 4), 128, style)

    geo = compute_figure(char, style)

    # Back limbs first (depth).
    _draw_limb(surf, color, geo.shoulder, geo.back_elbow, geo.back_hand,
               lw, style["hand_radius"])
    _draw_foot(surf, color, geo.back_knee, geo.back_foot, lw,
               style["foot_length"])
    pygame.draw.line(surf, color, geo.hip, geo.back_knee, lw)

    # Torso + head + front leg.
    pygame.draw.line(surf, color, geo.hip, geo.shoulder, lw)
    _draw_head(surf, color, geo, style)
    _draw_foot(surf, color, geo.front_knee, geo.front_foot, lw,
               style["foot_length"])
    pygame.draw.line(surf, color, geo.hip, geo.front_knee, lw)

    # Weapon + swing smear, then the front arm grips over it.
    weapon = get_weapon(char.id)
    if weapon is not None:
        if (char.action_state == "attacking"
                and char.attack_phase == "strike"):
            pose_id = select_pose_id(char)
            ang_from = _swing_smear_start_angle(pose_id, char.facing)
            draw_swing_smear(surf, weapon, geo.front_hand,
                             ang_from, geo.weapon_deg, lw, color)
        draw_weapon(surf, weapon, geo.front_hand, geo.weapon_deg, lw,
                    color, char.accent_color, off_hand_xy=geo.back_hand)

    _draw_limb(surf, color, geo.shoulder, geo.front_elbow, geo.front_hand,
               lw, style["hand_radius"])


# ── VFX helpers (exported) ────────────────────────────────────────────────────

def spawn_impact_burst(surf: pygame.Surface, x: int, y: int,
                        color: Tuple[int, int, int], size: int = 20) -> None:
    """Draw a radial starburst at (x, y) — rays + a bright hot core.

    Ray count and stroke width scale with `size` so big hits (crits,
    ultimates) read as genuinely heavier than light jabs.
    """
    num_rays = 8 if size < 60 else 12
    ray_w = max(2, size // 16)
    # Long rays + shorter offset rays for a denser star
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays
        ex = int(x + math.cos(angle) * size)
        ey = int(y + math.sin(angle) * size)
        pygame.draw.line(surf, color, (x, y), (ex, ey), ray_w)
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays + math.pi / num_rays
        ex = int(x + math.cos(angle) * size * 0.55)
        ey = int(y + math.sin(angle) * size * 0.55)
        pygame.draw.line(surf, color, (x, y), (ex, ey), max(1, ray_w - 1))
    # Hot core — colored disc + white-hot center
    pygame.draw.circle(surf, color, (x, y), max(4, size // 4))
    pygame.draw.circle(surf, (255, 255, 255), (x, y), max(2, size // 8))


# Per-effect indicator colours.
_EFFECT_COLORS = {
    "root":     (150, 110, 60),    # shackle brown
    "slow":     (90, 140, 235),    # cold blue
    "shield":   (235, 225, 110),   # golden
    "tenacity": (210, 120, 220),   # violet
}


def draw_effect_indicators(surf: pygame.Surface, char) -> None:
    """Draw a small dot per active status effect in a row above the head."""
    effects = getattr(char, "effects", None)
    if not effects:
        return
    cx = int(char.pos_x)
    top_y = int(char.pos_y) - 210          # above the figure
    spacing = 16
    n = len(effects)
    start_x = cx - (n - 1) * spacing // 2
    for i, effect in enumerate(effects):
        color = _EFFECT_COLORS.get(effect.kind, (220, 220, 220))
        ex = start_x + i * spacing
        pygame.draw.circle(surf, color, (ex, top_y), 6)
        pygame.draw.circle(surf, (0, 0, 0), (ex, top_y), 6, 2)


def spawn_flash_puff(surf: pygame.Surface, x: int, ground_y: int, color) -> None:
    """A quick blink mark — a bright vertical streak plus a few outward
    sparks — drawn at a Flash origin or destination."""
    x, ground_y = int(x), int(ground_y)
    top = ground_y - 150
    # Vertical light streak.
    streak = pygame.Surface((10, 150), pygame.SRCALPHA)
    pygame.draw.line(streak, (color[0], color[1], color[2], 150),
                     (5, 0), (5, 150), 4)
    surf.blit(streak, (x - 5, top))
    # Outward spark dots.
    for dx, dy in ((-14, -40), (14, -40), (-10, -90), (10, -90)):
        pygame.draw.circle(surf, color, (x + dx, ground_y + dy), 3)


def spawn_landing_dust(surf: pygame.Surface, x: int, ground_y: int,
                        color: Tuple[int, int, int], intensity: float = 1.0) -> None:
    """Draw 4 small expanding ellipses near (x, ground_y) suggesting a dust puff.

    Used by episodes when a character transitions from on_ground=False -> True.
    """
    num_puffs = 4
    base_w = int(10 * intensity)
    base_h = int(5 * intensity)
    for i in range(num_puffs):
        offset_x = int((i - num_puffs / 2 + 0.5) * 14 * intensity)
        offset_y = -int(i * 3 * intensity)
        w = max(2, base_w - i * 2)
        h = max(1, base_h - i)
        rect = pygame.Rect(x + offset_x - w, ground_y + offset_y - h, w * 2, h * 2)
        pygame.draw.ellipse(surf, color, rect, 1)


# ── Projectile layer (cooldown / ranged attacks) ──────────────────────────────

class ProjectileLayer:
    """Renders short-lived projectile particles for ranged attacks.

    Each projectile travels from start_xy to end_xy over duration_ms, rendered
    as a filled circle with a 3-segment fading tail. Stage 3 (play.py) spawns
    these on cooldown skill strike events.
    """

    def __init__(self):
        # Each item: (start_x, start_y, end_x, end_y, t0_ms, duration_ms, color)
        self._items = []

    def spawn(self, start, end, color, current_ms, duration_ms=350):
        """Add a new projectile traveling start->end over duration_ms."""
        self._items.append((
            int(start[0]), int(start[1]),
            int(end[0]), int(end[1]),
            int(current_ms), int(duration_ms),
            tuple(color),
        ))

    def draw(self, surf, current_ms):
        """Render every live projectile and cull expired ones.

        Each projectile is drawn as a 4px filled circle (with a 1px black
        outline) plus three fading tail dots trailing behind.
        """
        live = []
        for item in self._items:
            sx, sy, ex, ey, t0, dur, color = item
            t = (current_ms - t0) / dur
            if t >= 1.0:
                continue
            live.append(item)
            cx = sx + (ex - sx) * t
            cy = sy + (ey - sy) * t
            # Tail — 4 trailing segments, fatter and longer for visibility
            for offset, alpha, rad in ((0.06, 210, 8), (0.12, 150, 6),
                                       (0.18, 95, 5), (0.24, 50, 4)):
                tt = max(0.0, t - offset)
                tx = sx + (ex - sx) * tt
                ty = sy + (ey - sy) * tt
                d = rad * 2 + 2
                tail_surf = pygame.Surface((d, d), pygame.SRCALPHA)
                pygame.draw.circle(tail_surf, (*color, alpha), (d // 2, d // 2), rad)
                surf.blit(tail_surf, (int(tx) - d // 2, int(ty) - d // 2))
            # Bright core: white-hot center + colored body + dark outline
            pygame.draw.circle(surf, color, (int(cx), int(cy)), 9)
            pygame.draw.circle(surf, (255, 255, 255), (int(cx), int(cy)), 4)
            pygame.draw.circle(surf, (0, 0, 0), (int(cx), int(cy)), 9, 1)
        self._items = live
