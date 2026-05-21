"""Forward-kinematics for the 2-segment skeleton."""
import math

from pixel_battle.rl.poses import solve_limb, clamp_elbow, clamp_knee


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def test_straight_limb_reaches_full_length():
    root = (0.0, 0.0)
    joint, end = solve_limb(root, seg1_deg=90, flex_deg=0, len1=10, len2=10)
    assert abs(_dist(root, joint) - 10) < 1e-6
    assert abs(_dist(root, end) - 20) < 1e-6


def test_bent_limb_end_is_closer_than_straight():
    root = (0.0, 0.0)
    _, straight = solve_limb(root, 90, 0, 10, 10)
    _, bent = solve_limb(root, 90, 90, 10, 10)
    assert _dist(root, bent) < _dist(root, straight)


def test_joint_sits_at_seg1_length_regardless_of_flex():
    root = (0.0, 0.0)
    j1, _ = solve_limb(root, 90, 0, 12, 8)
    j2, _ = solve_limb(root, 90, 120, 12, 8)
    assert abs(_dist(root, j1) - 12) < 1e-6
    assert abs(_dist(root, j2) - 12) < 1e-6


def test_clamps_bound_flex():
    assert clamp_elbow(999) == 165.0
    assert clamp_elbow(-999) == -165.0
    assert clamp_knee(999) == 165.0
    assert clamp_knee(-999) == -165.0
    assert clamp_elbow(40) == 40.0
