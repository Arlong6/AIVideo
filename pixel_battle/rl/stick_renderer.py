"""Procedural stick figure draw — replaces sprite blits in RL pipeline.

Pose driven by Character.action_state, attack_phase, vel_x, on_ground.
"""
from __future__ import annotations
from typing import Tuple

import pygame

from pixel_battle.engine.character import Character


HEAD_RADIUS = 12
TORSO_LENGTH = 40
ARM_LENGTH = 22
LEG_LENGTH = 28
LINE_WIDTH = 3


def _arm_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_arm_dx, dy), (right_arm_dx, dy)) for the two arms.

    Pose interpretation:
      - attack_phase=='windup' → both arms pulled back
      - attack_phase=='strike' → front arm thrust forward (in facing direction)
      - default               → arms hang slightly out from body
    """
    facing = char.facing  # +1 right, -1 left
    if char.attack_phase == "windup":
        # Both arms pulled to back side
        back_dx = -facing * ARM_LENGTH
        return (back_dx, 6), (back_dx, 6)
    if char.attack_phase == "strike":
        # Front arm thrust forward, back arm pulled back for balance
        front_dx = facing * ARM_LENGTH
        back_dx = -facing * (ARM_LENGTH // 2)
        return (front_dx, -4), (back_dx, 8)
    if char.action_state == "hit_stagger":
        # Arms flailing up
        return (-ARM_LENGTH // 2, -ARM_LENGTH // 2), (ARM_LENGTH // 2, -ARM_LENGTH // 2)
    # Default: hanging out slightly to each side
    return (-ARM_LENGTH // 2, 10), (ARM_LENGTH // 2, 10)


def _leg_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_leg_dx, dy), (right_leg_dx, dy))."""
    if not char.on_ground:
        # Tucked in mid-air
        return (-8, LEG_LENGTH // 2), (8, LEG_LENGTH // 2)
    if abs(char.vel_x) > 0.5:
        # Splayed for walking
        return (-LEG_LENGTH // 2, LEG_LENGTH), (LEG_LENGTH // 2, LEG_LENGTH)
    # Standing
    return (-6, LEG_LENGTH), (6, LEG_LENGTH)


def draw_stick_figure(surf: pygame.Surface, char: Character,
                       color: Tuple[int, int, int]) -> None:
    """Draw a stick figure for `char` onto `surf` in `color`.

    Body anchor is char.pos_x, char.pos_y (feet position).
    Stick extends upward: hips → torso → shoulders → head.
    """
    cx = int(char.pos_x)
    cy = int(char.pos_y)

    hip_y = cy - LEG_LENGTH                      # waist
    shoulder_y = hip_y - TORSO_LENGTH            # neck
    head_center_y = shoulder_y - HEAD_RADIUS - 2 # head sits just above shoulders

    # Head
    pygame.draw.circle(surf, color, (cx, head_center_y), HEAD_RADIUS, LINE_WIDTH)
    # Eyes — two filled dots that look in facing direction
    eye_offset = 4 if char.facing >= 0 else -4
    pygame.draw.circle(surf, color, (cx + eye_offset - 3, head_center_y - 2), 1)
    pygame.draw.circle(surf, color, (cx + eye_offset + 3, head_center_y - 2), 1)

    # Torso
    pygame.draw.line(surf, color, (cx, shoulder_y), (cx, hip_y), LINE_WIDTH)

    # Arms (from shoulder)
    (lax, lay), (rax, ray) = _arm_offsets(char)
    pygame.draw.line(surf, color, (cx, shoulder_y),
                      (cx + lax, shoulder_y + lay), LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, shoulder_y),
                      (cx + rax, shoulder_y + ray), LINE_WIDTH)

    # Legs (from hip)
    (llx, lly), (rlx, rly) = _leg_offsets(char)
    pygame.draw.line(surf, color, (cx, hip_y),
                      (cx + llx, hip_y + lly), LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, hip_y),
                      (cx + rlx, hip_y + rly), LINE_WIDTH)
