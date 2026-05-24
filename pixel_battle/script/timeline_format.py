"""Dataclasses for the absolute-timeline fight format (Sub-project D)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class TimelineEvent:
    """One scheduled action on a character's timeline."""
    t: int                       # ms from match start
    action_int: int              # engine action 0..10
    raw_do: str                  # the source `do` verb (for debug / trace)
    skill_id: Optional[str] = None   # set when raw_do is "cast:<skill_id>"


@dataclass
class Timeline:
    """A loaded timeline-format fight: two parallel event lists."""
    name: str
    left: str                       # left character id
    right: str                      # right character id
    duration_ms: int                # author-declared expected fight length
    left_events: List[TimelineEvent]
    right_events: List[TimelineEvent]
