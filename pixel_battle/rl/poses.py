"""Two-segment skeleton + pose tables for the stick-figure renderer.

Angle convention (screen space, +x right, +y DOWN, degrees):
  0 = right, 90 = down, 180 = left, 270 = up.
A limb has two segments. Segment 1's angle is absolute; segment 2's angle
is a flex relative to segment 1. Poses are authored for facing = +1
(facing right); compute_figure() mirrors absolute angles (d -> 180 - d)
and flexes (f -> -f) for facing = -1.
"""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

Vec = Tuple[float, float]

# Joint flex clamps (degrees) — guard against degenerate/hyperextended limbs.
ELBOW_FLEX_MIN, ELBOW_FLEX_MAX = -165.0, 165.0
KNEE_FLEX_MIN, KNEE_FLEX_MAX = -165.0, 165.0


def _deg2vec(deg: float) -> Vec:
    r = math.radians(deg)
    return math.cos(r), math.sin(r)


def solve_limb(root: Vec, seg1_deg: float, flex_deg: float,
               len1: float, len2: float) -> Tuple[Vec, Vec]:
    """Return (joint, end) world positions for a 2-segment limb.

    root     -- proximal anchor (shoulder or hip)
    seg1_deg -- absolute angle of segment 1 (upper arm / thigh)
    flex_deg -- angle of segment 2 relative to segment 1
    """
    c1, s1 = _deg2vec(seg1_deg)
    joint = (root[0] + c1 * len1, root[1] + s1 * len1)
    c2, s2 = _deg2vec(seg1_deg + flex_deg)
    end = (joint[0] + c2 * len2, joint[1] + s2 * len2)
    return joint, end


def clamp_elbow(flex_deg: float) -> float:
    return max(ELBOW_FLEX_MIN, min(ELBOW_FLEX_MAX, flex_deg))


def clamp_knee(flex_deg: float) -> float:
    return max(KNEE_FLEX_MIN, min(KNEE_FLEX_MAX, flex_deg))


@dataclass
class FigurePose:
    """All joint angles for one figure at one instant (authored facing +1).

    Arm tuples are (shoulder_deg, elbow_flex_deg).
    Leg tuples are (hip_deg, knee_flex_deg).
    """
    torso_lean: float                 # deg; + leans toward facing
    front_arm: Tuple[float, float]
    back_arm: Tuple[float, float]
    front_leg: Tuple[float, float]
    back_leg: Tuple[float, float]
    weapon_deg: float                 # absolute weapon angle


def ease_in_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * t


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - (-2.0 * t + 2.0) ** 3 / 2.0


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_pair(a: Tuple[float, float], b: Tuple[float, float],
               t: float) -> Tuple[float, float]:
    return (_lerp(a[0], b[0], t), _lerp(a[1], b[1], t))


def lerp_pose(a: FigurePose, b: FigurePose, t: float) -> FigurePose:
    t = max(0.0, min(1.0, t))
    return FigurePose(
        torso_lean=_lerp(a.torso_lean, b.torso_lean, t),
        front_arm=_lerp_pair(a.front_arm, b.front_arm, t),
        back_arm=_lerp_pair(a.back_arm, b.back_arm, t),
        front_leg=_lerp_pair(a.front_leg, b.front_leg, t),
        back_leg=_lerp_pair(a.back_leg, b.back_leg, t),
        weapon_deg=_lerp(a.weapon_deg, b.weapon_deg, t),
    )


ARCHETYPE_IDS = frozenset(
    {"melee", "slam", "spin", "dash", "bolt", "multishot", "aura", "beam"})


def select_pose_id(char) -> str:
    """Pick the pose key for `char`'s current state.

    Attacking: `kick` if tagged so, else the skill's vfx archetype
    (unknown -> `melee`). Otherwise idle / walk / jump / hit.
    """
    if char.action_state == "attacking":
        if getattr(char, "attack_anim_hint", "") == "kick":
            return "kick"
        skill = getattr(char, "attack_used_kind", None)
        vfx = getattr(skill, "vfx", "melee") if skill is not None else "melee"
        return vfx if vfx in ARCHETYPE_IDS else "melee"
    if not char.on_ground:
        return "jump"
    if char.action_state == "hit_stagger":
        return "hit"
    if abs(char.vel_x) > 0.5:
        return "walk"
    return "idle"
