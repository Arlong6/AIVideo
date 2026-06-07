"""Procedural stick figure draw — replaces sprite blits in RL pipeline.

Pose driven by Character.action_state, attack_phase, vel_x, on_ground.
Alan Becker-style polish: filled head, hands, feet, smear trails,
impact burst + landing dust helpers.
"""
from __future__ import annotations
import math
from typing import Optional, Tuple

import pygame

try:
    from pygame import gfxdraw as _gfxdraw
    _HAS_GFXDRAW = True
except ImportError:
    _HAS_GFXDRAW = False

from pixel_battle.engine.character import Character
from pixel_battle.rl.poses import (
    FigureGeometry, compute_figure, cocked_weapon_deg, ease_in_out_cubic,
    select_pose_id,
)
from pixel_battle.rl.weapons import get_weapon, draw_weapon, draw_swing_smear


# ── Constants ────────────────────────────────────────────────────────────────
SMEAR_VEL_THRESHOLD = 2.5  # motion-smear ghosts kick in at walk speed (3.0)

# Motion-afterimage trail — spawned every N render frames when |vel_x| > threshold
MOTION_GHOST_VEL_THRESHOLD = 5.0   # px/frame; faster than a normal walk
MOTION_GHOST_INTERVAL_FRAMES = 3   # spawn one ghost every 3 render frames
MOTION_GHOST_LIFETIME_MS = 180     # each ghost lives 180 ms
MOTION_GHOST_MAX = 4               # max ghosts per character in flight at once
MOTION_GHOST_ALPHA_START = 100     # initial alpha (decays linearly to 0)

# Cross-state transition: when action_state changes, lerp between the last
# geometry snapshot and the new geometry over this many ms. Softened from the
# old snappy 55 → 90 per user direction (2026-05-30): casts/attacks were reading
# as stiff "pops"; 90 eases entry/exit while still landing strikes responsively.
STATE_TRANSITION_MS = 90

# Idle visual feint — renderer-only horizontal drift when a character has been
# idle for > FEINT_ONSET_MS and is within FEINT_ENGAGE_RANGE px of the opponent.
FEINT_ONSET_MS = 240        # ms of idle before feint starts (sooner = fewer dead, frozen holds)
FEINT_AMPLITUDE = 7.5       # ± px of horizontal offset
FEINT_PERIOD_MS = 1200.0    # full oscillation period (ms)
FEINT_ENGAGE_RANGE = 320.0  # px; beyond this, no feint (out-of-fight fringe)

# Default render tick interval for draw_stick_figure (120 fps)
_RENDER_TICK_MS = 1000.0 / 120   # 8.333 ms

# Weapon swing trail — tracked in RenderState, drawn during ACTIVE + early RECOVER
TRAIL_N = 8          # max tip positions buffered
TRAIL_ACTIVE_MS = 80  # how long into RECOVER the trail stays visible


# ── Cross-state pose interpolation ───────────────────────────────────────────

def _lerp_xy(a: Tuple[float, float], b: Tuple[float, float], t: float) -> Tuple[float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def _lerp_geo(a: FigureGeometry, b: FigureGeometry, t: float) -> FigureGeometry:
    """Linear-interpolate every joint position between two FigureGeometry snapshots.

    `t` should already be eased before calling.  weapon_deg is lerped by the
    shortest angular delta to avoid 360° wrap-around artifacts.
    """
    t = max(0.0, min(1.0, t))

    # Shortest-path angular lerp for weapon_deg.
    da = b.weapon_deg - a.weapon_deg
    # Normalise delta into (-180, 180] so lerp always picks the short arc.
    da = (da + 180.0) % 360.0 - 180.0
    weapon_deg = a.weapon_deg + da * t

    return FigureGeometry(
        head_center=_lerp_xy(a.head_center, b.head_center, t),
        shoulder=_lerp_xy(a.shoulder, b.shoulder, t),
        hip=_lerp_xy(a.hip, b.hip, t),
        front_elbow=_lerp_xy(a.front_elbow, b.front_elbow, t),
        front_hand=_lerp_xy(a.front_hand, b.front_hand, t),
        back_elbow=_lerp_xy(a.back_elbow, b.back_elbow, t),
        back_hand=_lerp_xy(a.back_hand, b.back_hand, t),
        front_knee=_lerp_xy(a.front_knee, b.front_knee, t),
        front_foot=_lerp_xy(a.front_foot, b.front_foot, t),
        back_knee=_lerp_xy(a.back_knee, b.back_knee, t),
        back_foot=_lerp_xy(a.back_foot, b.back_foot, t),
        weapon_deg=weapon_deg,
        facing=b.facing,
    )


class RenderState:
    """Per-character renderer cache that smooths pose transitions.

    When the pose key changes, we snapshot the last rendered FigureGeometry as
    the "from" position and lerp into the new target geometry over
    STATE_TRANSITION_MS ms using ease_in_out_cubic.

    Two separate references are maintained:
      _from_geo  — fixed start-of-transition snapshot; does NOT update
                   while a transition is in progress.
      _last_geo  — the geometry returned on the most recent call; used so
                   that if a SECOND state change fires mid-transition, the
                   new transition starts from exactly where the figure
                   visually was (smooth chain-transition).
    """

    def __init__(self) -> None:
        self._last_pose_key: Optional[str] = None
        self._from_geo: Optional[FigureGeometry] = None   # start of current transition
        self._last_geo: Optional[FigureGeometry] = None   # last rendered output
        self._transition_t_ms: float = STATE_TRANSITION_MS  # starts "done"
        # Weapon trail — ring buffer of (tip_x, tip_y) during attack phases
        self._trail: list = []   # list of (x, y) tip positions, newest last
        self._trail_recover_ms: float = 0.0  # elapsed ms in recover when trail active
        # Motion-afterimage ghosts — list of (geo_snapshot, age_ms)
        # spawned every N frames when |vel_x| > MOTION_GHOST_VEL_THRESHOLD
        self._motion_ghosts: list = []   # [(FigureGeometry, age_ms), ...]
        self._motion_ghost_frame_counter: int = 0
        # Walk cycle phase — accumulated ms while pose_id == "walk"
        self._walk_phase_t: float = 0.0
        # Idle feint — accumulated ms while in idle near an opponent
        # Used to drive a renderer-only horizontal drift (anti-statue bob).
        self._idle_t_ms: float = 0.0
        # Last computed feint dx (drawn-position-only offset, px).
        # Preserved across state changes so the cross-state lerp can taper it
        # back to 0 smoothly without a visible snap.
        self._feint_dx: float = 0.0

    def resolve(self, char, style: dict, dt_ms: float = 16.0,
                time_ms: float = 0.0) -> FigureGeometry:
        """Return the smoothed FigureGeometry for `char` this frame.

        Call exactly once per draw call.  `dt_ms` must match the render tick.
        `time_ms` is forwarded to compute_figure for sub-pose oscillations
        (e.g. idle breathing bob).
        """
        new_key = _pose_key(char)
        new_geo = compute_figure(char, style, time_ms)

        # ── Bootstrap (first call) ────────────────────────────────────────────
        if self._last_pose_key is None:
            self._last_pose_key = new_key
            self._from_geo = new_geo
            self._last_geo = new_geo
            self._transition_t_ms = STATE_TRANSITION_MS
            return new_geo

        # ── Walk phase accumulator ────────────────────────────────────────────
        if new_key == "walk":
            self._walk_phase_t += dt_ms
        else:
            self._walk_phase_t = 0.0

        # ── State changed? Start a fresh transition ───────────────────────────
        if new_key != self._last_pose_key:
            # Snapshot the LAST rendered output as the "from" position.
            # If we were mid-transition, _last_geo is already a blended
            # intermediate — starting from there gives a smooth chain.
            self._from_geo = self._last_geo
            self._transition_t_ms = 0.0
            self._last_pose_key = new_key

        # ── Advance timer ─────────────────────────────────────────────────────
        self._transition_t_ms += dt_ms

        if self._transition_t_ms >= STATE_TRANSITION_MS:
            # Transition complete — apply walk bob and return.
            out = self._apply_walk_bob(new_geo, new_key)
            self._last_geo = out
            return out

        # ── Mid-transition: lerp _from_geo → new_geo ─────────────────────────
        frac = ease_in_out_cubic(self._transition_t_ms / STATE_TRANSITION_MS)
        blended = _lerp_geo(self._from_geo, new_geo, frac)
        # Walk bob on the blended result (mid-transition walk keeps bobbing).
        blended = self._apply_walk_bob(blended, new_key)
        self._last_geo = blended
        return blended

    # ── Walk-cycle vertical bob + horizontal pelvis sway ─────────────────────
    def _apply_walk_bob(self, geo: FigureGeometry, pose_key: str) -> FigureGeometry:
        """Shift hip+torso+arms with a figure-8 walk sway; feet stay planted.

        Only applied while ``pose_key == "walk"``.
        - Vertical bob: 2 px amplitude, 400 ms period.
        - Horizontal sway: 1 px amplitude, 90° out of phase with the bob.
          Gives a natural hip figure-8 motion.
        """
        if pose_key != "walk":
            return geo
        phase = self._walk_phase_t / 400.0 * 2.0 * math.pi
        bob_y = math.sin(phase) * 2.0
        sway_x = math.cos(phase) * 1.0  # 90° out of phase
        new_hip = (geo.hip[0] + sway_x, geo.hip[1] + bob_y)
        # Preserve exact torso length/direction.
        dx = geo.shoulder[0] - geo.hip[0]
        dy = geo.shoulder[1] - geo.hip[1]
        dist = max(0.001, math.hypot(dx, dy))
        tc_w, ts_w = dx / dist, dy / dist
        new_shoulder = (new_hip[0] + tc_w * dist, new_hip[1] + ts_w * dist)
        head_offset_dx = geo.head_center[0] - geo.shoulder[0]
        head_offset_dy = geo.head_center[1] - geo.shoulder[1]
        new_head = (new_shoulder[0] + head_offset_dx, new_shoulder[1] + head_offset_dy)
        return FigureGeometry(
            head_center=new_head,
            shoulder=new_shoulder,
            hip=new_hip,
            front_elbow=(geo.front_elbow[0] + sway_x, geo.front_elbow[1] + bob_y),
            front_hand=(geo.front_hand[0] + sway_x, geo.front_hand[1] + bob_y),
            back_elbow=(geo.back_elbow[0] + sway_x, geo.back_elbow[1] + bob_y),
            back_hand=(geo.back_hand[0] + sway_x, geo.back_hand[1] + bob_y),
            front_knee=geo.front_knee,   # feet stay planted
            front_foot=geo.front_foot,
            back_knee=geo.back_knee,
            back_foot=geo.back_foot,
            weapon_deg=geo.weapon_deg,
            facing=geo.facing,
        )

    @property
    def transition_active(self) -> bool:
        """True while a cross-state lerp is in progress."""
        return self._transition_t_ms < STATE_TRANSITION_MS

    @property
    def walk_phase_t(self) -> float:
        """Accumulated ms since the character has been continuously walking."""
        return self._walk_phase_t

    def update_trail(self, char, geo: FigureGeometry, weapon, dt_ms: float) -> None:
        """Update the weapon-tip trail buffer based on the current attack phase.

        Call AFTER resolve() so `geo` is the final smoothed geometry.
        """
        phase = getattr(char, "attack_phase", "none")
        if weapon is None:
            self._trail = []
            self._trail_recover_ms = 0.0
            return

        import math as _m
        wr = _m.radians(geo.weapon_deg)
        tip = (geo.front_hand[0] + _m.cos(wr) * weapon.length,
               geo.front_hand[1] + _m.sin(wr) * weapon.length)

        if phase == "active":
            self._trail_recover_ms = 0.0
            self._trail.append(tip)
            if len(self._trail) > TRAIL_N:
                self._trail.pop(0)
        elif phase == "recover":
            self._trail_recover_ms += dt_ms
            if self._trail_recover_ms <= TRAIL_ACTIVE_MS:
                self._trail.append(tip)
                if len(self._trail) > TRAIL_N:
                    self._trail.pop(0)
            else:
                # Fade out complete — clear for next attack
                self._trail = []
        else:
            self._trail = []
            self._trail_recover_ms = 0.0

    def draw_trail(self, surf: pygame.Surface, char, color: tuple,
                   weapon) -> None:
        """Draw the fading arc connecting buffered weapon-tip positions.

        Width and tint depend on the attack's skill type:
          basic → 3 px, brand color
          cooldown/special → 5 px, blend toward white
          ultimate → 7 px, full white
        """
        if len(self._trail) < 2:
            return
        skill = getattr(char, "attack_used_kind", None)
        hint = getattr(char, "attack_anim_hint", "jab")
        if skill is not None:
            st = getattr(skill, "skill_type", None)
            from pixel_battle.engine.skill import SkillType as _ST
            if st is _ST.ULTIMATE:
                trail_width = 7
                base_color = (255, 255, 255)
            elif st in (_ST.COOLDOWN, _ST.SPECIAL):
                trail_width = 5
                # blend brand color 50% toward white
                base_color = (
                    min(255, color[0] + (255 - color[0]) // 2),
                    min(255, color[1] + (255 - color[1]) // 2),
                    min(255, color[2] + (255 - color[2]) // 2),
                )
            else:
                trail_width = 3
                base_color = color
        else:
            trail_width = 3
            base_color = color

        n = len(self._trail)
        trail_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        for i in range(1, n):
            # Newer segments are brighter; older are transparent
            alpha = int(220 * i / (n - 1)) if n > 1 else 220
            p0 = (int(self._trail[i - 1][0]), int(self._trail[i - 1][1]))
            p1 = (int(self._trail[i][0]), int(self._trail[i][1]))
            pygame.draw.line(trail_surf, (*base_color, alpha), p0, p1, trail_width)
        surf.blit(trail_surf, (0, 0))


    def update_idle_feint(self, char, dt_ms: float,
                           opponent_x: Optional[float] = None) -> float:
        """Update idle feint timer and return the current drawn-position-only dx.

        Rules:
          - While char.action_state == 'idle' AND distance to opponent ≤
            FEINT_ENGAGE_RANGE: accumulate _idle_t_ms, compute sinusoidal feint.
          - While NOT idle (or opponent too far): decay _idle_t_ms toward 0 and
            let the existing STATE_TRANSITION_MS lerp taper the offset naturally
            (we just hold _feint_dx; the cross-state blend handles fade-out via
            the draw-position offset in draw_stick_figure).
        The returned dx is drawn-position-only; char.pos_x is never modified.
        """
        action_state = getattr(char, "action_state", "idle")
        own_x = float(getattr(char, "pos_x", 0.0))
        dist = abs(own_x - (opponent_x or 9999.0))

        if action_state == "idle" and dist <= FEINT_ENGAGE_RANGE:
            self._idle_t_ms += dt_ms
        else:
            # Not idle or out of range — reset timer, feint dx decays via lerp
            self._idle_t_ms = 0.0

        if self._idle_t_ms >= FEINT_ONSET_MS:
            # Sinusoidal drift, onset-adjusted so it starts from 0
            onset_t = self._idle_t_ms - FEINT_ONSET_MS
            self._feint_dx = math.sin(
                2.0 * math.pi * onset_t / FEINT_PERIOD_MS
            ) * FEINT_AMPLITUDE
        else:
            # Before onset: smoothly decay toward 0 rather than snap
            # (also handles the "just left idle" case)
            decay = 1.0 - min(1.0, dt_ms / STATE_TRANSITION_MS)
            self._feint_dx *= decay

        return self._feint_dx

    def update_motion_ghosts(self, char, style: dict, dt_ms: float) -> None:
        """Snapshot the current figure if the character is moving fast enough.

        Spawns a new ghost every MOTION_GHOST_INTERVAL_FRAMES render frames
        when |vel_x| > MOTION_GHOST_VEL_THRESHOLD AND the character is on the
        ground (not airborne — jumps have their own trail).  Max MOTION_GHOST_MAX
        ghosts in flight; oldest evicted.
        """
        # Tick all existing ghosts
        surviving = []
        for (geo_snap, age_ms) in self._motion_ghosts:
            age_ms += dt_ms
            if age_ms < MOTION_GHOST_LIFETIME_MS:
                surviving.append((geo_snap, age_ms))
        self._motion_ghosts = surviving

        # Decide whether to spawn a new ghost this frame
        vel = abs(getattr(char, "vel_x", 0.0))
        on_ground = getattr(char, "on_ground", True)
        if vel > MOTION_GHOST_VEL_THRESHOLD and on_ground:
            self._motion_ghost_frame_counter += 1
            if self._motion_ghost_frame_counter >= MOTION_GHOST_INTERVAL_FRAMES:
                self._motion_ghost_frame_counter = 0
                if self._last_geo is not None:
                    # Evict oldest if at capacity
                    while len(self._motion_ghosts) >= MOTION_GHOST_MAX:
                        self._motion_ghosts.pop(0)
                    self._motion_ghosts.append((self._last_geo, 0.0))
        else:
            self._motion_ghost_frame_counter = 0

    def draw_motion_ghosts(self, surf: pygame.Surface, color: tuple,
                            style: dict) -> None:
        """Draw all live motion-afterimage ghosts as faded skeleton silhouettes."""
        if not self._motion_ghosts:
            return
        lw = max(1, style["line_width"] - 1)
        for (geo, age_ms) in self._motion_ghosts:
            frac = age_ms / max(1.0, MOTION_GHOST_LIFETIME_MS)
            alpha = max(0, int(MOTION_GHOST_ALPHA_START * (1.0 - frac)))
            if alpha < 4:
                continue
            ghost = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            gc = (color[0], color[1], color[2], alpha)
            # Minimal silhouette: torso + front arm + front leg
            pygame.draw.line(ghost, gc, _ixy(geo.hip), _ixy(geo.shoulder), lw)
            pygame.draw.line(ghost, gc, _ixy(geo.shoulder),
                             _ixy(geo.front_elbow), lw)
            pygame.draw.line(ghost, gc, _ixy(geo.front_elbow),
                             _ixy(geo.front_hand), lw)
            pygame.draw.line(ghost, gc, _ixy(geo.hip),
                             _ixy(geo.front_knee), lw)
            surf.blit(ghost, (0, 0))


def _ixy(pt: Tuple[float, float]) -> Tuple[int, int]:
    """Convert a float (x, y) pair to an int tuple for pygame drawing."""
    return (int(pt[0]), int(pt[1]))


def _pose_key(char) -> str:
    """A string that uniquely identifies the current pose bucket.

    Changes whenever a state-transition should begin. Using select_pose_id
    captures both action_state and physics conditions (vel, on_ground) the
    same way the pose resolver does, so the key changes exactly when the
    rendered pose would snap.
    """
    return select_pose_id(char)


# Module-level cache: one RenderState per character object identity.
# The cache lives at module scope so it persists across draw calls within a
# single render run.  It is keyed by `id(char)` which is stable for the
# lifetime of a single Battle instance.
_RENDER_STATE_CACHE: dict = {}


def _swing_smear_start_angle(pose_id: str, facing: int) -> float:
    """Weapon angle at the start of the strike sweep, in `facing` space.

    `cocked_weapon_deg` is authored for facing +1; mirror it for facing -1.
    """
    cocked = cocked_weapon_deg(pose_id)
    return cocked if facing >= 0 else 180.0 - cocked

# Per-character visual style. Limb lengths are split into two segments
# (upper_arm + forearm, thigh + shin) for the jointed skeleton.
_STYLES = {
    "brick_phone": {"head_shape": "square",   "head_size": 26, "crest": "antenna",
                    "torso_length": 88, "upper_arm": 30, "forearm": 30,
                    "thigh": 32, "shin": 32, "line_width": 8,
                    "hand_radius": 7, "foot_length": 22},
    "glass_slab":  {"head_shape": "triangle", "head_size": 30,
                    "torso_length": 104, "upper_arm": 31, "forearm": 31,
                    "thigh": 35, "shin": 35, "line_width": 5,
                    "hand_radius": 4, "foot_length": 14},
    "lux":         {"head_shape": "diamond",  "head_size": 30,
                    "torso_length": 108, "upper_arm": 30, "forearm": 30,
                    "thigh": 36, "shin": 36, "line_width": 5,
                    "hand_radius": 4, "foot_length": 13,
                    # Pose overrides — make Lux read as a mage, not a brawler.
                    # idle_weapon_deg: staff raised UP-back (held high, mage at the ready).
                    # walk_weapon_deg: staff carried up-forward.
                    # idle_torso_lean: slight forward lean, she's always leaning into magic.
                    "pose_overrides": {
                        "idle_weapon_deg": -118.0,
                        "walk_weapon_deg": -70.0,
                        "idle_torso_lean": 5.0,
                        # Staff micro-rotation: reads as "casting at the ready, staff alive".
                        "idle_oscillations": [
                            {"field": "weapon_deg", "amplitude": 8.0, "period_ms": 3000.0},
                        ],
                    }},
    "garen":       {"head_shape": "square",   "head_size": 28, "crest": "plume",
                    "torso_length": 86, "upper_arm": 32, "forearm": 31,
                    "thigh": 31, "shin": 31, "line_width": 9,
                    "hand_radius": 8, "foot_length": 22,
                    # Stoic shoulder shift — not statuesque, just vigilant.
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "weapon_deg", "amplitude": 2.0, "period_ms": 2500.0},
                        ],
                    }},
    "yasuo":       {"head_shape": "circle",   "head_size": 27, "crest": "topknot",
                    "torso_length": 94, "upper_arm": 33, "forearm": 32,
                    "thigh": 33, "shin": 33, "line_width": 6,
                    "hand_radius": 5, "foot_length": 15,
                    # Sword-hand twitch — twitchy duelist, always ready to draw.
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "near_hand_y_offset", "amplitude": 3.0, "period_ms": 800.0},
                        ],
                    }},
    "ashe":        {"head_shape": "triangle", "head_size": 27, "crest": "hood",
                    "torso_length": 96, "upper_arm": 34, "forearm": 33,
                    "thigh": 33, "shin": 33, "line_width": 5,
                    "hand_radius": 4, "foot_length": 13,
                    # Bowstring tension test — subtle pull-back.
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "far_hand_x_offset", "amplitude": 2.0, "period_ms": 1800.0},
                        ],
                    }},
    # ── New roster: pushed-apart builds so silhouette alone separates them ──
    "mordekaiser": {"head_shape": "square",   "head_size": 34, "crest": "horns",
                    "torso_length": 100, "upper_arm": 34, "forearm": 33,
                    "thigh": 36, "shin": 36, "line_width": 13,   # brute: thickest limbs
                    "hand_radius": 10, "foot_length": 28,
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "weapon_deg", "amplitude": 1.5, "period_ms": 2600.0},
                        ],
                    }},
    "pantheon":    {"head_shape": "circle",   "head_size": 28, "crest": "mohawk_helm",
                    "torso_length": 92, "upper_arm": 33, "forearm": 32,
                    "thigh": 34, "shin": 34, "line_width": 8,
                    "hand_radius": 6, "foot_length": 19},
    "katarina":    {"head_shape": "circle",   "head_size": 23, "crest": "ponytail",
                    "torso_length": 104, "upper_arm": 32, "forearm": 33,
                    "thigh": 37, "shin": 37, "line_width": 4,    # slim assassin, tall
                    "hand_radius": 3, "foot_length": 12,
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "near_hand_y_offset", "amplitude": 3.0, "period_ms": 700.0},
                        ],
                    }},
    "jinx":        {"head_shape": "circle",   "head_size": 25, "crest": "twin_tails",
                    "torso_length": 106, "upper_arm": 35, "forearm": 35,  # lanky, long arms
                    "thigh": 37, "shin": 37, "line_width": 4,
                    "hand_radius": 3, "foot_length": 12},
    # ── New 10 archetypes — build + crest + (unique) weapon separate them ──
    "bulwark":     {"head_shape": "square",   "head_size": 30, "crest": "great_helm",
                    "torso_length": 90, "upper_arm": 32, "forearm": 31,
                    "thigh": 33, "shin": 33, "line_width": 11,   # broad defensive tank
                    "hand_radius": 8, "foot_length": 24},
    "ironfist":    {"head_shape": "circle",   "head_size": 24, "crest": "topknot",
                    "torso_length": 92, "upper_arm": 36, "forearm": 35,  # long arms, puncher
                    "thigh": 32, "shin": 32, "line_width": 8,
                    "hand_radius": 9, "foot_length": 17,         # big fists
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "near_hand_y_offset", "amplitude": 4.0, "period_ms": 600.0},
                        ]}},
    "reaver":      {"head_shape": "triangle", "head_size": 25, "crest": "hood",
                    "torso_length": 112, "upper_arm": 33, "forearm": 34,  # tall, gaunt
                    "thigh": 38, "shin": 38, "line_width": 6,
                    "hand_radius": 4, "foot_length": 14},
    "deadeye":     {"head_shape": "circle",   "head_size": 26, "crest": "wide_brim",
                    "torso_length": 98, "upper_arm": 32, "forearm": 32,
                    "thigh": 34, "shin": 34, "line_width": 5,
                    "hand_radius": 4, "foot_length": 14},
    "cyclone":     {"head_shape": "circle",   "head_size": 26, "crest": "topknot",
                    "torso_length": 100, "upper_arm": 32, "forearm": 32,
                    "thigh": 35, "shin": 35, "line_width": 6,
                    "hand_radius": 5, "foot_length": 15,
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "weapon_deg", "amplitude": 6.0, "period_ms": 2200.0},
                        ]}},
    "wrecker":     {"head_shape": "square",   "head_size": 32, "crest": "spikes",
                    "torso_length": 96, "upper_arm": 34, "forearm": 33,
                    "thigh": 36, "shin": 36, "line_width": 12,   # brute, slightly < juggernaut
                    "hand_radius": 9, "foot_length": 26},
    "quarrel":     {"head_shape": "triangle", "head_size": 26, "crest": "hood",
                    "torso_length": 98, "upper_arm": 33, "forearm": 33,
                    "thigh": 34, "shin": 34, "line_width": 5,
                    "hand_radius": 4, "foot_length": 14},
    "cleaver":     {"head_shape": "square",   "head_size": 30, "crest": "horns",
                    "torso_length": 92, "upper_arm": 34, "forearm": 33,
                    "thigh": 35, "shin": 35, "line_width": 10,   # wide berserker
                    "hand_radius": 8, "foot_length": 23},
    "pyre":        {"head_shape": "diamond",  "head_size": 29, "crest": "flame_crown",
                    "torso_length": 106, "upper_arm": 30, "forearm": 30,  # lean mage
                    "thigh": 36, "shin": 36, "line_width": 5,
                    "hand_radius": 4, "foot_length": 13,
                    "pose_overrides": {
                        "idle_weapon_deg": -112.0, "walk_weapon_deg": -65.0,
                        "idle_torso_lean": 4.0,
                        "idle_oscillations": [
                            {"field": "weapon_deg", "amplitude": 9.0, "period_ms": 2600.0},
                        ]}},
    "venom":       {"head_shape": "circle",   "head_size": 23, "crest": "ninja_band",
                    "torso_length": 104, "upper_arm": 33, "forearm": 34,  # lithe ninja
                    "thigh": 37, "shin": 37, "line_width": 4,
                    "hand_radius": 3, "foot_length": 12,
                    "pose_overrides": {
                        "idle_oscillations": [
                            {"field": "near_hand_y_offset", "amplitude": 3.0, "period_ms": 750.0},
                        ]}},
}

_DEFAULT_STYLE = {"head_shape": "circle", "head_size": 22,
                  "torso_length": 80, "upper_arm": 28, "forearm": 28,
                  "thigh": 30, "shin": 30, "line_width": 4,
                  "hand_radius": 4, "foot_length": 12}


_FIGURE_SCALE = 0.54       # shrink every figure ~46% — small fighters, wide arena (ranged-kite feel)
_SCALED_KEYS = frozenset({"head_size", "torso_length", "upper_arm", "forearm",
                          "thigh", "shin", "line_width", "hand_radius", "foot_length"})


# Capes — char_id → RGB. A flowing cloak adds heroic silhouette weight; kept off
# the lithe/bare fighters (assassins, brawler, monk) on purpose.
_CAPES = {
    "garen": (40, 90, 200), "mordekaiser": (120, 30, 40),
    "pantheon": (190, 60, 50), "bulwark": (60, 100, 160),
    "reaver": (70, 40, 110), "pyre": (200, 70, 20),
    "wrecker": (90, 70, 70), "skylance": (190, 60, 50),
}


def get_style(char_id: str) -> dict:
    base = _STYLES.get(char_id, _DEFAULT_STYLE)
    out = {k: (max(1, int(v * _FIGURE_SCALE)) if k in _SCALED_KEYS else v)
           for k, v in base.items()}
    if char_id in _CAPES:
        out["cape"] = _CAPES[char_id]
    return out


# ── Jointed skeleton draw helpers ─────────────────────────────────────────────

def _draw_limb(surf, color, root, joint, end, line_width, cap_radius):
    pygame.draw.line(surf, color, root, joint, line_width)
    pygame.draw.line(surf, color, joint, end, line_width)
    pygame.draw.circle(surf, color, (int(end[0]), int(end[1])), cap_radius)


def _draw_foot(surf, color, knee, foot, line_width, foot_length):
    dx, dy = foot[0] - knee[0], foot[1] - knee[1]
    n = math.hypot(dx, dy) or 1.0
    px, py = -dy / n, dx / n
    half = foot_length / 2
    pygame.draw.line(surf, color, knee, foot, line_width)
    pygame.draw.line(surf, color,
                     (foot[0] + px * half, foot[1] + py * half),
                     (foot[0] - px * half, foot[1] - py * half), line_width)


def _draw_head(surf, color, geo, style):
    cx, cy = int(geo.head_center[0]), int(geo.head_center[1])
    hs = style["head_size"]
    shape = style["head_shape"]
    if shape == "square":
        rect = pygame.Rect(cx - hs, cy - hs, hs * 2, hs * 2)
        pygame.draw.rect(surf, color, rect)
        pygame.draw.rect(surf, (0, 0, 0), rect, 2)
    elif shape == "triangle":
        pts = [(cx, cy + hs), (cx - hs, cy - hs), (cx + hs, cy - hs)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (0, 0, 0), pts, 2)
    elif shape == "diamond":
        pts = [(cx, cy - hs), (cx + hs, cy), (cx, cy + hs), (cx - hs, cy)]
        pygame.draw.polygon(surf, color, pts)
        pygame.draw.polygon(surf, (0, 0, 0), pts, 2)
    else:
        pygame.draw.circle(surf, color, (cx, cy), hs)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), hs, 2)


def _draw_crest(surf, color, accent, geo, style):
    """Draw a per-champion headgear/hair crest on top of the head. This is the
    single strongest 'who is this' cue at small figure scale — far more legible
    than body build. `style['crest']` selects the shape; `facing` orients the
    asymmetric ones (hair/hoods trail BEHIND the head)."""
    crest = style.get("crest")
    if not crest:
        return
    cx, cy = int(geo.head_center[0]), int(geo.head_center[1])
    hs = style["head_size"]
    f = geo.facing
    back = -f                      # +x is the way the figure faces; hair trails back
    blk = (0, 0, 0)

    def poly(pts, fill, outline=blk, ow=1):
        ipts = [(int(x), int(y)) for x, y in pts]
        pygame.draw.polygon(surf, fill, ipts)
        if ow:
            pygame.draw.polygon(surf, outline, ipts, ow)

    if crest == "horns":           # demon brute — two curved horns up-out
        for s in (-1, 1):
            base = (cx + s * hs * 0.7, cy - hs * 0.6)
            poly([base, (base[0] + s * hs * 0.5, cy - hs * 1.9),
                  (base[0] + s * hs * 1.05, cy - hs * 1.2),
                  (base[0] + s * hs * 0.3, cy - hs * 0.3)], accent)
    elif crest == "mohawk_helm":   # spartan — a front-to-back crest plume
        top = cy - hs
        poly([(cx - hs * 0.9, top), (cx + hs * 0.9, top),
              (cx + hs * 0.5, top - hs * 1.3), (cx - hs * 0.5, top - hs * 1.3)],
             accent)
    elif crest == "plume":         # knight — single feather plume off the top
        top = (cx - back * hs * 0.2, cy - hs)
        poly([top, (top[0] - back * hs * 1.4, top[1] - hs * 1.5),
              (top[0] - back * hs * 0.5, top[1] - hs * 0.4)], accent)
    elif crest == "topknot":       # samurai bun + short tail behind
        knot = (cx - back * hs * 0.2, cy - hs * 1.15)
        pygame.draw.circle(surf, color, (int(knot[0]), int(knot[1])), max(2, int(hs * 0.45)))
        pygame.draw.circle(surf, blk, (int(knot[0]), int(knot[1])), max(2, int(hs * 0.45)), 1)
    elif crest == "ponytail":      # assassin — high tail whipping back
        root = (cx + back * hs * 0.5, cy - hs * 0.7)
        poly([root, (root[0] + back * hs * 1.7, root[1] - hs * 0.5),
              (root[0] + back * hs * 1.5, root[1] + hs * 0.6),
              (root[0] + back * hs * 0.2, root[1] + hs * 0.2)], color)
    elif crest == "twin_tails":    # gunner — two long tails out the sides
        for s in (-1, 1):
            root = (cx + s * hs * 0.8, cy)
            poly([root, (root[0] + s * hs * 0.6, cy + hs * 1.9),
                  (root[0] + s * hs * 1.2, cy + hs * 1.7),
                  (root[0] + s * hs * 0.4, cy - hs * 0.2)], color)
    elif crest == "hood":          # ranger — a peaked hood over+behind the head
        poly([(cx + back * hs * 1.3, cy - hs * 0.2), (cx - back * hs * 0.2, cy - hs * 1.5),
              (cx - back * hs * 0.9, cy - hs * 0.3), (cx + back * hs * 0.6, cy + hs * 0.4)],
             accent)
    elif crest == "great_helm":    # tank — full visored helm dome + slit + top fin
        pygame.draw.circle(surf, accent, (cx, int(cy - hs * 0.1)), max(2, int(hs * 0.95)))
        pygame.draw.circle(surf, blk, (cx, int(cy - hs * 0.1)), max(2, int(hs * 0.95)), 1)
        pygame.draw.line(surf, blk, (cx - hs * 0.7, cy - hs * 0.1),
                         (cx + hs * 0.7, cy - hs * 0.1), 2)
        poly([(cx - hs * 0.22, cy - hs * 0.9), (cx + hs * 0.22, cy - hs * 0.9),
              (cx, cy - hs * 1.55)], accent)
    elif crest == "wide_brim":     # gunslinger — wide hat brim + cap
        top = cy - hs * 0.85
        poly([(cx - hs * 1.5, top), (cx + hs * 1.5, top),
              (cx + hs * 1.15, top + hs * 0.28), (cx - hs * 1.15, top + hs * 0.28)], accent)
        poly([(cx - hs * 0.62, top), (cx + hs * 0.62, top),
              (cx + hs * 0.46, top - hs * 0.85), (cx - hs * 0.46, top - hs * 0.85)], accent)
    elif crest == "spikes":        # brute — row of three upward spikes
        top = cy - hs
        for s in (-1, 0, 1):
            bx = cx + s * hs * 0.62
            poly([(bx - hs * 0.22, top), (bx + hs * 0.22, top),
                  (bx, top - hs * 0.95)], accent)
    elif crest == "flame_crown":   # fire mage — flame tongues rising off the crown
        top = cy - hs * 0.85
        for s in (-1, 0, 1):
            bx = cx + s * hs * 0.55
            h2 = hs * (1.4 if s == 0 else 0.95)
            poly([(bx - hs * 0.26, top), (bx + hs * 0.26, top),
                  (bx + hs * 0.06, top - h2)], accent)
    elif crest == "ninja_band":    # ninja — forehead band + two tails trailing back
        pygame.draw.line(surf, accent, (cx - hs * 0.95, cy - hs * 0.45),
                         (cx + hs * 0.95, cy - hs * 0.45), max(2, int(hs * 0.32)))
        root = (cx + back * hs * 0.75, cy - hs * 0.4)
        for dy in (0.0, 0.45):
            poly([root, (root[0] + back * hs * 1.5, root[1] + hs * dy),
                  (root[0] + back * hs * 1.35, root[1] + hs * (dy + 0.35)),
                  (root[0], root[1] + hs * 0.18)], accent)
    elif crest == "antenna":       # brick phone — stubby antenna
        ax = cx - back * hs * 0.4
        pygame.draw.line(surf, accent, (ax, cy - hs), (ax, cy - hs * 1.9), 3)
        pygame.draw.circle(surf, accent, (int(ax), int(cy - hs * 1.9)), 3)


# ── Ghost (smear) drawing ─────────────────────────────────────────────────────

def _draw_ghost(surf, char, color, offset_x, alpha, style):
    """Faded torso + front-arm ghost for fast-movement smear."""
    w, h = surf.get_size()
    ghost = pygame.Surface((w, h), pygame.SRCALPHA)
    orig_x = char.pos_x
    char.pos_x = orig_x + offset_x
    try:
        geo = compute_figure(char, style)
    finally:
        char.pos_x = orig_x
    gc = (color[0], color[1], color[2], alpha)
    lw = style["line_width"]
    pygame.draw.line(ghost, gc, geo.hip, geo.shoulder, lw)
    pygame.draw.line(ghost, gc, geo.shoulder, geo.front_elbow, lw)
    pygame.draw.line(ghost, gc, geo.front_elbow, geo.front_hand, lw)
    surf.blit(ghost, (0, 0))


def _draw_cape(surf, geo, style, time_ms: float, vel_x: float) -> None:
    """A flowing cape behind the figure (style['cape'] = RGB). Billows with a
    gentle time wave plus a velocity-driven drag, so it reads as cloth in motion.
    Drawn before the back limbs so the body sits on top of it."""
    cape_col = style.get("cape")
    if not cape_col:
        return
    f = geo.facing
    back = -f                          # cape trails the way the figure faces away
    sx, sy = geo.shoulder
    L = style["torso_length"] * 1.08
    w = max(3, style["line_width"])
    sway = math.sin(time_ms / 240.0) * 5.0 - float(vel_x) * 2.6   # billow + drag
    collar1 = (sx - f * w * 0.4, sy - w * 0.3)
    collar2 = (sx + back * w * 1.3, sy + w * 0.2)
    hemx = sx + back * (L * 0.42) + sway
    hem_out = (hemx + back * w * 2.2, sy + L * 0.88)
    hem_in = (hemx - w * 1.1 + back * w * 0.4, sy + L)
    pts = [(int(collar1[0]), int(collar1[1])), (int(collar2[0]), int(collar2[1])),
           (int(hem_out[0]), int(hem_out[1])), (int(hem_in[0]), int(hem_in[1]))]
    pygame.draw.polygon(surf, cape_col, pts)
    pygame.draw.polygon(surf, (0, 0, 0), pts, 1)


# ── Main draw function ────────────────────────────────────────────────────────

def draw_stick_figure(surf, char, color, dt_ms: float = _RENDER_TICK_MS,
                      time_ms: float = 0.0,
                      opponent_x: Optional[float] = None):
    """Draw a jointed stick figure for `char` onto `surf` in `color`.

    `dt_ms` should match the render tick interval (default 8.333 ms = 120 fps).
    It is forwarded to the per-character RenderState for transition timing.
    `time_ms` is the current render time in ms, used for idle breathing bob.
    `opponent_x` is used for the idle feint range check.  Pass the opponent's
    current pos_x so the feint only fires when characters are close enough to
    be "in the fight."  If None (default), the feint is suppressed.
    """
    style = get_style(char.id)
    lw = style["line_width"]

    if abs(char.vel_x) > SMEAR_VEL_THRESHOLD:
        _draw_ghost(surf, char, color, -int(char.vel_x * 8), 64, style)
        _draw_ghost(surf, char, color, -int(char.vel_x * 4), 128, style)

    char_key = id(char)
    if char_key not in _RENDER_STATE_CACHE:
        _RENDER_STATE_CACHE[char_key] = RenderState()
    rs = _RENDER_STATE_CACHE[char_key]
    geo = rs.resolve(char, style, dt_ms=dt_ms, time_ms=time_ms)

    # ── Idle visual feint: renderer-only horizontal drift ────────────────────
    # Doesn't touch char.pos_x; just offsets the drawn position.
    feint_dx = rs.update_idle_feint(char, dt_ms=dt_ms, opponent_x=opponent_x)
    if feint_dx != 0.0:
        # Shift every joint in the geometry by feint_dx (x-axis only)
        def _shift(pt):
            return (pt[0] + feint_dx, pt[1])
        from pixel_battle.rl.poses import FigureGeometry as _FG
        geo = _FG(
            head_center=_shift(geo.head_center),
            shoulder=_shift(geo.shoulder),
            hip=_shift(geo.hip),
            front_elbow=_shift(geo.front_elbow),
            front_hand=_shift(geo.front_hand),
            back_elbow=_shift(geo.back_elbow),
            back_hand=_shift(geo.back_hand),
            front_knee=_shift(geo.front_knee),
            front_foot=_shift(geo.front_foot),
            back_knee=_shift(geo.back_knee),
            back_foot=_shift(geo.back_foot),
            weapon_deg=geo.weapon_deg,
            facing=geo.facing,
        )

    # Motion-afterimage ghosts: update snapshot queue, then draw behind figure
    rs.update_motion_ghosts(char, style, dt_ms=dt_ms)
    rs.draw_motion_ghosts(surf, color, style)

    # Cape (if any) sits behind the body.
    _draw_cape(surf, geo, style, time_ms, char.vel_x)

    # Back limbs first (depth).
    _draw_limb(surf, color, geo.shoulder, geo.back_elbow, geo.back_hand,
               lw, style["hand_radius"])
    _draw_foot(surf, color, geo.back_knee, geo.back_foot, lw,
               style["foot_length"])
    pygame.draw.line(surf, color, geo.hip, geo.back_knee, lw)

    # Torso + head + front leg.
    pygame.draw.line(surf, color, geo.hip, geo.shoulder, lw)
    _draw_head(surf, color, geo, style)
    _draw_crest(surf, color, char.accent_color, geo, style)
    _draw_foot(surf, color, geo.front_knee, geo.front_foot, lw,
               style["foot_length"])
    pygame.draw.line(surf, color, geo.hip, geo.front_knee, lw)

    # Weapon + swing smear + weapon trail, then the front arm grips over it.
    weapon = get_weapon(char.id)
    # Update and draw the weapon-tip trail (active + early recover)
    rs.update_trail(char, geo, weapon, dt_ms=dt_ms)
    rs.draw_trail(surf, char, color, weapon)
    if weapon is not None:
        if (char.action_state == "attacking"
                and char.attack_phase == "strike"):
            pose_id = select_pose_id(char)
            ang_from = _swing_smear_start_angle(pose_id, char.facing)
            draw_swing_smear(surf, weapon, geo.front_hand,
                             ang_from, geo.weapon_deg, lw, color)
        draw_weapon(surf, weapon, geo.front_hand, geo.weapon_deg, lw,
                    color, char.accent_color, off_hand_xy=geo.back_hand)

    _draw_limb(surf, color, geo.shoulder, geo.front_elbow, geo.front_hand,
               lw, style["hand_radius"])


# ── VFX helpers (exported) ────────────────────────────────────────────────────

def spawn_impact_burst(surf: pygame.Surface, x: int, y: int,
                        color: Tuple[int, int, int], size: int = 20) -> None:
    """Draw a radial starburst at (x, y) — rays + a bright hot core.

    Ray count and stroke width scale with `size` so big hits (crits,
    ultimates) read as genuinely heavier than light jabs.
    """
    num_rays = 8 if size < 60 else 12
    ray_w = max(2, size // 16)
    # Long rays + shorter offset rays for a denser star
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays
        ex = int(x + math.cos(angle) * size)
        ey = int(y + math.sin(angle) * size)
        pygame.draw.line(surf, color, (x, y), (ex, ey), ray_w)
    for i in range(num_rays):
        angle = (2 * math.pi * i) / num_rays + math.pi / num_rays
        ex = int(x + math.cos(angle) * size * 0.55)
        ey = int(y + math.sin(angle) * size * 0.55)
        pygame.draw.line(surf, color, (x, y), (ex, ey), max(1, ray_w - 1))
    # Hot core — colored disc + white-hot center
    pygame.draw.circle(surf, color, (x, y), max(4, size // 4))
    pygame.draw.circle(surf, (255, 255, 255), (x, y), max(2, size // 8))


# Per-effect indicator colours.
_EFFECT_COLORS = {
    "root":     (150, 110, 60),    # shackle brown
    "slow":     (90, 140, 235),    # cold blue
    "shield":   (235, 225, 110),   # golden
    "tenacity": (210, 120, 220),   # violet
}

# Shield ring parameters.
_SHIELD_RING_RADIUS = 32          # px (unscaled figure units)
_SHIELD_RING_WIDTH = 3            # stroke width
_SHIELD_PULSE_PERIOD_MS = 600.0   # full sine cycle (ms)
_SHIELD_ALPHA_MIN = 80
_SHIELD_ALPHA_MAX = 180
_SHIELD_BLEND_WITH_WHITE = 0.5    # 0.0 = pure brand color, 1.0 = pure white


def _blend_with_white(color: tuple, t: float) -> tuple:
    """Blend `color` toward white by factor `t` ∈ [0, 1]."""
    return (
        int(color[0] + (255 - color[0]) * t),
        int(color[1] + (255 - color[1]) * t),
        int(color[2] + (255 - color[2]) * t),
    )


def _draw_shield_ring(surf: pygame.Surface, char, current_ms: float = 0.0) -> None:
    """Draw a translucent pulsing ring around `char` when it has a SHIELD effect.

    Ring is centered on the character's hip (torso center-of-mass proxy),
    with a sinusoidal alpha pulse over _SHIELD_PULSE_PERIOD_MS.
    """
    from pixel_battle.engine.effects import SHIELD as _SHIELD_KIND
    effects = getattr(char, "effects", None)
    shield_effect = next((e for e in (effects or []) if e.kind == _SHIELD_KIND), None)
    if shield_effect is None:
        return

    # Color: blend brand_color toward white.
    brand = getattr(char, "brand_color", getattr(char, "color", (235, 225, 110)))
    ring_color = _blend_with_white(brand, _SHIELD_BLEND_WITH_WHITE)

    # Pulse alpha sinusoidally.
    phase = (current_ms % _SHIELD_PULSE_PERIOD_MS) / _SHIELD_PULSE_PERIOD_MS
    pulse = (math.sin(phase * 2 * math.pi) + 1.0) / 2.0  # 0..1
    alpha = int(_SHIELD_ALPHA_MIN + (_SHIELD_ALPHA_MAX - _SHIELD_ALPHA_MIN) * pulse)

    cx = int(char.pos_x)
    # Hip is ~half torso-length above pos_y.  Use a fixed visual offset.
    cy = int(char.pos_y) - 60

    # Blit a small SRCALPHA surface so we get real transparency.
    r = _SHIELD_RING_RADIUS
    pad = _SHIELD_RING_WIDTH + 2
    d = (r + pad) * 2
    ring_surf = pygame.Surface((d, d), pygame.SRCALPHA)
    rc = (ring_color[0], ring_color[1], ring_color[2], alpha)
    if _HAS_GFXDRAW:
        _gfxdraw.aacircle(ring_surf, r + pad, r + pad, r, rc)
        # Fill with a second, thicker filled circle at lower alpha for the glow.
        glow_a = max(0, alpha // 3)
        gc = (ring_color[0], ring_color[1], ring_color[2], glow_a)
        _gfxdraw.filled_circle(ring_surf, r + pad, r + pad, r + 4, gc)
        _gfxdraw.aacircle(ring_surf, r + pad, r + pad, r, rc)
    else:
        pygame.draw.circle(ring_surf, rc, (r + pad, r + pad), r, _SHIELD_RING_WIDTH)
    surf.blit(ring_surf, (cx - r - pad, cy - r - pad))


def draw_effect_indicators(surf: pygame.Surface, char,
                            current_ms: float = 0.0) -> None:
    """Draw status effect indicators.

    SHIELD: dramatic pulsing glow ring around the torso.
    All other effects: small colored dot row above the head.
    """
    effects = getattr(char, "effects", None)
    if not effects:
        return

    from pixel_battle.engine.effects import SHIELD as _SHIELD_KIND
    _draw_shield_ring(surf, char, current_ms=current_ms)

    # Dot row for non-shield effects.
    non_shield = [e for e in effects if e.kind != _SHIELD_KIND]
    if not non_shield:
        return
    cx = int(char.pos_x)
    top_y = int(char.pos_y) - 210          # above the figure
    spacing = 16
    n = len(non_shield)
    start_x = cx - (n - 1) * spacing // 2
    for i, effect in enumerate(non_shield):
        color = _EFFECT_COLORS.get(effect.kind, (220, 220, 220))
        ex = start_x + i * spacing
        pygame.draw.circle(surf, color, (ex, top_y), 6)
        pygame.draw.circle(surf, (0, 0, 0), (ex, top_y), 6, 2)


def spawn_flash_puff(surf: pygame.Surface, x: int, ground_y: int, color) -> None:
    """A quick blink mark — a bright vertical streak plus a few outward
    sparks — drawn at a Flash origin or destination."""
    x, ground_y = int(x), int(ground_y)
    top = ground_y - 150
    # Vertical light streak.
    streak = pygame.Surface((10, 150), pygame.SRCALPHA)
    pygame.draw.line(streak, (color[0], color[1], color[2], 150),
                     (5, 0), (5, 150), 4)
    surf.blit(streak, (x - 5, top))
    # Outward spark dots.
    for dx, dy in ((-14, -40), (14, -40), (-10, -90), (10, -90)):
        pygame.draw.circle(surf, color, (x + dx, ground_y + dy), 3)


def spawn_landing_dust(surf: pygame.Surface, x: int, ground_y: int,
                        color: Tuple[int, int, int], intensity: float = 1.0) -> None:
    """Draw 4 small expanding ellipses near (x, ground_y) suggesting a dust puff.

    Used by episodes when a character transitions from on_ground=False -> True.
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


# ── Projectile layer (cooldown / ranged attacks) ──────────────────────────────

class ProjectileLayer:
    """Renders short-lived projectile particles for ranged attacks.

    Each projectile travels from start_xy to end_xy over duration_ms, rendered
    as a filled circle with a 3-segment fading tail. Stage 3 (play.py) spawns
    these on cooldown skill strike events.
    """

    def __init__(self):
        # Each item: (start_x, start_y, end_x, end_y, t0_ms, duration_ms, color)
        self._items = []

    def spawn(self, start, end, color, current_ms, duration_ms=350, kind="orb"):
        """Add a projectile traveling start->end over duration_ms. `kind` selects
        a per-weapon visual: orb(mage)/ice/rocket/bullet/bolt/kunai/fire."""
        self._items.append((
            int(start[0]), int(start[1]), int(end[0]), int(end[1]),
            int(current_ms), int(duration_ms), tuple(color), kind,
        ))

    def draw(self, surf, current_ms):
        """Render every live projectile (per `kind` visual) and cull expired ones."""
        live = []
        for item in self._items:
            sx, sy, ex, ey, t0, dur, color, kind = item
            t = (current_ms - t0) / dur
            if t >= 1.0:
                continue
            live.append(item)
            cx = sx + (ex - sx) * t
            cy = sy + (ey - sy) * t
            ang = math.atan2(ey - sy, ex - sx)
            if kind == "ice":
                self._draw_ice(surf, cx, cy, ang, sx, sy, ex, ey, t)
            elif kind == "rocket":
                self._draw_rocket(surf, cx, cy, ang, color, sx, sy, ex, ey, t)
            elif kind == "bullet":
                self._draw_bullet(surf, cx, cy, ang, color)
            elif kind == "bolt":
                self._draw_bolt(surf, cx, cy, ang, color)
            elif kind == "kunai":
                self._draw_kunai(surf, cx, cy, color, current_ms)
            elif kind == "fire":
                self._draw_fire(surf, cx, cy, sx, sy, ex, ey, t, current_ms)
            else:
                self._draw_orb(surf, cx, cy, color, sx, sy, ex, ey, t)
        self._items = live

    @staticmethod
    def _trail(surf, sx, sy, ex, ey, t, segs, add=True):
        for off, a, r, col in segs:
            tt = max(0.0, t - off)
            tx = sx + (ex - sx) * tt
            ty = sy + (ey - sy) * tt
            d = r * 2 + 2
            s = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(s, (*col, a), (d // 2, d // 2), r)
            surf.blit(s, (int(tx) - d // 2, int(ty) - d // 2),
                      special_flags=pygame.BLEND_RGB_ADD if add else 0)

    def _draw_orb(self, surf, cx, cy, color, sx, sy, ex, ey, t):       # mage light
        self._trail(surf, sx, sy, ex, ey, t,
                    [(0.05, 150, 16, color), (0.10, 120, 14, color), (0.15, 95, 12, color),
                     (0.20, 70, 10, color), (0.26, 48, 8, color), (0.32, 30, 6, color)])
        gr = 30
        glow = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        for rr, ga in ((gr, 45), (int(gr * 0.62), 80), (int(gr * 0.32), 140)):
            pygame.draw.circle(glow, (*color, ga), (gr, gr), rr)
        surf.blit(glow, (int(cx) - gr, int(cy) - gr), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(surf, color, (int(cx), int(cy)), 11)
        pygame.draw.circle(surf, (255, 255, 255), (int(cx), int(cy)), 6)

    def _draw_ice(self, surf, cx, cy, ang, sx, sy, ex, ey, t):          # frost arrow
        self._trail(surf, sx, sy, ex, ey, t,
                    [(0.08, 120, 4, (200, 240, 255)), (0.16, 80, 3, (200, 240, 255)),
                     (0.26, 50, 2, (200, 240, 255))])
        L, W = 15, 5
        p = ang + math.pi / 2
        tip = (cx + math.cos(ang) * L, cy + math.sin(ang) * L)
        back = (cx - math.cos(ang) * L * 0.7, cy - math.sin(ang) * L * 0.7)
        s1 = (cx + math.cos(p) * W, cy + math.sin(p) * W)
        s2 = (cx - math.cos(p) * W, cy - math.sin(p) * W)
        pts = [(int(tip[0]), int(tip[1])), (int(s1[0]), int(s1[1])),
               (int(back[0]), int(back[1])), (int(s2[0]), int(s2[1]))]
        pygame.draw.polygon(surf, (180, 235, 255), pts)
        pygame.draw.polygon(surf, (255, 255, 255), pts, 1)

    def _draw_rocket(self, surf, cx, cy, ang, color, sx, sy, ex, ey, t):  # explosive
        self._trail(surf, sx, sy, ex, ey, t,
                    [(0.10, 90, 6, (170, 170, 170)), (0.20, 58, 7, (160, 160, 160)),
                     (0.32, 34, 8, (150, 150, 150))], add=False)
        back = (cx - math.cos(ang) * 10, cy - math.sin(ang) * 10)
        fs = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(fs, (255, 180, 40, 200), (8, 8), 6)
        surf.blit(fs, (int(back[0]) - 8, int(back[1]) - 8), special_flags=pygame.BLEND_RGB_ADD)
        tip = (cx + math.cos(ang) * 9, cy + math.sin(ang) * 9)
        pygame.draw.line(surf, color, (int(back[0]), int(back[1])),
                         (int(tip[0]), int(tip[1])), 6)
        pygame.draw.circle(surf, (255, 235, 130), (int(tip[0]), int(tip[1])), 3)

    def _draw_bullet(self, surf, cx, cy, ang, color):                   # gun tracer
        bt = (cx - math.cos(ang) * 24, cy - math.sin(ang) * 24)
        s = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.line(s, (*color, 150), (int(bt[0]), int(bt[1])), (int(cx), int(cy)), 2)
        surf.blit(s, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(surf, (255, 255, 225), (int(cx), int(cy)), 3)
        pygame.draw.circle(surf, color, (int(cx), int(cy)), 2)

    def _draw_bolt(self, surf, cx, cy, ang, color):                     # crossbow bolt
        L = 16
        p = ang + math.pi / 2
        tip = (cx + math.cos(ang) * L, cy + math.sin(ang) * L)
        back = (cx - math.cos(ang) * L, cy - math.sin(ang) * L)
        pygame.draw.line(surf, color, (int(back[0]), int(back[1])),
                         (int(tip[0]), int(tip[1])), 3)
        h1 = (tip[0] - math.cos(ang) * 6 + math.cos(p) * 4, tip[1] - math.sin(ang) * 6 + math.sin(p) * 4)
        h2 = (tip[0] - math.cos(ang) * 6 - math.cos(p) * 4, tip[1] - math.sin(ang) * 6 - math.sin(p) * 4)
        pygame.draw.polygon(surf, (235, 235, 235),
                            [(int(tip[0]), int(tip[1])), (int(h1[0]), int(h1[1])), (int(h2[0]), int(h2[1]))])
        for s in (1, -1):
            fl = (back[0] + math.cos(p) * 4 * s, back[1] + math.sin(p) * 4 * s)
            pygame.draw.line(surf, (210, 130, 80), (int(back[0]), int(back[1])),
                             (int(fl[0]), int(fl[1])), 2)

    def _draw_kunai(self, surf, cx, cy, color, current_ms):             # spinning blade
        rot = (current_ms / 38.0) % (2 * math.pi)
        for k in range(2):
            a = rot + k * math.pi
            p = a + math.pi / 2
            tip = (cx + math.cos(a) * 9, cy + math.sin(a) * 9)
            b1 = (cx + math.cos(p) * 3, cy + math.sin(p) * 3)
            b2 = (cx - math.cos(p) * 3, cy - math.sin(p) * 3)
            pygame.draw.polygon(surf, color,
                                [(int(tip[0]), int(tip[1])), (int(b1[0]), int(b1[1])), (int(b2[0]), int(b2[1]))])
        pygame.draw.circle(surf, (30, 50, 25), (int(cx), int(cy)), 2)

    def _draw_fire(self, surf, cx, cy, sx, sy, ex, ey, t, current_ms):  # fireball
        self._trail(surf, sx, sy, ex, ey, t,
                    [(0.08, 130, 5, (255, 110, 30)), (0.16, 85, 4, (255, 90, 20)),
                     (0.26, 50, 3, (220, 70, 15))])
        jit = int((current_ms // 50) % 3) - 1
        g = pygame.Surface((24, 24), pygame.SRCALPHA)
        pygame.draw.circle(g, (255, 140, 40, 150), (12, 12), 10)
        pygame.draw.circle(g, (255, 210, 120, 200), (12, 12), 6)
        surf.blit(g, (int(cx) - 12 + jit, int(cy) - 12), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.circle(surf, (255, 245, 200), (int(cx), int(cy)), 3)
