"""Per-skill numeric attack range."""
from pixel_battle.engine.skill import Skill, SkillType
from pixel_battle.engine.physics import MELEE_RANGE, SPECIAL_RANGE


def test_effective_range_numeric():
    s = Skill.from_dict({"id": "x", "type": "cooldown", "anim": "a",
                         "range": 280})
    assert s.effective_range == 280


def test_effective_range_string_special():
    s = Skill.from_dict({"id": "x", "type": "cooldown", "anim": "a",
                         "range": "special"})
    assert s.effective_range == SPECIAL_RANGE


def test_effective_range_special_type_defaults_to_special():
    # A SPECIAL-type skill with no explicit range still reaches SPECIAL_RANGE.
    s = Skill.from_dict({"id": "x", "type": "special", "anim": "a"})
    assert s.effective_range == SPECIAL_RANGE


def test_effective_range_basic_defaults_to_melee():
    s = Skill.from_dict({"id": "x", "type": "basic", "anim": "a"})
    assert s.effective_range == MELEE_RANGE
