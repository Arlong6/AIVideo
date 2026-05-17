import pytest
from pixel_battle.engine.skill import Skill, SkillType


def test_basic_skill_from_dict():
    s = Skill.from_dict({
        "id": "headbutt",
        "type": "basic",
        "anim": "attack",
    })
    assert s.id == "headbutt"
    assert s.skill_type is SkillType.BASIC
    assert s.mp_cost == 0
    assert s.anim == "attack"


def test_special_skill_requires_mp_cost():
    s = Skill.from_dict({
        "id": "snake_strike",
        "type": "special",
        "mp_cost": 30,
        "dmg": 15,
        "anim": "snake",
    })
    assert s.skill_type is SkillType.SPECIAL
    assert s.mp_cost == 30
    assert s.dmg == 15


def test_ultimate_skill():
    s = Skill.from_dict({
        "id": "indestructible_throw",
        "type": "ultimate",
        "mp_cost": 100,
        "dmg": 40,
        "anim": "throw_cinematic",
    })
    assert s.skill_type is SkillType.ULTIMATE
    assert s.mp_cost == 100


def test_unknown_skill_type_raises():
    with pytest.raises(ValueError):
        Skill.from_dict({"id": "x", "type": "nonsense", "anim": "a"})
