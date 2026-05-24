"""Verify that pre-setting `pending_cast_skill_id` on a character makes
`_start_attack_with_kind` select that specific skill rather than
`affordable[0]` / `first off-cd`."""
from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.rng import BattleRNG


def _new_battle():
    # Lux has two special skills: lucent_singularity (mp_cost=26) and
    # prismatic_barrier (mp_cost=20). Engine default = first affordable
    # (lucent_singularity if MP >= 26; otherwise prismatic_barrier).
    # We will test: setting pending_cast_skill_id = "prismatic_barrier"
    # makes the engine pick prismatic_barrier even when lucent_singularity
    # is also affordable (i.e. we give Lux full MP).
    lux = Character.load("lux")
    garen = Character.load("garen")
    b = Battle(lux, garen, rng=BattleRNG(seed=0))
    # advance past STARTING and clear last_attack guard
    b.elapsed_ms = 5000
    lux.last_attack_ms = -10000
    lux.mp = 100   # enough for both specials
    return b, lux, garen


def test_pending_cast_overrides_affordable_first():
    b, lux, garen = _new_battle()
    # Default behaviour: pick first affordable special (lucent_singularity).
    b._start_attack_with_kind(lux, garen, "special")
    assert lux.attack_used_kind is not None
    assert lux.attack_used_kind.id == "lucent_singularity"


def test_pending_cast_picks_named_skill():
    b, lux, garen = _new_battle()
    # Reset to attack-ready
    lux.attack_used_kind = None
    lux.action_state = "idle"
    lux.attack_phase = "none"
    lux.last_attack_ms = -10000
    # Pre-set the named skill the driver wants
    lux.pending_cast_skill_id = "prismatic_barrier"
    b._start_attack_with_kind(lux, garen, "special")
    assert lux.attack_used_kind is not None
    assert lux.attack_used_kind.id == "prismatic_barrier"
    # Field is consumed (cleared) after the attack starts
    assert lux.pending_cast_skill_id is None


def test_pending_cast_unknown_id_noop():
    b, lux, garen = _new_battle()
    lux.attack_used_kind = None
    lux.action_state = "idle"
    lux.attack_phase = "none"
    lux.last_attack_ms = -10000
    lux.pending_cast_skill_id = "no_such_skill_xyz"
    b._start_attack_with_kind(lux, garen, "special")
    # Named skill not in the special list → no-op (do NOT silently fall back to affordable[0])
    assert lux.action_state == "idle"
    assert lux.attack_used_kind is None
    # Field is consumed even on no-op so a stale id can't fire next tick
    assert lux.pending_cast_skill_id is None
