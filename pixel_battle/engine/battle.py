"""Battle simulation: state machine + per-tick combat resolution.

Pure logic, no rendering. Produces an event log consumable by renderer/captions.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import Skill, SkillType

INTRO_MS = 2000
CRIT_CHANCE = 0.10
CRIT_MULT = 2
STAGGER_MS = 500
SPECIAL_MP_GAIN_PER_HIT = 12
MP_GAIN_ON_HIT_TAKEN = 6


class BattleState(Enum):
    STARTING = "starting"
    FIGHTING = "fighting"
    ULTIMATE_PLAYING = "ultimate_playing"
    KO = "ko"


class EventType(Enum):
    INTRO = "intro"
    HIT = "hit"
    MISS = "miss"
    CRIT = "crit"
    ULTIMATE_START = "ultimate_start"
    ULTIMATE_END = "ultimate_end"
    KO = "ko"


@dataclass
class Event:
    type: EventType
    t_ms: int
    actor: Optional[str] = None
    target: Optional[str] = None
    amount: int = 0
    extra: dict = field(default_factory=dict)


class Battle:
    def __init__(self, left: Character, right: Character, rng: BattleRNG):
        self.left = left
        self.right = right
        self.rng = rng
        self.state = BattleState.STARTING
        self.elapsed_ms = 0
        self.events: List[Event] = []
        self._left_stagger_until = -1
        self._right_stagger_until = -1
        self._ultimate_resume_at: Optional[int] = None

    def tick_ms(self, dt_ms: int) -> None:
        self.elapsed_ms += dt_ms

        if self.state is BattleState.STARTING:
            # A pre-KO condition (e.g. set externally) skips the intro entirely
            if self.left.is_ko() or self.right.is_ko():
                self.state = BattleState.FIGHTING
                self._emit(EventType.INTRO)
                # Fall through to FIGHTING logic (KO guard below will handle it)
            elif self.elapsed_ms >= INTRO_MS:
                self.state = BattleState.FIGHTING
                self._emit(EventType.INTRO)
                # Fall through to FIGHTING logic below
            else:
                return

        if self.state is BattleState.KO:
            return

        if self.state is BattleState.ULTIMATE_PLAYING:
            if self._ultimate_resume_at and self.elapsed_ms >= self._ultimate_resume_at:
                self.state = BattleState.FIGHTING
                self._emit(EventType.ULTIMATE_END)
            return

        # FIGHTING state — check for pre-existing KO (e.g. damage applied externally)
        if self.left.is_ko():
            self.state = BattleState.KO
            self._emit(EventType.KO, target=self.left.id)
            return
        if self.right.is_ko():
            self.state = BattleState.KO
            self._emit(EventType.KO, target=self.right.id)
            return

        self._try_attack(self.left, self.right, self._left_stagger_until)
        if self.state is not BattleState.FIGHTING:
            return
        self._try_attack(self.right, self.left, self._right_stagger_until)

    def _try_attack(self, attacker: Character, defender: Character, stagger_until: int) -> None:
        if self.elapsed_ms < stagger_until:
            return
        if self.elapsed_ms - attacker.last_attack_ms < attacker.attack_interval_ms:
            return
        attacker.last_attack_ms = self.elapsed_ms

        if not self.rng.roll_check(attacker.accuracy):
            self._emit(EventType.MISS, actor=attacker.id, target=defender.id)
            return

        lo, hi = attacker.damage_range
        dmg = self.rng.randint(lo, hi)
        is_crit = self.rng.roll_check(CRIT_CHANCE)
        if is_crit:
            dmg *= CRIT_MULT
            self._emit(EventType.CRIT, actor=attacker.id, target=defender.id, amount=dmg)

        defender.take_damage(dmg)
        attacker.gain_mp(SPECIAL_MP_GAIN_PER_HIT)
        defender.gain_mp(MP_GAIN_ON_HIT_TAKEN)

        if defender is self.left:
            self._left_stagger_until = self.elapsed_ms + STAGGER_MS
        else:
            self._right_stagger_until = self.elapsed_ms + STAGGER_MS

        self._emit(EventType.HIT, actor=attacker.id, target=defender.id, amount=dmg)

        if defender.is_ko():
            self.state = BattleState.KO
            self._emit(EventType.KO, actor=attacker.id, target=defender.id)

    def _emit(self, etype: EventType, **kwargs) -> None:
        self.events.append(Event(type=etype, t_ms=self.elapsed_ms, **kwargs))
