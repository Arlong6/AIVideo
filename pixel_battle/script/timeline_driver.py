# pixel_battle/script/timeline_driver.py
"""TimelineDriver — plays a Timeline against a Battle, tick by tick.

Per-character cursors + per-character accumulated delay offsets. When a
character cannot act at the scheduled time, the entire remaining timeline
on THAT character shifts forward together; the other character is
unaffected. See spec §7."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from pixel_battle.engine.effects import ROOT
from pixel_battle.script.timeline_format import Timeline, TimelineEvent


# Engine tick granularity — match Battle.tick_ms's typical step (the renderer
# steps at 1 frame ≈ 16 ms). When the driver can't fire an event, it pushes
# the per-character delay by this much so the event retries next tick.
# Must match rl/env.py:TICK_MS. Update both together.
ENGINE_TICK_MS = 16

# Cumulative-delay cap: stuns and long animations would otherwise push a
# character's whole timeline arbitrarily far into the future, causing huge
# idle gaps later. 400ms is "two attack-phase animations" worth of slop.
DELAY_CAP_MS = 400

# Action int constants — kept in sync with DO_VERBS / engine `_apply_action`.
_IDLE = 0
_RETREAT = 1
_ADVANCE = 2
_JUMP = 3
_ATK_BASIC = 4
_ATK_CD = 5
_ATK_ULT = 6
_ATK_SPECIAL = 7
_ATK_KICK = 8
_FLASH_IN = 9
_FLASH_BACK = 10
_BLOCK = 11
_CROUCH = 12

_ATTACK_ACTIONS = frozenset({_ATK_BASIC, _ATK_CD, _ATK_ULT, _ATK_SPECIAL, _ATK_KICK})
_MOVE_ACTIONS = frozenset({_RETREAT, _ADVANCE, _JUMP})
_GROUND_ACTIONS = _MOVE_ACTIONS | _ATTACK_ACTIONS
_DEFENSIVE_ACTIONS = frozenset({_BLOCK, _CROUCH})


@dataclass
class _SideCursor:
    events: List[TimelineEvent]
    index: int = 0
    delay_ms: int = 0

    def peek(self) -> Optional[TimelineEvent]:
        return self.events[self.index] if self.index < len(self.events) else None

    def advance(self) -> None:
        self.index += 1


def _can_act(char, action_int: int) -> bool:
    """Predicate: would emitting this action right now be wasted?

    Kept deliberately small. Engine's `_apply_action` remains authoritative
    on cooldown / mp / range / facing; the driver only checks two cases
    where the engine would silently drop the event and the script's intent
    is clearly "wait for the block to clear":
      - mid-attack-phase (windup/active/recover): a new attack/movement is
        a no-op until the current animation ends.
      - rooted + movement verb: root pins the character; the script wants
        movement to fire after root drops, not while it's active.
    Casting and Flash are NOT blocked by root (Flash bypasses root; a cast
    issued under root should start windup the moment root expires).
    Block and crouch can fire from any non-attacking/non-stagger state."""
    if action_int == _IDLE:
        return True
    if char.action_state in ("attacking", "hit_stagger"):
        return False
    # Defensive actions (block/crouch) can fire from idle, walk, or even
    # while blocking/crouching (to re-enter the defensive state).
    if action_int in _DEFENSIVE_ACTIONS:
        return True
    # `pos_y > GROUND_Y - tolerance` -- jumping mid-air. Ground verbs (move/
    # attack) are engine no-ops in mid-air; let them wait for landing.
    if char.action_state == "jumping" and action_int in _GROUND_ACTIONS:
        return False
    # Root: blocks movement; Flash/cast still allowed
    if char.has_effect(ROOT) and action_int in _MOVE_ACTIONS:
        return False
    return True


class TimelineDriver:
    """Drives a Battle from a Timeline. Same call interface as ScriptDriver:
    `decide(battle) -> (left_action, right_action)` per tick."""

    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.left = timeline.left
        self.right = timeline.right
        self._left = _SideCursor(events=timeline.left_events)
        self._right = _SideCursor(events=timeline.right_events)

    def decide(self, battle):
        left_act = self._decide_side(self._left, battle.left, battle.elapsed_ms)
        right_act = self._decide_side(self._right, battle.right, battle.elapsed_ms)
        return left_act, right_act

    def _decide_side(self, cursor: _SideCursor, char, elapsed_ms: int) -> int:
        ev = cursor.peek()
        if ev is None:
            return _IDLE
        scheduled_t = ev.t + cursor.delay_ms
        if elapsed_ms < scheduled_t:
            return _IDLE
        if not _can_act(char, ev.action_int):
            # Special case: rooted character with a movement event — root can
            # last 1.5s+, which would otherwise jam the whole timeline behind
            # one missed step. SKIP the movement event (advance cursor) rather
            # than wait — its window has already passed.
            if char.has_effect(ROOT) and ev.action_int in _MOVE_ACTIONS:
                cursor.advance()
                return _IDLE
            # Cap cumulative delay so long stuns don't push the whole timeline
            # arbitrarily far into the future.
            if cursor.delay_ms < DELAY_CAP_MS:
                cursor.delay_ms += ENGINE_TICK_MS
            return _IDLE
        # Fire — set the named-skill channel for cast: events, then advance cursor.
        if ev.skill_id is not None:
            char.pending_cast_skill_id = ev.skill_id
        cursor.advance()
        return ev.action_int
