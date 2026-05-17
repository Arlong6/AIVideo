"""Character runtime state + loader.

Characters are pure data in data/characters.json. This class wraps that data
with mutable runtime state (hp, mp, current state).
"""
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pixel_battle.engine.skill import Skill, SkillType

HP_MAX = 100
MP_MAX = 100
DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "characters.json"


@dataclass
class Character:
    id: str
    display_name: str
    color: tuple
    accent_color: tuple
    attack_interval_ms: int
    accuracy: float
    damage_range: tuple
    skills: List[Skill]
    hp: int = HP_MAX
    mp: int = 0
    mp_max: int = MP_MAX
    last_attack_ms: int = -10000

    @classmethod
    def load(cls, char_id: str) -> "Character":
        with open(DATA_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if char_id not in data:
            raise KeyError(f"Unknown character: {char_id}")
        d = data[char_id]
        return cls(
            id=char_id,
            display_name=d["display_name"],
            color=tuple(d["color"]),
            accent_color=tuple(d["accent_color"]),
            attack_interval_ms=d["attack_interval_ms"],
            accuracy=d["accuracy"],
            damage_range=tuple(d["damage"]),
            skills=[Skill.from_dict(s) for s in d["skills"]],
        )

    def skills_of_type(self, t: SkillType) -> List[Skill]:
        return [s for s in self.skills if s.skill_type is t]

    def take_damage(self, amount: int) -> None:
        self.hp = max(0, self.hp - amount)

    def gain_mp(self, amount: int) -> None:
        self.mp = min(self.mp_max, self.mp + amount)

    def spend_mp(self, amount: int) -> None:
        self.mp = max(0, self.mp - amount)

    def is_ko(self) -> bool:
        return self.hp <= 0

    def ultimate_ready(self) -> bool:
        return self.mp >= self.mp_max
