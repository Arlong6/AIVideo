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


# ── Constants ────────────────────────────────────────────────────────────────
HEAD_RADIUS = 16          # was 12
TORSO_LENGTH = 40
ARM_LENGTH = 22
LEG_LENGTH = 28
LINE_WIDTH = 3
HAND_RADIUS = 3           # new
FOOT_LENGTH = 8           # new
SMEAR_VEL_THRESHOLD = 3.0 # new

# Phase durations in ms (used for pose interpolation)
_WINDUP_DUR = 128
_STRIKE_DUR = 64
_RECOVER_DUR = 160


# ── Per-character visual style ────────────────────────────────────────────────
# Keys match Character.id; falls back to defaults.
_STYLES = {
    "brick_phone": {
        "head_shape": "square",
        "head_size": 18,
        "torso_length": 40,
        "arm_length": 22,
        "leg_length": 26,
        "line_width": 4,
        "hand_radius": 4,
        "foot_length": 10,
    },
    "glass_slab": {
        "head_shape": "triangle",
        "head_size": 17,
        "torso_length": 50,
        "arm_length": 24,
        "leg_length": 32,
        "line_width": 2,
        "hand_radius": 2,
        "foot_length": 7,
    },
}

_DEFAULT_STYLE = {
    "head_shape": "circle",
    "head_size": HEAD_RADIUS,
    "torso_length": TORSO_LENGTH,
    "arm_length": ARM_LENGTH,
    "leg_length": LEG_LENGTH,
    "line_width": LINE_WIDTH,
    "hand_radius": HAND_RADIUS,
    "foot_length": FOOT_LENGTH,
}


def get_style(char_id: str) -> dict:
    return _STYLES.get(char_id, _DEFAULT_STYLE)


# ── Easing functions ──────────────────────────────────────────────────────────

def _ease_in_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def _ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp2(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[int, int]:
    return (int(_lerp(a[0], b[0], t)), int(_lerp(a[1], b[1], t)))


# ── Pose helpers ──────────────────────────────────────────────────────────────

def _arm_offsets(char: Character, arm_length: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_arm_dx, dy), (right_arm_dx, dy)) with smooth interpolation."""
    facing = char.facing  # +1 right, -1 left
    phase = char.attack_phase
    phase_t = getattr(char, "attack_phase_t", 0)  # elapsed ms in current phase

    # Default arm poses (derived from arm_length so brick/glass scale correctly)
    default_l = (-arm_length // 2, 10)
    default_r = (arm_length // 2, 10)
    # Facing-adjusted target poses
    # "pulled back" = arms go to the back of body
    pulled = ((-facing * arm_length, 6), (-facing * arm_length, 6))
    # "thrust forward" = front arm fully forward, back arm half-back
    thrust_l = (facing * arm_length, -4)
    thrust_r = (-facing * (arm_length // 2), 8)

    if phase == "windup":
        t = _ease_in_cubic(phase_t / _WINDUP_DUR)
        l = _lerp2(default_l, pulled[0], t)
        r = _lerp2(default_r, pulled[1], t)
        return l, r

    if phase == "strike":
        t = _ease_out_cubic(phase_t / _STRIKE_DUR)
        l = _lerp2(pulled[0], thrust_l, t)
        r = _lerp2(pulled[1], thrust_r, t)
        return l, r

    if phase == "recover":
        t = _ease_in_out_cubic(phase_t / _RECOVER_DUR)
        # from thrust back toward default
        l = _lerp2(thrust_l, default_l, t)
        r = _lerp2(thrust_r, default_r, t)
        return l, r

    if char.action_state == "hit_stagger":
        # Arms flailing up
        return (-arm_length // 2, -arm_length // 2), (arm_length // 2, -arm_length // 2)

    # Default: hanging out slightly to each side
    return default_l, default_r


def _leg_offsets(char: Character, leg_length: int) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_leg_dx, dy), (right_leg_dx, dy))."""
    if not char.on_ground:
        return (-8, leg_length // 2), (8, leg_length // 2)
    if abs(char.vel_x) > 0.5:
        return (-leg_length // 2, leg_length), (leg_length // 2, leg_length)
    return (-6, leg_length), (6, leg_length)


# ── Ghost (smear) drawing ─────────────────────────────────────────────────────

def _draw_ghost(surf: pygame.Surface, char: Character, color: Tuple[int, int, int],
                offset_x: int, alpha: int, style: dict) -> None:
    """Draw a faded ghost torso+arms at (pos_x + offset_x) onto a SRCALPHA temp surface
    and blit it onto surf."""
    w, h = surf.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)

    gc = (color[0], color[1], color[2], alpha)
    cx = int(char.pos_x) + offset_x
    cy = int(char.pos_y)

    hip_y = cy - style["leg_length"]
    shoulder_y = hip_y - style["torso_length"]

    # Torso only
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx, hip_y), style["line_width"])
    # Arms
    (lax, lay), (rax, ray) = _arm_offsets(char, style["arm_length"])
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx + lax, shoulder_y + lay), style["line_width"])
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx + rax, shoulder_y + ray), style["line_width"])

    surf.blit(ghost, (0, 0))


# ── Main draw function ────────────────────────────────────────────────────────

def draw_stick_figure(surf: pygame.Surface, char: Character,
                       color: Tuple[int, int, int]) -> None:
    """Draw a stick figure for `char` onto `surf` in `color`.

    Body anchor is char.pos_x, char.pos_y (feet position).
    Stick extends upward: hips → torso → shoulders → head.
    """
    style = get_style(char.id)
    head_size = style["head_size"]
    torso_length = style["torso_length"]
    arm_length = style["arm_length"]
    leg_length = style["leg_length"]
    line_width = style["line_width"]
    hand_radius = style["hand_radius"]
    foot_length = style["foot_length"]
    head_shape = style["head_shape"]

    # ── Motion smears ────────────────────────────────────────────────────────
    if abs(char.vel_x) > SMEAR_VEL_THRESHOLD:
        trail1_x = -int(char.vel_x * 4)
        trail2_x = -int(char.vel_x * 8)
        _draw_ghost(surf, char, color, trail2_x, 64, style)   # 25% alpha (64/255)
        _draw_ghost(surf, char, color, trail1_x, 128, style)  # 50% alpha (128/255)

    cx = int(char.pos_x)
    cy = int(char.pos_y)

    hip_y = cy - leg_length
    shoulder_y = hip_y - torso_length
    head_center_y = shoulder_y - head_size - 2

    # ── Head: shape switch (circle / square / triangle) ──────────────────────
    if head_shape == "square":
        rect = pygame.Rect(cx - head_size, head_center_y - head_size,
                           head_size * 2, head_size * 2)
        pygame.draw.rect(surf, color, rect)
        pygame.draw.rect(surf, (0, 0, 0), rect, 2)
    elif head_shape == "triangle":
        pts = [
            (cx, head_center_y + head_size),               # bottom apex
            (cx - head_size, head_center_y - head_size),   # top-left
            (cx + head_size, head_center_y - head_size),   # top-right
        ]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (0, 0, 0), pts, 2)
    else:
        pygame.draw.circle(surf, color, (cx, head_center_y), head_size)          # filled
        pygame.draw.circle(surf, (0, 0, 0), (cx, head_center_y), head_size, 2)  # outline

    # ── Torso ─────────────────────────────────────────────────────────────────
    pygame.draw.line(surf, color, (cx, shoulder_y), (cx, hip_y), line_width)

    # ── Arms + hands ─────────────────────────────────────────────────────────
    (lax, lay), (rax, ray) = _arm_offsets(char, arm_length)
    left_hand = (cx + lax, shoulder_y + lay)
    right_hand = (cx + rax, shoulder_y + ray)
    pygame.draw.line(surf, color, (cx, shoulder_y), left_hand, line_width)
    pygame.draw.line(surf, color, (cx, shoulder_y), right_hand, line_width)
    pygame.draw.circle(surf, color, left_hand, hand_radius)
    pygame.draw.circle(surf, color, right_hand, hand_radius)

    # ── Legs + feet ──────────────────────────────────────────────────────────
    (llx, lly), (rlx, rly) = _leg_offsets(char, leg_length)
    left_foot = (cx + llx, hip_y + lly)
    right_foot = (cx + rlx, hip_y + rly)
    pygame.draw.line(surf, color, (cx, hip_y), left_foot, line_width)
    pygame.draw.line(surf, color, (cx, hip_y), right_foot, line_width)

    # Foot flicks: short horizontal perpendicular segment at foot tip
    # Compute direction of leg to find perpendicular
    for foot, (leg_dx, leg_dy) in [(left_foot, (llx, lly)), (right_foot, (rlx, rly))]:
        leg_len = math.hypot(leg_dx, leg_dy)
        if leg_len < 1:
            continue
        # Perpendicular to leg direction
        perp_x = -leg_dy / leg_len
        perp_y = leg_dx / leg_len
        half = foot_length // 2
        fx0 = int(foot[0] + perp_x * half)
        fy0 = int(foot[1] + perp_y * half)
        fx1 = int(foot[0] - perp_x * half)
        fy1 = int(foot[1] - perp_y * half)
        pygame.draw.line(surf, color, (fx0, fy0), (fx1, fy1), line_width)


# ── VFX helpers (exported) ────────────────────────────────────────────────────

def spawn_impact_burst(surf: pygame.Surface, x: int, y: int,
                        color: Tuple[int, int, int], size: int = 20) -> None:
    """Draw a radial starburst at (x, y) with 8 line segments extending `size` px.

    Used by episodes on HIT events.
    """
    num_rays = 8
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays
        ex = int(x + math.cos(angle) * size)
        ey = int(y + math.sin(angle) * size)
        pygame.draw.line(surf, color, (x, y), (ex, ey), 2)


def spawn_landing_dust(surf: pygame.Surface, x: int, ground_y: int,
                        color: Tuple[int, int, int], intensity: float = 1.0) -> None:
    """Draw 4 small expanding ellipses near (x, ground_y) suggesting a dust puff.

    Used by episodes when a character transitions from on_ground=False → True.
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
