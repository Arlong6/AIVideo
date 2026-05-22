# pixel_battle/script/loader.py
"""Load + validate a YAML fight script into a FightScript."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List
import json

import yaml

from pixel_battle.engine.character import DATA_PATH
from pixel_battle.script.conditions import (
    compile_condition, ConditionError, Predicate,
)

# `do` verbs the driver understands → engine action integers.
DO_VERBS = {
    "idle": 0, "retreat": 1, "advance": 2, "jump": 3,
    "attack:basic": 4, "attack:cd": 5, "attack:ultimate": 6,
    "attack:special": 7, "attack:kick": 8,
}


class ScriptError(ValueError):
    """Raised when a fight script is malformed."""


@dataclass
class Intent:
    do: str            # a key of DO_VERBS
    until: Predicate   # compiled condition
    until_src: str     # the raw condition string (for debugging)


@dataclass
class FightScript:
    name: str
    left: str          # left character id
    right: str         # right character id
    left_intents: List[Intent]
    right_intents: List[Intent]


def _known_character_ids() -> set:
    with open(DATA_PATH, encoding="utf-8") as f:
        return set(json.load(f).keys())


def _parse_intents(raw, side: str) -> List[Intent]:
    if not isinstance(raw, list) or not raw:
        raise ScriptError(f"{side}_script must be a non-empty list")
    intents = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or "do" not in item or "until" not in item:
            raise ScriptError(f"{side}_script[{i}] needs 'do' and 'until'")
        do = str(item["do"])
        if do not in DO_VERBS:
            raise ScriptError(f"{side}_script[{i}]: unknown do verb {do!r}")
        until_src = str(item["until"])
        try:
            until = compile_condition(until_src)
        except ConditionError as e:
            raise ScriptError(f"{side}_script[{i}]: {e}") from e
        intents.append(Intent(do=do, until=until, until_src=until_src))
    return intents


def load_script_text(text: str) -> FightScript:
    """Parse + validate a fight script from YAML text."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ScriptError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise ScriptError("script must be a YAML mapping")
    for key in ("name", "left", "right", "left_script", "right_script"):
        if key not in data:
            raise ScriptError(f"script missing required key: {key!r}")

    known = _known_character_ids()
    for side in ("left", "right"):
        if data[side] not in known:
            raise ScriptError(f"unknown character id: {data[side]!r}")

    return FightScript(
        name=str(data["name"]),
        left=str(data["left"]), right=str(data["right"]),
        left_intents=_parse_intents(data["left_script"], "left"),
        right_intents=_parse_intents(data["right_script"], "right"),
    )


def load_script(path) -> FightScript:
    """Load + validate a fight script from a YAML file."""
    return load_script_text(Path(path).read_text(encoding="utf-8"))
