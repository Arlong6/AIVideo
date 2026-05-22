"""Skill.applies — data-driven status-effect attachment."""
from pixel_battle.engine.effects import SkillApplies, ROOT, SHIELD, EFFECT_KINDS
from pixel_battle.engine.skill import Skill


def test_skill_without_applies_is_none():
    s = Skill.from_dict({"id": "x", "type": "basic", "anim": "attack"})
    assert s.applies is None


def test_skill_with_applies_parses_into_skillapplies():
    s = Skill.from_dict({
        "id": "light_binding", "type": "cooldown", "anim": "light_binding",
        "applies": {"effect": "root", "duration_ms": 1500,
                    "magnitude": 1.0, "target": "opponent"},
    })
    assert isinstance(s.applies, SkillApplies)
    assert s.applies.effect == ROOT
    assert s.applies.duration_ms == 1500
    assert s.applies.target == "opponent"


def test_applies_rejects_unknown_effect():
    import pytest
    with pytest.raises(ValueError):
        Skill.from_dict({"id": "x", "type": "basic", "anim": "attack",
                         "applies": {"effect": "nonsense", "duration_ms": 100,
                                     "magnitude": 1.0, "target": "self"}})


def test_effect_kinds_constant():
    assert EFFECT_KINDS == frozenset({"root", "slow", "shield", "tenacity"})
