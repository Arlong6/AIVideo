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


def test_cooldown_skill_type():
    s = Skill.from_dict({
        "id": "screw_dart", "type": "cooldown", "anim": "screw_dart",
        "cooldown_ms": 4000, "dmg": 5, "range": "special",
    })
    assert s.skill_type is SkillType.COOLDOWN
    assert s.cooldown_ms == 4000
    assert s.range == "special"
    assert s.stagger_ms == 0
    assert s.mp_cost == 0


def test_skill_defaults_for_new_fields():
    """Existing skill dicts without new fields still load with defaults."""
    s = Skill.from_dict({"id": "headbutt", "type": "basic", "anim": "attack"})
    assert s.cooldown_ms == 0
    assert s.range == "melee"
    assert s.stagger_ms == 0


def test_skill_stagger_ms():
    s = Skill.from_dict({
        "id": "shard_scatter", "type": "cooldown", "anim": "shard_scatter",
        "cooldown_ms": 4000, "dmg": 4, "range": "special", "stagger_ms": 500,
    })
    assert s.stagger_ms == 500
