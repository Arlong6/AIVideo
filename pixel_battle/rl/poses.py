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
