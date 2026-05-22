"""Skill data model. Skills are pure data loaded from characters.json."""
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pixel_battle.engine.effects import SkillApplies


class SkillType(Enum):
    BASIC = "basic"
    COOLDOWN = "cooldown"
    SPECIAL = "special"
    ULTIMATE = "ultimate"


@dataclass
class Skill:
    id: str
    skill_type: SkillType
    anim: str
    mp_cost: int = 0
    dmg: int = 0
    cooldown_ms: int = 0
    range: str = "melee"        # "melee" | "special"
    stagger_ms: int = 0          # 0 = use engine default STAGGER_MS
    vfx: str = "melee"           # visual archetype the renderer draws:
                                 # melee/bolt/multishot/aura/dash/spin/slam/beam
    applies: Optional[SkillApplies] = None

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
            cooldown_ms=d.get("cooldown_ms", 0),
            range=d.get("range", "melee"),
            stagger_ms=d.get("stagger_ms", 0),
            vfx=d.get("vfx", "melee"),
            applies=(SkillApplies.from_dict(d["applies"])
                     if d.get("applies") else None),
        )
