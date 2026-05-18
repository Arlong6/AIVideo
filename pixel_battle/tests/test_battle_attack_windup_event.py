"""ATTACK_WINDUP event is emitted at the start of CD-skill / Special attacks.
Episode runner uses this to spawn the ChargeFX (sparkles converging on attacker).
"""
from pixel_battle.engine.battle import Battle, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _setup():
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(2500)  # past intro
    a.pos_x = 200
    b.pos_x = 280  # in melee range
    return bat, a, b


def test_cd_skill_attack_emits_windup_event():
    """When _start_attack picks a COOLDOWN skill, ATTACK_WINDUP event fires."""
    bat, a, b = _setup()
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    a.attack_used_kind = cd_skill
    a.action_state = "idle"
    prev_count = len(bat.events)
    a.mp = 0
    bat._start_attack(a, b)
    new_events = [e for e in bat.events[prev_count:]]
    windup_events = [e for e in new_events if e.type is EventType.ATTACK_WINDUP]
    if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
        assert len(windup_events) == 1
        ev = windup_events[0]
        assert ev.actor == a.id
        assert ev.extra.get("skill_id") == cd_skill.id
        assert ev.extra.get("skill_type") == "cooldown"


def test_basic_attack_does_not_emit_windup_event():
    """When _start_attack picks a BASIC skill, no ATTACK_WINDUP event fires."""
    bat, a, b = _setup()
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.mp = 0
    prev_count = len(bat.events)
    bat._start_attack(a, b)
    new_events = bat.events[prev_count:]
    windup_events = [e for e in new_events if e.type is EventType.ATTACK_WINDUP]
    assert windup_events == []


def test_special_attack_emits_windup_event():
    """When _start_attack picks a SPECIAL skill, ATTACK_WINDUP event fires."""
    bat, a, b = _setup()
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.mp = 100
    prev_count = len(bat.events)
    found_special = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.last_attack_ms = -10000
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.SPECIAL:
            found_special = True
            break
    assert found_special, "Couldn't get AI to pick a SPECIAL across 30 rolls"
    windup_events = [e for e in bat.events[prev_count:] if e.type is EventType.ATTACK_WINDUP]
    assert len(windup_events) >= 1
    last = windup_events[-1]
    assert last.extra.get("skill_type") == "special"
