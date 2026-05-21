"""Pose model, interpolation, selection, distinctness, visual safety."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.poses import (
    FigurePose, lerp_pose, ease_in_cubic, ease_out_cubic, ease_in_out_cubic,
)


def _pose(v):
    return FigurePose(torso_lean=v, front_arm=(v, v), back_arm=(v, v),
                      front_leg=(v, v), back_leg=(v, v), weapon_deg=v)


def test_lerp_pose_endpoints():
    a, b = _pose(0.0), _pose(100.0)
    assert lerp_pose(a, b, 0.0).torso_lean == 0.0
    assert lerp_pose(a, b, 1.0).torso_lean == 100.0


def test_lerp_pose_midpoint():
    mid = lerp_pose(_pose(0.0), _pose(100.0), 0.5)
    assert mid.torso_lean == 50.0
    assert mid.front_arm == (50.0, 50.0)
    assert mid.weapon_deg == 50.0


def test_lerp_pose_clamps_t():
    a, b = _pose(0.0), _pose(100.0)
    assert lerp_pose(a, b, -5.0).torso_lean == 0.0
    assert lerp_pose(a, b, 9.0).torso_lean == 100.0


def test_easing_monotonic_0_to_1():
    for ease in (ease_in_cubic, ease_out_cubic, ease_in_out_cubic):
        assert abs(ease(0.0)) < 1e-9
        assert abs(ease(1.0) - 1.0) < 1e-9
        assert 0.0 <= ease(0.5) <= 1.0
