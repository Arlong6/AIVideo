# pixel_battle/script/timeline_loader.py
"""Parse + validate a timeline-format fight YAML into a `Timeline`."""
from __future__ import annotations
import json
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from pixel_battle.engine.character import DATA_PATH
from pixel_battle.engine.skill import SkillType
from pixel_battle.script.loader import DO_VERBS    # 11 do-verbs → action ints
from pixel_battle.script.timeline_format import Timeline, TimelineEvent


# `cast:<skill_id>` routes to the same action int as the skill's `attack:<kind>`.
_SKILL_TYPE_TO_ACTION = {
    SkillType.BASIC: 4,
    SkillType.COOLDOWN: 5,
    SkillType.ULTIMATE: 6,
    SkillType.SPECIAL: 7,
}


class TimelineLoadError(ValueError):
    """Raised when a timeline-format fight file is malformed."""


def _load_character_db():
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _resolve_do(do: str, char_id: str, db: dict, side: str) -> Tuple[int, Optional[str]]:
    """Resolve a `do` field to (action_int, skill_id_or_None).

    Raises TimelineLoadError on unknown verb or unknown skill."""
    if do in DO_VERBS:
        return DO_VERBS[do], None
    if not do.startswith("cast:"):
        raise TimelineLoadError(f"{side}: unknown do verb {do!r}")
    skill_id = do.split(":", 1)[1]
    char_data = db[char_id]
    skill_entries = char_data.get("skills", [])
    match = next((s for s in skill_entries if s["id"] == skill_id), None)
    if match is None:
        # Disambiguate: unknown across the whole game vs known but not on this char
        is_known = any(s["id"] == skill_id
                       for c in db.values() for s in c.get("skills", []))
        if is_known:
            raise TimelineLoadError(
                f"{side}: {skill_id!r} is not a skill of {char_id!r}")
        raise TimelineLoadError(f"{side}: unknown skill id {skill_id!r}")
    stype = SkillType(match["type"])
    action_int = _SKILL_TYPE_TO_ACTION.get(stype)
    if action_int is None:
        raise TimelineLoadError(
            f"{side}: skill {skill_id!r} has unroutable type {stype.value!r}")
    return action_int, skill_id


def _parse_timeline(raw, char_id: str, db: dict, side: str) -> List[TimelineEvent]:
    if not isinstance(raw, list):
        raise TimelineLoadError(f"{side}_timeline must be a list")
    events: List[TimelineEvent] = []
    last_t = -1
    for i, item in enumerate(raw):
        if not isinstance(item, dict) or "t" not in item or "do" not in item:
            raise TimelineLoadError(
                f"{side}_timeline[{i}] needs 't' and 'do'")
        t = item["t"]
        if not isinstance(t, int):
            raise TimelineLoadError(
                f"{side}_timeline[{i}]: t must be an integer (ms), got {t!r}")
        if t < 0:
            raise TimelineLoadError(
                f"{side}_timeline[{i}]: t is negative ({t})")
        if t <= last_t:
            raise TimelineLoadError(
                f"{side}_timeline[{i}]: non-monotonic t "
                f"({t} <= previous {last_t}; timestamps must strictly increase)")
        do = str(item["do"])
        action_int, skill_id = _resolve_do(
            do, char_id, db, f"{side}_timeline[{i}]")
        events.append(TimelineEvent(
            t=t, action_int=action_int, raw_do=do, skill_id=skill_id))
        last_t = t
    return events


def load_timeline_text(text: str) -> Timeline:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise TimelineLoadError(f"invalid YAML: {e}") from e
    if not isinstance(data, dict):
        raise TimelineLoadError("timeline file must be a YAML mapping")
    for key in ("name", "left", "right", "duration_ms",
                "left_timeline", "right_timeline"):
        if key not in data:
            raise TimelineLoadError(f"missing required key: {key!r}")
    db = _load_character_db()
    for side in ("left", "right"):
        if data[side] not in db:
            raise TimelineLoadError(f"unknown character id: {data[side]!r}")
    seed = data.get("seed")
    if seed is not None and not isinstance(seed, int):
        raise TimelineLoadError(f"'seed' must be an integer, got {seed!r}")
    left_smp = data.get("left_start_mp")
    right_smp = data.get("right_start_mp")
    for label, val in (("left_start_mp", left_smp), ("right_start_mp", right_smp)):
        if val is not None and not isinstance(val, int):
            raise TimelineLoadError(f"'{label}' must be an integer, got {val!r}")
    return Timeline(
        name=str(data["name"]),
        left=str(data["left"]), right=str(data["right"]),
        duration_ms=int(data["duration_ms"]),
        left_events=_parse_timeline(
            data["left_timeline"], str(data["left"]), db, "left"),
        right_events=_parse_timeline(
            data["right_timeline"], str(data["right"]), db, "right"),
        seed=int(seed) if seed is not None else None,
        left_start_mp=int(left_smp) if left_smp is not None else None,
        right_start_mp=int(right_smp) if right_smp is not None else None,
    )


def load_timeline(path) -> Timeline:
    """Load + validate a timeline-format fight from a YAML file path."""
    return load_timeline_text(Path(path).read_text(encoding="utf-8"))
