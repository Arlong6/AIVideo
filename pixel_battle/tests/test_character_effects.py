"""Character status-effect storage + shield-routed damage."""
from pixel_battle.engine.character import Character
from pixel_battle.engine.effects import StatusEffect, ROOT, SHIELD


def test_new_character_has_no_effects():
    c = Character.load("garen")
    assert c.effects == []


def test_effect_of_and_has_effect():
    c = Character.load("garen")
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=1000))
    assert c.has_effect(ROOT) is True
    assert c.effect_of(ROOT).remaining_ms == 1000
    assert c.has_effect(SHIELD) is False
    assert c.effect_of(SHIELD) is None


def test_shield_absorbs_damage_before_hp():
    c = Character.load("garen")
    c.hp = 100
    c.effects.append(StatusEffect(kind=SHIELD, remaining_ms=5000, magnitude=20))
    c.take_damage(8)
    assert c.hp == 100                       # fully absorbed
    assert c.effect_of(SHIELD).magnitude == 12


def test_shield_overflow_spills_to_hp_and_shield_drops():
    c = Character.load("garen")
    c.hp = 100
    c.effects.append(StatusEffect(kind=SHIELD, remaining_ms=5000, magnitude=5))
    c.take_damage(12)
    assert c.hp == 93                        # 5 absorbed, 7 to HP
    assert c.has_effect(SHIELD) is False     # depleted shield removed


def test_reset_physics_clears_effects():
    c = Character.load("garen")
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=1000))
    c.reset_physics(initial_x=100.0, facing=1)
    assert c.effects == []
