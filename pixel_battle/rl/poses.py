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
from typing import Dict, Tuple

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


# Static (non-attack) poses, authored for facing = +1.
IDLE_POSE = FigurePose(
    torso_lean=0.0,
    front_arm=(88.0, -26.0), back_arm=(100.0, -32.0),
    front_leg=(96.0, 14.0), back_leg=(84.0, 14.0),
    weapon_deg=120.0)

WALK_POSE = FigurePose(
    torso_lean=8.0,
    front_arm=(60.0, -40.0), back_arm=(130.0, -40.0),
    front_leg=(120.0, 26.0), back_leg=(60.0, 30.0),
    weapon_deg=70.0)

JUMP_POSE = FigurePose(
    torso_lean=6.0,
    front_arm=(40.0, -70.0), back_arm=(150.0, -70.0),
    front_leg=(120.0, 70.0), back_leg=(70.0, 70.0),
    weapon_deg=40.0)

HIT_POSE = FigurePose(
    torso_lean=-22.0,
    front_arm=(250.0, -60.0), back_arm=(290.0, -60.0),
    front_leg=(110.0, 50.0), back_leg=(70.0, 40.0),
    weapon_deg=300.0)


@dataclass
class FigureGeometry:
    """World-space positions for every drawable point of the figure."""
    head_center: Vec
    shoulder: Vec
    hip: Vec
    front_elbow: Vec
    front_hand: Vec
    back_elbow: Vec
    back_hand: Vec
    front_knee: Vec
    front_foot: Vec
    back_knee: Vec
    back_foot: Vec
    weapon_deg: float
    facing: int


def _mirror_abs(deg: float, facing: int) -> float:
    return deg if facing >= 0 else 180.0 - deg


def _mirror_flex(flex: float, facing: int) -> float:
    return flex if facing >= 0 else -flex


def _fp(torso, fa, ba, fl, bl, wpn) -> FigurePose:
    return FigurePose(torso_lean=torso, front_arm=fa, back_arm=ba,
                      front_leg=fl, back_leg=bl, weapon_deg=wpn)


# Renderer-side phase durations (ms) used only to pace pose interpolation.
# They do NOT affect gameplay timing.
_PHASE_DUR: Dict[str, Dict[str, int]] = {
    "melee":     {"windup": 90,  "strike": 55,  "recover": 130},
    "slam":      {"windup": 240, "strike": 110, "recover": 260},
    "spin":      {"windup": 160, "strike": 200, "recover": 200},
    "dash":      {"windup": 130, "strike": 90,  "recover": 170},
    "bolt":      {"windup": 150, "strike": 70,  "recover": 160},
    "multishot": {"windup": 170, "strike": 110, "recover": 180},
    "aura":      {"windup": 200, "strike": 160, "recover": 220},
    "beam":      {"windup": 180, "strike": 260, "recover": 220},
    "kick":      {"windup": 120, "strike": 70,  "recover": 180},
}
_DEFAULT_PHASE_DUR = {"windup": 120, "strike": 70, "recover": 160}


# {archetype: {"cocked": <end of windup>, "extended": <end of strike>}}
# Authored for facing = +1. Starting values — tuned in Task 11.
ARCHETYPE_POSES: Dict[str, Dict[str, FigurePose]] = {
    "melee": {
        "cocked":   _fp(-18, (215, -95), (150, -45), (110, 20), (70, 24), 250),
        "extended": _fp(24, (8, -4), (120, -30), (70, 16), (118, 22), 12),
    },
    "slam": {
        "cocked":   _fp(-30, (255, -40), (285, -40), (104, 34), (70, 30), 280),
        "extended": _fp(30, (40, -6), (95, -10), (84, 22), (96, 24), 55),
    },
    "spin": {
        "cocked":   _fp(0, (200, -10), (340, -10), (100, 18), (80, 18), 200),
        "extended": _fp(0, (20, -8), (160, -8), (110, 20), (70, 20), 20),
    },
    "dash": {
        "cocked":   _fp(-12, (210, -85), (150, -50), (70, 70), (60, 16), 240),
        "extended": _fp(46, (6, -2), (140, -36), (135, 24), (40, 8), 368),  # weapon_deg 368 (=8 deg +360): lerp sweeps upward, not down through the below-ground zone
    },
    "bolt": {
        "cocked":   _fp(-10, (140, -70), (120, -50), (104, 16), (76, 20), 150),
        "extended": _fp(16, (4, -8), (96, -40), (96, 16), (84, 18), 4),
    },
    "multishot": {
        "cocked":   _fp(-14, (188, -60), (170, -55), (108, 20), (70, 22), 200),
        "extended": _fp(20, (340, -30), (30, -30), (74, 16), (112, 20), 330),
    },
    "aura": {
        "cocked":   _fp(-8, (300, -30), (250, -30), (96, 40), (84, 40), 300),
        "extended": _fp(2, (285, -16), (255, -16), (92, 16), (88, 16), 285),
    },
    "beam": {
        "cocked":   _fp(-26, (200, -70), (170, -60), (110, 30), (60, 24), 200),
        "extended": _fp(-16, (354, -12), (6, -12), (118, 28), (52, 20), 0),
    },
    "kick": {
        "cocked":   _fp(-14, (250, -50), (290, -50), (40, 110), (88, 16), 300),
        "extended": _fp(20, (240, -40), (300, -40), (8, 6), (92, 14), 300),
    },
}


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
    # airborne hit_stagger reads as jump (limbs tuck up)
    if not char.on_ground:
        return "jump"
    if char.action_state == "hit_stagger":
        return "hit"
    if abs(char.vel_x) > 0.5:
        return "walk"
    return "idle"


def _phase_dur(pose_id: str, phase: str) -> int:
    return _PHASE_DUR.get(pose_id, _DEFAULT_PHASE_DUR).get(
        phase, _DEFAULT_PHASE_DUR[phase])


def _resolve_attack_pose(pose_id: str, char) -> FigurePose:
    table = ARCHETYPE_POSES.get(pose_id, ARCHETYPE_POSES["melee"])
    cocked, extended = table["cocked"], table["extended"]
    phase = getattr(char, "attack_phase", "none")
    phase_t = getattr(char, "attack_phase_t", 0)
    if phase == "windup":
        t = ease_in_cubic(phase_t / _phase_dur(pose_id, "windup"))
        return lerp_pose(IDLE_POSE, cocked, t)
    if phase == "strike":
        t = ease_out_cubic(phase_t / _phase_dur(pose_id, "strike"))
        return lerp_pose(cocked, extended, t)
    if phase == "recover":
        t = ease_in_out_cubic(phase_t / _phase_dur(pose_id, "recover"))
        return lerp_pose(extended, IDLE_POSE, t)
    # unknown / no phase: hold the cocked pose
    return cocked


# Used by stick_renderer's swing-arc smear (plan Task 8).
def cocked_weapon_deg(pose_id: str) -> float:
    """Weapon angle at the start of the strike sweep (facing +1)."""
    table = ARCHETYPE_POSES.get(pose_id, ARCHETYPE_POSES["melee"])
    return table["cocked"].weapon_deg


def resolve_pose(char) -> FigurePose:
    """Return the interpolated FigurePose for `char`'s current state."""
    pose_id = select_pose_id(char)
    if pose_id in ARCHETYPE_IDS:
        return _resolve_attack_pose(pose_id, char)
    if pose_id == "kick":
        return _resolve_attack_pose("kick", char)
    if pose_id == "walk":
        return WALK_POSE
    if pose_id == "jump":
        return JUMP_POSE
    if pose_id == "hit":
        return HIT_POSE
    return IDLE_POSE


def compute_figure(char, style: dict) -> FigureGeometry:
    """Resolve `char`'s pose, run FK, and position the figure with the
    lower foot planted at `char.pos_y`."""
    pose = resolve_pose(char)
    facing = 1 if char.facing >= 0 else -1
    cx, cy = float(char.pos_x), float(char.pos_y)

    thigh, shin = style["thigh"], style["shin"]
    upper, fore = style["upper_arm"], style["forearm"]
    torso_len = style["torso_length"]

    # 1. Solve both legs from a temporary hip at the origin.
    fh_deg = _mirror_abs(pose.front_leg[0], facing)
    fk_flex = _mirror_flex(clamp_knee(pose.front_leg[1]), facing)
    bh_deg = _mirror_abs(pose.back_leg[0], facing)
    bk_flex = _mirror_flex(clamp_knee(pose.back_leg[1]), facing)
    f_knee0, f_foot0 = solve_limb((0.0, 0.0), fh_deg, fk_flex, thigh, shin)
    b_knee0, b_foot0 = solve_limb((0.0, 0.0), bh_deg, bk_flex, thigh, shin)

    # 2. Place the hip so the LOWER foot (largest y) sits at cy.
    lowest = max(f_foot0[1], b_foot0[1])
    hip = (cx, cy - lowest)

    def _shift(p):
        return (p[0] + hip[0], p[1] + hip[1])

    front_knee, front_foot = _shift(f_knee0), _shift(f_foot0)
    back_knee, back_foot = _shift(b_knee0), _shift(b_foot0)

    # 3. Torso up from hip (270 deg = straight up; + lean toward facing).
    torso_deg = _mirror_abs(270.0 + pose.torso_lean, facing)
    tc, ts = _deg2vec(torso_deg)
    shoulder = (hip[0] + tc * torso_len, hip[1] + ts * torso_len)
    head_gap = style["head_size"] + 6
    head_center = (shoulder[0] + tc * head_gap, shoulder[1] + ts * head_gap)

    # 4. Arms from the shoulder.
    fa_deg = _mirror_abs(pose.front_arm[0], facing)
    fa_flex = _mirror_flex(clamp_elbow(pose.front_arm[1]), facing)
    ba_deg = _mirror_abs(pose.back_arm[0], facing)
    ba_flex = _mirror_flex(clamp_elbow(pose.back_arm[1]), facing)
    front_elbow, front_hand = solve_limb(shoulder, fa_deg, fa_flex, upper, fore)
    back_elbow, back_hand = solve_limb(shoulder, ba_deg, ba_flex, upper, fore)

    return FigureGeometry(
        head_center=head_center, shoulder=shoulder, hip=hip,
        front_elbow=front_elbow, front_hand=front_hand,
        back_elbow=back_elbow, back_hand=back_hand,
        front_knee=front_knee, front_foot=front_foot,
        back_knee=back_knee, back_foot=back_foot,
        weapon_deg=_mirror_abs(pose.weapon_deg, facing), facing=facing)
