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


from pixel_battle.engine.character import Character
from pixel_battle.rl.poses import select_pose_id


def _char(state="idle", on_ground=True, vel_x=0.0):
    c = Character.load("garen")
    c.action_state = state
    c.on_ground = on_ground
    c.vel_x = vel_x
    return c


def test_select_idle_walk_jump_hit():
    assert select_pose_id(_char("idle")) == "idle"
    assert select_pose_id(_char("idle", vel_x=2.0)) == "walk"
    assert select_pose_id(_char("idle", on_ground=False)) == "jump"
    assert select_pose_id(_char("hit_stagger")) == "hit"


def test_select_attack_uses_vfx_archetype():
    c = _char("attacking")
    c.attack_anim_hint = "jab"
    c.attack_used_kind = c.skills[2]            # garen judgment, vfx "spin"
    assert c.attack_used_kind.vfx == "spin"
    assert select_pose_id(c) == "spin"


def test_select_attack_unknown_vfx_falls_back_to_melee():
    c = _char("attacking")
    c.attack_anim_hint = "jab"

    class _Fake:
        vfx = "nonsense"
    c.attack_used_kind = _Fake()
    assert select_pose_id(c) == "melee"


def test_select_kick_overrides_archetype():
    c = _char("attacking")
    c.attack_anim_hint = "kick"
    c.attack_used_kind = c.skills[0]            # basic, vfx "melee"
    assert select_pose_id(c) == "kick"
