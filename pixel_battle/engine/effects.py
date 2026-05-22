"""Status effects — root, slow, shield, tenacity."""
from __future__ import annotations
from dataclasses import dataclass

ROOT = "root"
SLOW = "slow"
SHIELD = "shield"
TENACITY = "tenacity"
EFFECT_KINDS = frozenset({ROOT, SLOW, SHIELD, TENACITY})

_TARGETS = frozenset({"self", "opponent"})


@dataclass
class StatusEffect:
    """A live effect on a character. `magnitude`: slow/tenacity = factor in
    (0, 1); shield = remaining damage pool; root = unused (1.0)."""
    kind: str
    remaining_ms: int
    magnitude: float = 1.0

    def is_expired(self) -> bool:
        return self.remaining_ms <= 0


@dataclass
class SkillApplies:
    """Data-driven status effect a skill attaches when it lands / is cast."""
    effect: str
    duration_ms: int
    magnitude: float
    target: str        # "self" | "opponent"

    @classmethod
    def from_dict(cls, d: dict) -> "SkillApplies":
        effect = d["effect"]
        if effect not in EFFECT_KINDS:
            raise ValueError(f"Unknown status effect: {effect!r}")
        target = d.get("target", "opponent")
        if target not in _TARGETS:
            raise ValueError(f"Unknown applies target: {target!r}")
        return cls(effect=effect, duration_ms=int(d["duration_ms"]),
                   magnitude=float(d.get("magnitude", 1.0)), target=target)
