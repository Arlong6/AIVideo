# pixel_battle/script/driver.py
"""ScriptDriver — turns a FightScript into per-tick engine actions."""
from __future__ import annotations

from pixel_battle.script.conditions import ConditionContext
from pixel_battle.script.loader import DO_VERBS, FightScript

# An intent that never satisfies its `until` is force-advanced after this long,
# so a script can never hang.
INTENT_MAX_MS = 4000


class _SideState:
    """Per-character cursor through an intent list."""
    def __init__(self, intents):
        self.intents = intents
        self.index = 0
        self.intent_start_ms = None        # battle.elapsed_ms when intent began
        self.attacked_this_intent = False

    def active(self):
        if self.index < len(self.intents):
            return self.intents[self.index]
        return None


class ScriptDriver:
    """Plays a FightScript: each tick, emits (left_action, right_action)."""

    def __init__(self, script: FightScript):
        self.script = script
        self._left = _SideState(script.left_intents)
        self._right = _SideState(script.right_intents)

    def decide(self, battle) -> tuple:
        """Return (left_action, right_action) for the current battle tick."""
        dist = abs(battle.left.pos_x - battle.right.pos_x)
        left_act = self._decide_side(self._left, battle.left, battle.right,
                                     dist, battle.elapsed_ms)
        right_act = self._decide_side(self._right, battle.right, battle.left,
                                      dist, battle.elapsed_ms)
        return left_act, right_act

    def _decide_side(self, state: _SideState, char, opp,
                     dist: float, now_ms: int) -> int:
        intent = state.active()
        if intent is None:
            return DO_VERBS["idle"]              # script exhausted → idle

        if state.intent_start_ms is None:
            state.intent_start_ms = now_ms
            state.attacked_this_intent = False

        elapsed = now_ms - state.intent_start_ms
        if char.action_state == "attacking":
            state.attacked_this_intent = True

        ctx = ConditionContext(
            dist=dist, intent_elapsed_ms=elapsed, char=char, opponent=opp,
            attacked_this_intent=state.attacked_this_intent)

        if intent.until(ctx) or elapsed >= INTENT_MAX_MS:
            state.index += 1
            state.intent_start_ms = None         # next intent starts fresh
            intent = state.active()
            if intent is None:
                return DO_VERBS["idle"]

        return DO_VERBS[intent.do]
