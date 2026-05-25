# pixel_battle/tests/test_combat_reactions.py
"""Tests for block / crouch defensive mechanics and new pose verbs."""
from __future__ import annotations
import types

import pytest

from pixel_battle.engine.battle import (
    Battle, BattleState,
    BLOCK_DURATION_MS, CROUCH_DURATION_MS, BLOCK_DMG_MULT, STAGGER_MS,
)
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.script.loader import DO_VERBS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _env(left_id="garen", right_id="lux", seed=99):
    env = PixelBattleEnv(seed=seed, left_id=left_id, right_id=right_id)
    env.reset()
    # Step past intro
    for _ in range(200):
        env.step((0, 0))
    return env


def _place_melee(env):
    """Put both characters just inside melee range."""
    env.left.pos_x = 200
    env.right.pos_x = 260
    env.left.last_attack_ms = -99999
    env.right.last_attack_ms = -99999


# ── Loader / verb registration ────────────────────────────────────────────────

def test_block_verb_registered():
    assert "block" in DO_VERBS
    assert DO_VERBS["block"] == 11


def test_crouch_verb_registered():
    assert "crouch" in DO_VERBS
    assert DO_VERBS["crouch"] == 12


# ── Engine: block reduces damage ─────────────────────────────────────────────

def test_block_reduces_damage():
    """A blocking character takes at most BLOCK_DMG_MULT × base damage."""
    env = _env()
    _place_melee(env)

    # Measure raw damage without block: hit right repeatedly and record max.
    raw_damages = []
    for _ in range(20):
        env2 = _env()
        _place_melee(env2)
        hp_before = env2.right.hp
        env2.step((4, 0))   # left basic attack; right idle
        # Advance until attack resolves
        for _ in range(30):
            env2.step((0, 0))
            if env2.right.hp < hp_before:
                break
        dmg = hp_before - env2.right.hp
        if dmg > 0:
            raw_damages.append(dmg)

    if not raw_damages:
        pytest.skip("No hits landed in raw damage measurement")
    max_raw = max(raw_damages)

    # Now measure with block: right blocks while left attacks.
    env3 = _env()
    _place_melee(env3)
    hp_before = env3.right.hp
    # Right enters block immediately before being hit
    env3.step((4, 11))   # left basic attack + right block simultaneously
    for _ in range(30):
        env3.step((0, 0))
        if env3.right.hp < hp_before:
            break
    blocked_dmg = hp_before - env3.right.hp

    # Blocked damage must be ≤ BLOCK_DMG_MULT × max observed raw damage (+ 1 for int rounding)
    # Allow tolerance: blocked_dmg may be 0 if attack missed or 1 (min after block)
    assert blocked_dmg <= max(1, int(max_raw * BLOCK_DMG_MULT) + 1), (
        f"Blocked damage {blocked_dmg} exceeds expected ceiling "
        f"{int(max_raw * BLOCK_DMG_MULT)+1} (max raw={max_raw})"
    )


def test_block_expires_after_duration():
    """After BLOCK_DURATION_MS the character's action_state returns to idle."""
    env = _env()
    env.step((11, 0))   # left enters block
    assert env.left.action_state == "blocking"

    # Advance time past BLOCK_DURATION_MS
    ticks_needed = (BLOCK_DURATION_MS // 16) + 10
    for _ in range(ticks_needed):
        env.step((0, 0))
        if env.left.action_state != "blocking":
            break

    assert env.left.action_state != "blocking", (
        f"Block did not expire: action_state={env.left.action_state!r}")


# ── Engine: crouch dodges projectiles ────────────────────────────────────────

def _make_skill_stub(vfx: str):
    s = types.SimpleNamespace(
        vfx=vfx, id=f"stub_{vfx}", effective_range=500,
        skill_type=None, stagger_ms=0, dmg=0, mp_cost=0,
        applies=None, cooldown_ms=0, anim="",
    )
    return s


def _battle_with_blocking_defender(defender_state: str, attacker_vfx: str):
    """Set up a Battle where defender is in `defender_state` and attacker fires
    a skill with `attacker_vfx`.  Returns (battle, attacker, defender)."""
    left = Character.load("garen")
    right = Character.load("lux")
    rng = BattleRNG(seed=1)
    battle = Battle(left=left, right=right, rng=rng)
    # Skip intro
    while battle.state == BattleState.STARTING:
        battle.tick_ms(16, skip_ai=True)

    # Place in range
    left.pos_x = 200.0
    right.pos_x = 260.0

    # Put defender (right) in desired state
    right.action_state = defender_state
    right.crouch_end_ms = battle.elapsed_ms + 9999
    right.block_end_ms = battle.elapsed_ms + 9999

    # Attacker (left) fires bolt skill
    skill_stub = _make_skill_stub(attacker_vfx)
    from pixel_battle.engine.skill import SkillType
    skill_stub.skill_type = SkillType.COOLDOWN
    left.attack_used_kind = skill_stub
    left.action_state = "attacking"
    left.attack_phase = "windup"
    left.attack_phase_t = 9999   # bypass windup immediately

    return battle, left, right


def test_crouch_dodges_projectile():
    """Crouching defender evades bolt/multishot/beam skills — MISS emitted."""
    for vfx in ("bolt", "multishot", "beam"):
        battle, attacker, defender = _battle_with_blocking_defender("crouching", vfx)
        hp_before = defender.hp
        battle._resolve_attack_hit(attacker, defender)
        assert defender.hp == hp_before, (
            f"Crouch should have dodged vfx={vfx!r} but defender took damage")
        # A MISS event with reason "crouched_under" must exist
        from pixel_battle.engine.battle import EventType
        miss_events = [e for e in battle.events
                       if e.type == EventType.MISS
                       and e.extra.get("reason") == "crouched_under"]
        assert miss_events, f"No crouched_under MISS event for vfx={vfx!r}"


def test_crouch_does_not_dodge_melee():
    """Crouching defender is still hit by melee/dash skills."""
    for vfx in ("melee", "dash"):
        battle, attacker, defender = _battle_with_blocking_defender("crouching", vfx)
        hp_before = defender.hp
        battle._resolve_attack_hit(attacker, defender)
        # Damage must have landed (melee ignores crouch)
        assert defender.hp < hp_before, (
            f"Crouching should NOT dodge vfx={vfx!r} but no damage was taken")


# ── Poses: existence check ────────────────────────────────────────────────────

def test_hit_react_pose_exists():
    from pixel_battle.rl.poses import HIT_REACT_POSE, FigurePose
    assert isinstance(HIT_REACT_POSE, FigurePose)


def test_block_pose_exists():
    from pixel_battle.rl.poses import BLOCK_POSE, FigurePose
    assert isinstance(BLOCK_POSE, FigurePose)


def test_crouch_pose_exists():
    from pixel_battle.rl.poses import CROUCH_POSE, FigurePose
    assert isinstance(CROUCH_POSE, FigurePose)


# ── Pose routing: select_pose_id dispatches new states ───────────────────────

def test_select_pose_id_hit_stagger_routes_hit_react():
    from pixel_battle.rl.poses import select_pose_id
    c = Character.load("garen")
    c.action_state = "hit_stagger"
    c.on_ground = True
    assert select_pose_id(c) == "hit_react"


def test_select_pose_id_blocking_routes_block():
    from pixel_battle.rl.poses import select_pose_id
    c = Character.load("garen")
    c.action_state = "blocking"
    c.on_ground = True
    assert select_pose_id(c) == "block"


def test_select_pose_id_crouching_routes_crouch():
    from pixel_battle.rl.poses import select_pose_id
    c = Character.load("garen")
    c.action_state = "crouching"
    c.on_ground = True
    assert select_pose_id(c) == "crouch"
