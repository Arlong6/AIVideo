# pixel_battle/script/conditions.py
"""Compile a script `until` string into a predicate over a ConditionContext."""
from __future__ import annotations
import operator
from dataclasses import dataclass
from typing import Callable

from pixel_battle.engine.effects import EFFECT_KINDS


class ConditionError(ValueError):
    """Raised when an `until` condition string cannot be compiled."""


@dataclass
class ConditionContext:
    """Everything a condition can read about the current tick."""
    dist: float                  # horizontal distance between the fighters
    intent_elapsed_ms: int       # ms elapsed inside the active intent
    char: object                 # the scripted Character
    opponent: object             # the other Character
    attacked_this_intent: bool   # did `char` start an attack during this intent


_CMP = {">=": operator.ge, "<=": operator.le}
Predicate = Callable[[ConditionContext], bool]


def compile_condition(src: str) -> Predicate:
    """Compile an `until` string (e.g. 'dist>=230') into a predicate."""
    s = src.strip()

    if s == "skill_done":
        return lambda c: c.attacked_this_intent and \
            c.char.action_state != "attacking"

    if s.startswith("target_has:"):
        effect = s.split(":", 1)[1].strip()
        if effect not in EFFECT_KINDS:
            raise ConditionError(f"unknown effect in condition: {src!r}")
        return lambda c: c.opponent.has_effect(effect)

    for op_s, op_f in _CMP.items():
        if op_s in s:
            field, _, num = s.partition(op_s)
            field = field.strip()
            try:
                n = float(num.strip())
            except ValueError:
                raise ConditionError(f"bad number in condition: {src!r}")
            if field == "dist":
                return lambda c, n=n, f=op_f: f(c.dist, n)
            if field == "time":
                return lambda c, n=n, f=op_f: f(c.intent_elapsed_ms, n)
            if field == "hp":
                return lambda c, n=n, f=op_f: f(c.char.hp, n)
            if field == "target_hp":
                return lambda c, n=n, f=op_f: f(c.opponent.hp, n)
            raise ConditionError(f"unknown field {field!r} in condition: {src!r}")

    raise ConditionError(f"unparseable condition: {src!r}")
