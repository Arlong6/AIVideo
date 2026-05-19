"""Procedural stick figure draw — replaces sprite blits in RL pipeline.

Pose driven by Character.action_state, attack_phase, vel_x, on_ground.
Alan Becker-style polish: filled head, eyebrows, hands, feet, smear trails,
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
EYEBROW_LENGTH = 8        # new
SMEAR_VEL_THRESHOLD = 3.0 # new

# Phase durations in ms (used for pose interpolation)
_WINDUP_DUR = 128
_STRIKE_DUR = 64
_RECOVER_DUR = 160

# Arm pose keyframes: (dx, dy) relative to shoulder
_ARM_DEFAULT_L = (-ARM_LENGTH // 2, 10)
_ARM_DEFAULT_R = (ARM_LENGTH // 2, 10)
_ARM_PULLED_L = (-ARM_LENGTH, 6)   # both pulled to "back" during windup
_ARM_PULLED_R = (-ARM_LENGTH, 6)
# For strike we use facing-dependent values; the "front thrust" is computed inline.


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

def _arm_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_arm_dx, dy), (right_arm_dx, dy)) with smooth interpolation."""
    facing = char.facing  # +1 right, -1 left
    phase = char.attack_phase
    phase_t = getattr(char, "attack_phase_t", 0)  # elapsed ms in current phase

    # Facing-adjusted target poses
    # "pulled back" = arms go to the back of body
    pulled = ((-facing * ARM_LENGTH, 6), (-facing * ARM_LENGTH, 6))
    # "thrust forward" = front arm fully forward, back arm half-back
    thrust_l = (facing * ARM_LENGTH, -4)
    thrust_r = (-facing * (ARM_LENGTH // 2), 8)

    if phase == "windup":
        t = _ease_in_cubic(phase_t / _WINDUP_DUR)
        l = _lerp2(_ARM_DEFAULT_L, pulled[0], t)
        r = _lerp2(_ARM_DEFAULT_R, pulled[1], t)
        return l, r

    if phase == "strike":
        t = _ease_out_cubic(phase_t / _STRIKE_DUR)
        l = _lerp2(pulled[0], thrust_l, t)
        r = _lerp2(pulled[1], thrust_r, t)
        return l, r

    if phase == "recover":
        t = _ease_in_out_cubic(phase_t / _RECOVER_DUR)
        # from thrust back toward default
        l = _lerp2(thrust_l, _ARM_DEFAULT_L, t)
        r = _lerp2(thrust_r, _ARM_DEFAULT_R, t)
        return l, r

    if char.action_state == "hit_stagger":
        # Arms flailing up
        return (-ARM_LENGTH // 2, -ARM_LENGTH // 2), (ARM_LENGTH // 2, -ARM_LENGTH // 2)

    # Default: hanging out slightly to each side
    return _ARM_DEFAULT_L, _ARM_DEFAULT_R


def _leg_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_leg_dx, dy), (right_leg_dx, dy))."""
    if not char.on_ground:
        return (-8, LEG_LENGTH // 2), (8, LEG_LENGTH // 2)
    if abs(char.vel_x) > 0.5:
        return (-LEG_LENGTH // 2, LEG_LENGTH), (LEG_LENGTH // 2, LEG_LENGTH)
    return (-6, LEG_LENGTH), (6, LEG_LENGTH)


# ── Ghost (smear) drawing ─────────────────────────────────────────────────────

def _draw_ghost(surf: pygame.Surface, char: Character, color: Tuple[int, int, int],
                offset_x: int, alpha: int) -> None:
    """Draw a faded ghost torso+arms at (pos_x + offset_x) onto a SRCALPHA temp surface
    and blit it onto surf."""
    w, h = surf.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)

    gc = (color[0], color[1], color[2], alpha)
    cx = int(char.pos_x) + offset_x
    cy = int(char.pos_y)

    hip_y = cy - LEG_LENGTH
    shoulder_y = hip_y - TORSO_LENGTH

    # Torso only
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx, hip_y), LINE_WIDTH)
    # Arms
    (lax, lay), (rax, ray) = _arm_offsets(char)
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx + lax, shoulder_y + lay), LINE_WIDTH)
    pygame.draw.line(ghost, gc, (cx, shoulder_y), (cx + rax, shoulder_y + ray), LINE_WIDTH)

    surf.blit(ghost, (0, 0))


# ── Main draw function ────────────────────────────────────────────────────────

def draw_stick_figure(surf: pygame.Surface, char: Character,
                       color: Tuple[int, int, int]) -> None:
    """Draw a stick figure for `char` onto `surf` in `color`.

    Body anchor is char.pos_x, char.pos_y (feet position).
    Stick extends upward: hips → torso → shoulders → head.
    """
    # ── Motion smears ────────────────────────────────────────────────────────
    if abs(char.vel_x) > SMEAR_VEL_THRESHOLD:
        trail1_x = -int(char.vel_x * 4)
        trail2_x = -int(char.vel_x * 8)
        _draw_ghost(surf, char, color, trail2_x, 64)   # 25% alpha (64/255)
        _draw_ghost(surf, char, color, trail1_x, 128)  # 50% alpha (128/255)

    cx = int(char.pos_x)
    cy = int(char.pos_y)

    hip_y = cy - LEG_LENGTH
    shoulder_y = hip_y - TORSO_LENGTH
    head_center_y = shoulder_y - HEAD_RADIUS - 2

    # ── Head: filled circle + outline ring ───────────────────────────────────
    pygame.draw.circle(surf, color, (cx, head_center_y), HEAD_RADIUS)          # filled
    pygame.draw.circle(surf, (0, 0, 0), (cx, head_center_y), HEAD_RADIUS, 2)  # outline

    # ── Eyes ─────────────────────────────────────────────────────────────────
    eye_offset = 4 if char.facing >= 0 else -4
    pygame.draw.circle(surf, (0, 0, 0), (cx + eye_offset - 3, head_center_y - 2), 2)
    pygame.draw.circle(surf, (0, 0, 0), (cx + eye_offset + 3, head_center_y - 2), 2)

    # ── Eyebrows ─────────────────────────────────────────────────────────────
    brow_y = head_center_y - 6
    is_angry = (char.action_state == "attacking" or
                char.attack_phase in ("windup", "strike"))
    is_dazed = (char.action_state == "hit_stagger")
    brow_color = (20, 20, 20)

    if is_angry:
        # Angry V-shape: tilted inward (\\ /)
        lbx = cx + eye_offset - 3
        rbx = cx + eye_offset + 3
        pygame.draw.line(surf, brow_color,
                         (lbx - EYEBROW_LENGTH // 2, brow_y + 3),
                         (lbx + EYEBROW_LENGTH // 2, brow_y - 3), 2)
        pygame.draw.line(surf, brow_color,
                         (rbx - EYEBROW_LENGTH // 2, brow_y - 3),
                         (rbx + EYEBROW_LENGTH // 2, brow_y + 3), 2)
    elif is_dazed:
        # Dazed: straight horizontal lines
        lbx = cx + eye_offset - 3
        rbx = cx + eye_offset + 3
        pygame.draw.line(surf, brow_color,
                         (lbx - EYEBROW_LENGTH // 2, brow_y),
                         (lbx + EYEBROW_LENGTH // 2, brow_y), 2)
        pygame.draw.line(surf, brow_color,
                         (rbx - EYEBROW_LENGTH // 2, brow_y),
                         (rbx + EYEBROW_LENGTH // 2, brow_y), 2)
    else:
        # Relaxed: short flat lines slightly above eyes
        pygame.draw.line(surf, brow_color,
                         (cx + eye_offset - 3 - EYEBROW_LENGTH // 2, brow_y),
                         (cx + eye_offset - 3 + EYEBROW_LENGTH // 2, brow_y), 2)
        pygame.draw.line(surf, brow_color,
                         (cx + eye_offset + 3 - EYEBROW_LENGTH // 2, brow_y),
                         (cx + eye_offset + 3 + EYEBROW_LENGTH // 2, brow_y), 2)

    # ── Torso ─────────────────────────────────────────────────────────────────
    pygame.draw.line(surf, color, (cx, shoulder_y), (cx, hip_y), LINE_WIDTH)

    # ── Arms + hands ─────────────────────────────────────────────────────────
    (lax, lay), (rax, ray) = _arm_offsets(char)
    left_hand = (cx + lax, shoulder_y + lay)
    right_hand = (cx + rax, shoulder_y + ray)
    pygame.draw.line(surf, color, (cx, shoulder_y), left_hand, LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, shoulder_y), right_hand, LINE_WIDTH)
    pygame.draw.circle(surf, color, left_hand, HAND_RADIUS)
    pygame.draw.circle(surf, color, right_hand, HAND_RADIUS)

    # ── Legs + feet ──────────────────────────────────────────────────────────
    (llx, lly), (rlx, rly) = _leg_offsets(char)
    left_foot = (cx + llx, hip_y + lly)
    right_foot = (cx + rlx, hip_y + rly)
    pygame.draw.line(surf, color, (cx, hip_y), left_foot, LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, hip_y), right_foot, LINE_WIDTH)

    # Foot flicks: short horizontal perpendicular segment at foot tip
    # Compute direction of leg to find perpendicular
    for foot, (leg_dx, leg_dy) in [(left_foot, (llx, lly)), (right_foot, (rlx, rly))]:
        leg_len = math.hypot(leg_dx, leg_dy)
        if leg_len < 1:
            continue
        # Perpendicular to leg direction
        perp_x = -leg_dy / leg_len
        perp_y = leg_dx / leg_len
        half = FOOT_LENGTH // 2
        fx0 = int(foot[0] + perp_x * half)
        fy0 = int(foot[1] + perp_y * half)
        fx1 = int(foot[0] - perp_x * half)
        fy1 = int(foot[1] - perp_y * half)
        pygame.draw.line(surf, color, (fx0, fy0), (fx1, fy1), LINE_WIDTH)


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
