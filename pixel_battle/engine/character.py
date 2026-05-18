"""Character runtime state + loader.

Characters are pure data in data/characters.json. This class wraps that data
with mutable runtime state (hp, mp, current state).
"""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

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
    # Physics fields — safe defaults so existing tests don't break before reset_physics is called
    pos_x: float = 0.0
    pos_y: float = 0.0
    vel_x: float = 0.0
    vel_y: float = 0.0
    on_ground: bool = True
    facing: int = 1
    action_state: str = "idle"
    attack_phase: str = "none"
    attack_phase_t: int = 0
    attack_used_kind: object = None
    skill_cd_ready_at: Dict[str, int] = field(default_factory=dict)
    retreat_until_ms: int = 0
    windup_stun_until_ms: int = 0

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

    def reset_physics(self, initial_x: float, facing: int) -> None:
        """Reset to battle-start state. Called by Battle on init."""
        from pixel_battle.engine.physics import GROUND_Y
        self.pos_x = initial_x
        self.pos_y = GROUND_Y
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.on_ground = True
        self.facing = facing   # 1 = facing right, -1 = facing left
        self.action_state = "idle"
        self.attack_phase = "none"
        self.attack_phase_t = 0
        self.attack_used_kind = None
        self.last_attack_ms = -10000
        self.skill_cd_ready_at = {}
        self.retreat_until_ms = 0
        self.windup_stun_until_ms = 0
        self.hp = HP_MAX
        self.mp = 0

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

    def skill_off_cooldown(self, skill: Skill, now_ms: int) -> bool:
        return self.skill_cd_ready_at.get(skill.id, 0) <= now_ms
