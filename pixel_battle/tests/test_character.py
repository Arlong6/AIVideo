import pytest
from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType


def test_load_brick_phone():
    c = Character.load("brick_phone")
    assert c.id == "brick_phone"
    assert c.display_name == "Brick Phone"
    assert c.hp == 100
    assert c.mp == 0
    assert c.mp_max == 100
    assert len(c.skills) == 4


def test_load_glass_slab():
    c = Character.load("glass_slab")
    assert c.display_name == "Glass Slab"
    assert c.accuracy == 0.75


def test_skills_by_type():
    c = Character.load("brick_phone")
    basics = c.skills_of_type(SkillType.BASIC)
    ults = c.skills_of_type(SkillType.ULTIMATE)
    assert len(basics) == 1
    assert basics[0].id == "headbutt"
    assert len(ults) == 1
    assert ults[0].id == "indestructible_throw"


def test_take_damage_clamps_to_zero():
    c = Character.load("brick_phone")
    c.take_damage(150)
    assert c.hp == 0
    assert c.is_ko()


def test_gain_mp_clamps_to_max():
    c = Character.load("brick_phone")
    c.gain_mp(200)
    assert c.mp == 100
    assert c.ultimate_ready()


def test_spend_mp():
    c = Character.load("brick_phone")
    c.gain_mp(50)
    c.spend_mp(30)
    assert c.mp == 20


def test_unknown_character_raises():
    with pytest.raises(KeyError):
        Character.load("godzilla")
