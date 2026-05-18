"""Battle simulation: physics-based 2D melee combat.

Each character has world position and velocity. They walk toward the opponent,
attacks only land when within MELEE_RANGE, and the AI pursues/attacks/reacts.
Pure logic, no rendering. Produces an event log consumable by renderer/captions.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import Skill, SkillType
from pixel_battle.engine.physics import (
    ARENA_LEFT, ARENA_RIGHT, GROUND_Y,
    WALK_SPEED, JUMP_VELOCITY, GRAVITY, MAX_FALL_SPEED,
    MELEE_RANGE, SPECIAL_RANGE, ULTIMATE_TRIGGER_DISTANCE,
    apply_gravity, clamp_x,
)

INTRO_MS = 2000
CRIT_CHANCE = 0.10
CRIT_MULT = 2
STAGGER_MS = 300
SPECIAL_MP_GAIN_PER_HIT = 12
MP_GAIN_ON_HIT_TAKEN = 6
ULTIMATE_DURATION_MS = 6500  # gives cinematic ~6s + 0.5s buffer

# Attack phase timing (ms)
ATTACK_WINDUP_MS = 200
ATTACK_ACTIVE_MS = 90
ATTACK_RECOVER_MS = 250

JUMP_COOLDOWN_MS = 600

# AI tuning
AI_ATTACK_IN_RANGE_PROB = 0.60    # chance to attack per tick when in range
AI_JUMP_IN_RANGE_PROB = 0.20      # chance to jump/dodge per tick when in range
AI_JUMP_APPROACH_PROB = 0.05      # chance to jump while closing distance


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
        self._ultimate_resume_at: Optional[int] = None

        # Initialize physics positions
        left.reset_physics(initial_x=ARENA_LEFT + 60, facing=1)
        right.reset_physics(initial_x=ARENA_RIGHT - 60, facing=-1)

    # ------------------------------------------------------------------ #
    # Public API                                                            #
    # ------------------------------------------------------------------ #

    def tick_ms(self, dt_ms: int) -> None:
        self.elapsed_ms += dt_ms

        if self.state is BattleState.STARTING:
            if self.left.is_ko() or self.right.is_ko():
                self.state = BattleState.FIGHTING
                self._emit(EventType.INTRO)
            elif self.elapsed_ms >= INTRO_MS:
                self.state = BattleState.FIGHTING
                self._emit(EventType.INTRO)
            else:
                return

        if self.state is BattleState.KO:
            return

        if self.state is BattleState.ULTIMATE_PLAYING:
            if self._ultimate_resume_at and self.elapsed_ms >= self._ultimate_resume_at:
                self.state = BattleState.FIGHTING
                self._emit(EventType.ULTIMATE_END)
            return

        # FIGHTING --------------------------------------------------------
        # Pre-existing KO check
        if self.left.is_ko():
            self._end_ko(victim=self.left)
            return
        if self.right.is_ko():
            self._end_ko(victim=self.right)
            return

        # Update physics for both characters
        self._update_physics(self.left, dt_ms)
        self._update_physics(self.right, dt_ms)

        # Update attack phase state machines
        self._update_attack_phase(self.left, self.right, dt_ms)
        if self.state is not BattleState.FIGHTING:
            return
        self._update_attack_phase(self.right, self.left, dt_ms)
        if self.state is not BattleState.FIGHTING:
            return

        # Update hit-stagger timers
        self._update_stagger(self.left, dt_ms)
        self._update_stagger(self.right, dt_ms)

        # Ultimate check — before AI so it fires immediately when ready
        if self.left.ultimate_ready() and self.left.action_state not in ("attacking", "hit_stagger", "ko"):
            self._trigger_ultimate(self.left, self.right)
            return
        if self.right.ultimate_ready() and self.right.action_state not in ("attacking", "hit_stagger", "ko"):
            self._trigger_ultimate(self.right, self.left)
            return

        # AI decisions
        self._ai_choose_action(self.left, self.right, dt_ms)
        self._ai_choose_action(self.right, self.left, dt_ms)

    # ------------------------------------------------------------------ #
    # Physics                                                               #
    # ------------------------------------------------------------------ #

    def _update_physics(self, char: Character, dt_ms: int) -> None:
        """Apply velocity + gravity, resolve ground collision, clamp to arena."""
        # Frames at ~16ms each; physics was designed for 1 frame = 16ms steps.
        # For non-standard dt we scale, but keep it simple: treat each call as 1 frame.

        if not char.on_ground:
            char.vel_y = apply_gravity(char.vel_y)

        char.pos_x = clamp_x(char.pos_x + char.vel_x)
        char.pos_y += char.vel_y

        # Ground collision
        if char.pos_y >= GROUND_Y:
            char.pos_y = GROUND_Y
            char.vel_y = 0.0
            char.on_ground = True
            if char.action_state == "jumping":
                char.action_state = "idle"

        # Decay horizontal velocity when on ground and not walking
        if char.on_ground and char.action_state != "walking":
            char.vel_x *= 0.7  # friction

        # Ensure facing is updated relative to opponent
        # (done during _ai_choose_action instead, to avoid import cycle)

    def _update_stagger(self, char: Character, dt_ms: int) -> None:
        if char.action_state == "hit_stagger":
            if not hasattr(char, "_stagger_remaining_ms"):
                char._stagger_remaining_ms = STAGGER_MS
            char._stagger_remaining_ms -= dt_ms
            if char._stagger_remaining_ms <= 0:
                char.action_state = "idle"
                char._stagger_remaining_ms = 0

    # ------------------------------------------------------------------ #
    # Attack phase state machine                                            #
    # ------------------------------------------------------------------ #

    def _update_attack_phase(self, attacker: Character, defender: Character, dt_ms: int) -> None:
        if attacker.action_state != "attacking":
            return

        attacker.attack_phase_t += dt_ms

        if attacker.attack_phase == "windup":
            if attacker.attack_phase_t >= ATTACK_WINDUP_MS:
                attacker.attack_phase = "active"
                attacker.attack_phase_t = 0
                # Damage check on first frame of active
                self._resolve_attack_hit(attacker, defender)

        elif attacker.attack_phase == "active":
            if attacker.attack_phase_t >= ATTACK_ACTIVE_MS:
                attacker.attack_phase = "recover"
                attacker.attack_phase_t = 0

        elif attacker.attack_phase == "recover":
            if attacker.attack_phase_t >= ATTACK_RECOVER_MS:
                attacker.attack_phase = "none"
                attacker.attack_phase_t = 0
                attacker.action_state = "idle"

    def _resolve_attack_hit(self, attacker: Character, defender: Character) -> None:
        """Called once when attack becomes active. Check range, roll hit."""
        skill = attacker.attack_used_kind
        if skill is None:
            skill = attacker.skills_of_type(SkillType.BASIC)[0]

        distance = abs(attacker.pos_x - defender.pos_x)
        range_limit = SPECIAL_RANGE if skill.skill_type is SkillType.SPECIAL else MELEE_RANGE

        if distance > range_limit:
            self._emit(EventType.MISS, actor=attacker.id, target=defender.id,
                       extra={"reason": "out_of_range"})
            return

        if not self.rng.roll_check(attacker.accuracy):
            self._emit(EventType.MISS, actor=attacker.id, target=defender.id)
            return

        lo, hi = attacker.damage_range
        dmg = self.rng.randint(lo, hi)
        is_crit = self.rng.roll_check(CRIT_CHANCE)
        if is_crit:
            dmg *= CRIT_MULT
            self._emit(EventType.CRIT, actor=attacker.id, target=defender.id, amount=dmg)

        use_special = skill.skill_type is SkillType.SPECIAL
        if use_special:
            dmg += skill.dmg
            attacker.spend_mp(skill.mp_cost)

        attacker.gain_mp(SPECIAL_MP_GAIN_PER_HIT)
        defender.take_damage(dmg)
        defender.gain_mp(MP_GAIN_ON_HIT_TAKEN)

        # Apply stagger + knockback to defender
        defender.action_state = "hit_stagger"
        defender._stagger_remaining_ms = STAGGER_MS
        knockback_dir = 1 if attacker.pos_x < defender.pos_x else -1
        defender.vel_x = knockback_dir * 4.0
        # Cancel defender's attack if mid-swing
        if defender.attack_phase != "none":
            defender.attack_phase = "none"
            defender.attack_phase_t = 0

        attacker.last_attack_ms = self.elapsed_ms

        self._emit(
            EventType.HIT,
            actor=attacker.id,
            target=defender.id,
            amount=dmg,
            extra={
                "skill_id": skill.id,
                "skill_type": skill.skill_type.value,
                "anim": skill.anim,
                "crit": is_crit,
            },
        )

        if defender.is_ko():
            self._end_ko(victim=defender, actor=attacker)

    # ------------------------------------------------------------------ #
    # AI decision                                                           #
    # ------------------------------------------------------------------ #

    def _ai_choose_action(self, char: Character, opp: Character, dt_ms: int) -> None:
        """Simple AI: pursue → attack → react. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return

        # Update facing toward opponent
        if opp.pos_x > char.pos_x:
            char.facing = 1
        else:
            char.facing = -1

        distance = abs(char.pos_x - opp.pos_x)

        # Defensive retreat when very low HP and opponent has high MP
        if char.hp < 30 and opp.mp >= opp.mp_max * 0.7:
            # Walk away
            away_dir = -1 if char.facing == 1 else 1
            self._start_walk(char, away_dir)
            return

        if distance > MELEE_RANGE * 0.8:
            # Close the distance
            self._start_walk(char, char.facing)
            # Small jump chance while approaching
            if char.on_ground and self.rng.roll_check(AI_JUMP_APPROACH_PROB):
                self._start_jump(char)
        else:
            # In range — choose action
            roll = self.rng.uniform()
            if roll < AI_ATTACK_IN_RANGE_PROB:
                # Try to attack
                if char.action_state not in ("attacking",):
                    can_attack = (self.elapsed_ms - char.last_attack_ms) >= char.attack_interval_ms
                    if can_attack:
                        self._start_attack(char, opp)
                    else:
                        # Cooldown still running — keep walking to stay close
                        self._start_walk(char, char.facing)
            elif roll < AI_ATTACK_IN_RANGE_PROB + AI_JUMP_IN_RANGE_PROB:
                # Jump/dodge
                if char.on_ground:
                    self._start_jump(char)
            else:
                # Brief idle — stop walking
                char.vel_x = 0.0
                if char.action_state == "walking":
                    char.action_state = "idle"

    # ------------------------------------------------------------------ #
    # Action helpers (also callable from tests)                             #
    # ------------------------------------------------------------------ #

    def _start_walk(self, char: Character, direction: int) -> None:
        char.vel_x = direction * WALK_SPEED
        char.action_state = "walking"

    def _start_jump(self, char: Character) -> None:
        if not char.on_ground:
            return
        char.vel_y = JUMP_VELOCITY
        char.on_ground = False
        char.action_state = "jumping"

    def _start_attack(self, char: Character, opp: Character) -> None:
        """Begin windup phase. Decide basic vs special skill."""
        if char.action_state == "attacking":
            return  # already mid-attack
        specials = char.skills_of_type(SkillType.SPECIAL)
        # Filter to specials the character can afford
        affordable = [s for s in specials if char.mp >= s.mp_cost]
        use_special = bool(affordable) and self.rng.roll_check(0.5)
        if use_special:
            special = affordable[self.rng.randint(0, len(affordable) - 1)]
        else:
            special = None
        skill = special if use_special else char.skills_of_type(SkillType.BASIC)[0]
        char.attack_used_kind = skill
        char.attack_phase = "windup"
        char.attack_phase_t = 0
        char.action_state = "attacking"
        char.vel_x = 0.0  # plant feet during attack

    # ------------------------------------------------------------------ #
    # Ultimate                                                              #
    # ------------------------------------------------------------------ #

    def _trigger_ultimate(self, attacker: Character, defender: Character) -> None:
        ult = attacker.skills_of_type(SkillType.ULTIMATE)[0]
        attacker.spend_mp(ult.mp_cost)
        defender.take_damage(ult.dmg)
        # Cancel any ongoing attack
        attacker.action_state = "idle"
        attacker.attack_phase = "none"
        self.state = BattleState.ULTIMATE_PLAYING
        self._ultimate_resume_at = self.elapsed_ms + ULTIMATE_DURATION_MS
        self._emit(
            EventType.ULTIMATE_START,
            actor=attacker.id,
            target=defender.id,
            amount=ult.dmg,
            extra={"skill_id": ult.id, "anim": ult.anim, "duration_ms": ULTIMATE_DURATION_MS},
        )
        if defender.is_ko():
            self._end_ko(victim=defender, actor=attacker)

    # ------------------------------------------------------------------ #
    # KO                                                                    #
    # ------------------------------------------------------------------ #

    def _end_ko(self, victim: Character, actor: Optional[Character] = None) -> None:
        self.state = BattleState.KO
        victim.action_state = "ko"
        self._emit(
            EventType.KO,
            actor=actor.id if actor else None,
            target=victim.id,
        )

    # ------------------------------------------------------------------ #
    # Emit helper                                                           #
    # ------------------------------------------------------------------ #

    def _emit(self, etype: EventType, **kwargs) -> None:
        self.events.append(Event(type=etype, t_ms=self.elapsed_ms, **kwargs))
