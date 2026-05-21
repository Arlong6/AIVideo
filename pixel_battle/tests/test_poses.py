"""Pose model, interpolation, selection, distinctness, visual safety."""
import math as _math
import os
import types
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.engine.character import Character
from pixel_battle.rl.poses import (
    FigurePose, lerp_pose, ease_in_cubic, ease_out_cubic, ease_in_out_cubic,
    select_pose_id, compute_figure, FigureGeometry, ARCHETYPE_POSES,
    cocked_weapon_deg,
    ELBOW_FLEX_MIN, ELBOW_FLEX_MAX, KNEE_FLEX_MIN, KNEE_FLEX_MAX,
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


def test_easing_monotonic_and_bounded():
    samples = [i * 0.05 for i in range(21)]  # 0.0, 0.05, ..., 1.0
    for ease in (ease_in_cubic, ease_out_cubic, ease_in_out_cubic):
        # endpoints
        assert abs(ease(0.0)) < 1e-9
        assert abs(ease(1.0) - 1.0) < 1e-9
        values = [ease(t) for t in samples]
        # every sample within [0, 1]
        for t, v in zip(samples, values):
            assert 0.0 <= v <= 1.0, f"{ease.__name__}({t}) = {v} out of [0,1]"
        # non-decreasing (monotonic)
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1] + 1e-12, (
                f"{ease.__name__} not monotonic at t={samples[i]:.2f}: "
                f"{values[i]} > {values[i+1]}"
            )


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


# Minimal style for tests (matches the _STYLES schema from Task 8).
_TEST_STYLE = {
    "head_shape": "circle", "head_size": 26, "torso_length": 80,
    "upper_arm": 30, "forearm": 30, "thigh": 34, "shin": 34,
    "line_width": 7, "hand_radius": 6, "foot_length": 18,
}


def _standing(char_id="garen", facing=1):
    c = Character.load(char_id)
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = facing
    c.action_state = "idle"
    c.on_ground = True
    return c


def test_compute_figure_returns_geometry():
    geo = compute_figure(_standing(), _TEST_STYLE)
    assert isinstance(geo, FigureGeometry)


def test_idle_lower_foot_is_planted_at_pos_y():
    c = _standing()
    geo = compute_figure(c, _TEST_STYLE)
    lower_foot_y = max(geo.front_foot[1], geo.back_foot[1])
    assert abs(lower_foot_y - c.pos_y) < 1e-6


def test_facing_mirrors_horizontally():
    right = compute_figure(_standing(facing=1), _TEST_STYLE)
    left = compute_figure(_standing(facing=-1), _TEST_STYLE)
    # Head sits above pos_x for both; mirroring keeps it near centre but
    # flips any horizontal asymmetry of the arms.
    assert abs(right.front_hand[0] - 240) > 0  # arm extends off-centre
    assert abs((right.front_hand[0] - 240) + (left.front_hand[0] - 240)) < 1e-6


def _attacking(vfx, phase, phase_t, char_id="garen"):
    c = Character.load(char_id)
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "attacking"
    c.attack_anim_hint = "jab"
    c.attack_phase = phase
    c.attack_phase_t = phase_t

    class _Sk:
        pass
    s = _Sk()
    s.vfx = vfx
    c.attack_used_kind = s
    return c


def test_all_eight_archetypes_have_pose_tables():
    for a in ("melee", "slam", "spin", "dash",
              "bolt", "multishot", "aura", "beam"):
        assert a in ARCHETYPE_POSES
        assert "cocked" in ARCHETYPE_POSES[a]
        assert "extended" in ARCHETYPE_POSES[a]


def test_archetype_strike_silhouettes_are_pairwise_distinct():
    """Anti-monotony lock: each archetype's strike-end silhouette — front
    hand + front foot + back hand — must differ meaningfully from every
    other archetype's."""
    sigs = {}
    for a in ("melee", "slam", "spin", "dash",
              "bolt", "multishot", "aura", "beam"):
        geo = compute_figure(_attacking(a, "strike", 999), _TEST_STYLE)
        sigs[a] = (geo.front_hand, geo.front_foot, geo.back_hand)
    keys = list(sigs)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            total = sum(_math.hypot(p[0] - q[0], p[1] - q[1])
                        for p, q in zip(sigs[keys[i]], sigs[keys[j]]))
            assert total > 25.0, \
                f"{keys[i]} vs {keys[j]} too similar ({total:.1f}px)"


def test_attack_pose_changes_across_phases():
    w = compute_figure(_attacking("melee", "windup", 10), _TEST_STYLE)
    s = compute_figure(_attacking("melee", "strike", 999), _TEST_STYLE)
    assert w.front_hand != s.front_hand


def test_cocked_weapon_deg_known_pose():
    """cocked_weapon_deg returns the weapon_deg from the pose table."""
    assert cocked_weapon_deg("slam") == ARCHETYPE_POSES["slam"]["cocked"].weapon_deg


def test_cocked_weapon_deg_unknown_falls_back_to_melee():
    """Unknown pose id falls back to the melee cocked weapon angle."""
    assert cocked_weapon_deg("nonsense") == ARCHETYPE_POSES["melee"]["cocked"].weapon_deg


# play.py camera shows CAM_VIEW_H = 502 world px with the floor framed
# ~82% down, so only ~411 px above the feet are ever on-screen.
_MAX_HALF_W = 260      # gross-error guard on horizontal splay from pos_x
_MAX_HEIGHT = 400      # figure + weapon must stay under the camera's top edge


def test_all_poses_keep_feet_planted_and_in_frame():
    from pixel_battle.rl.stick_renderer import get_style
    from pixel_battle.rl.weapons import get_weapon

    pose_specs = [("idle", "none"), ("walk", "none"),
                  ("jump", "none"), ("hit", "none")]
    for a in ("melee", "slam", "spin", "dash",
              "bolt", "multishot", "aura", "beam", "kick"):
        for ph in ("windup", "strike", "recover"):
            pose_specs.append((a, ph))

    for char_id in ("brick_phone", "glass_slab", "garen",
                    "lux", "yasuo", "ashe"):
        style = get_style(char_id)
        weapon = get_weapon(char_id)
        for pose_id, phase in pose_specs:
            for facing in (1, -1):
                c = Character.load(char_id)
                c.pos_x, c.pos_y = 240.0, 720.0
                c.facing = facing
                if phase == "none":
                    c.action_state = ("hit_stagger" if pose_id == "hit"
                                      else "idle")
                    c.on_ground = pose_id != "jump"
                    c.vel_x = 4.0 if pose_id == "walk" else 0.0
                    phase_t_values = (None,)   # static poses: single sample
                else:
                    c.action_state = "attacking"
                    c.attack_phase = phase
                    c.attack_anim_hint = ("kick" if pose_id == "kick"
                                          else "jab")
                    vfx_val = pose_id if pose_id != "kick" else "melee"
                    c.attack_used_kind = types.SimpleNamespace(vfx=vfx_val)
                    phase_t_values = (30, 999)  # mid-sweep + keyframe endpoint

                for attack_phase_t in phase_t_values:
                    if attack_phase_t is not None:
                        c.attack_phase_t = attack_phase_t

                    geo = compute_figure(c, style)
                    tag = f"{char_id}/{pose_id}/{phase}/f{facing}"

                    # Feet: the lower foot is planted exactly at pos_y.
                    lower = max(geo.front_foot[1], geo.back_foot[1])
                    assert abs(lower - c.pos_y) < 1e-6, f"{tag} foot float"

                    # Every drawable point — including the weapon tip — in frame.
                    pts = [geo.head_center, geo.shoulder, geo.hip,
                           geo.front_elbow, geo.front_hand,
                           geo.back_elbow, geo.back_hand,
                           geo.front_knee, geo.front_foot,
                           geo.back_knee, geo.back_foot]
                    if weapon is not None:
                        wr = _math.radians(geo.weapon_deg)
                        pts.append((
                            geo.front_hand[0] + _math.cos(wr) * weapon.length,
                            geo.front_hand[1] + _math.sin(wr) * weapon.length))
                    for px, py in pts:
                        assert abs(px - c.pos_x) < _MAX_HALF_W, f"{tag} too wide"
                        assert c.pos_y - py < _MAX_HEIGHT, f"{tag} too tall"
                        assert py <= c.pos_y + 2, f"{tag} below ground"
