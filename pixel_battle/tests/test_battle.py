import pytest
from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def make_battle(seed=42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    return Battle(left=a, right=b, rng=BattleRNG(seed))


def test_initial_state_is_starting():
    b = make_battle()
    assert b.state is BattleState.STARTING
    assert b.left.hp == 100
    assert b.right.hp == 100


def test_battle_starts_after_intro():
    b = make_battle()
    b.tick_ms(2500)
    assert b.state is BattleState.FIGHTING


def test_first_attack_logs_event():
    b = make_battle(seed=42)
    for _ in range(300):
        b.tick_ms(16)
        if any(e.type is EventType.HIT or e.type is EventType.MISS for e in b.events):
            break
    attack_events = [e for e in b.events if e.type in (EventType.HIT, EventType.MISS)]
    assert len(attack_events) > 0


def test_damage_reduces_hp():
    b = make_battle(seed=42)
    starting_hp = b.right.hp
    for _ in range(2000):
        b.tick_ms(16)
        if b.right.hp < starting_hp:
            break
    assert b.right.hp < starting_hp


def test_ko_ends_battle():
    b = make_battle(seed=42)
    b.right.take_damage(100)
    b.tick_ms(50)
    assert b.state is BattleState.KO
    assert any(e.type is EventType.KO for e in b.events)


def test_same_seed_same_outcome():
    b1 = make_battle(seed=99)
    b2 = make_battle(seed=99)
    for _ in range(500):
        b1.tick_ms(16)
        b2.tick_ms(16)
    assert b1.left.hp == b2.left.hp
    assert b1.right.hp == b2.right.hp
    assert len(b1.events) == len(b2.events)
