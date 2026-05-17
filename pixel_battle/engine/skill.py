"""Skill data model. Skills are pure data loaded from characters.json."""
from dataclasses import dataclass, field
from enum import Enum


class SkillType(Enum):
    BASIC = "basic"
    SPECIAL = "special"
    ULTIMATE = "ultimate"


@dataclass
class Skill:
    id: str
    skill_type: SkillType
    anim: str
    mp_cost: int = 0
    dmg: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "Skill":
        try:
            skill_type = SkillType(d["type"])
        except ValueError as e:
            raise ValueError(f"Unknown skill type: {d['type']}") from e
        return cls(
            id=d["id"],
            skill_type=skill_type,
            anim=d["anim"],
            mp_cost=d.get("mp_cost", 0),
            dmg=d.get("dmg", 0),
        )
