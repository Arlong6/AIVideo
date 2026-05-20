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
AI_ATTACK_IN_RANGE_PROB = 0.72    # chance to attack per tick when in range
AI_JUMP_IN_RANGE_PROB = 0.10      # chance to jump/dodge per tick when in range
AI_RETREAT_IN_RANGE_PROB = 0.05   # rare retreat to break clinch
AI_JUMP_APPROACH_PROB = 0.03      # chance to jump while closing distance

RETREAT_DURATION_MS = 800           # max consecutive ms in retreat before forced re-evaluate
WALL_STUCK_PX = 30                  # distance from arena edge that counts as stuck
DEFENSIVE_RETREAT_HP = 15           # HP below which defensive retreat may trigger
MIN_CHAR_DISTANCE = 70              # px; min horizontal distance between character centers


class BattleState(Enum):
    STARTING = "starting"
    FIGHTING = "fighting"
    ULTIMATE_PLAYING = "ultimate_playing"
    KO = "ko"


class EventType(Enum):
    INTRO = "intro"
    ATTACK_WINDUP = "attack_windup"
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

    def tick_ms(self, dt_ms: int, skip_ai: bool = False) -> None:
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

        # Resolve character collision (no overlap)
        self._resolve_character_collision()

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

        if skip_ai:
            return

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

    def _resolve_character_collision(self) -> None:
        """Push both characters apart if they're closer than MIN_CHAR_DISTANCE.
        Each takes half of the correction so the midpoint is preserved.
        """
        dx = abs(self.left.pos_x - self.right.pos_x)
        if dx >= MIN_CHAR_DISTANCE:
            return
        push = (MIN_CHAR_DISTANCE - dx) / 2.0
        if self.left.pos_x < self.right.pos_x:
            self.left.pos_x = clamp_x(self.left.pos_x - push)
            self.right.pos_x = clamp_x(self.right.pos_x + push)
        else:
            self.left.pos_x = clamp_x(self.left.pos_x + push)
            self.right.pos_x = clamp_x(self.right.pos_x - push)

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
        # Range: skill.range field if set, else type-based fallback
        if skill.range == "special":
            range_limit = SPECIAL_RANGE
        elif skill.skill_type is SkillType.SPECIAL:
            range_limit = SPECIAL_RANGE
        else:
            range_limit = MELEE_RANGE

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
        use_cooldown = skill.skill_type is SkillType.COOLDOWN
        if use_special:
            dmg += skill.dmg
            attacker.spend_mp(skill.mp_cost)
        elif use_cooldown:
            dmg += skill.dmg  # CD skills also use static dmg as a boost
            attacker.skill_cd_ready_at[skill.id] = self.elapsed_ms + skill.cooldown_ms

        attacker.gain_mp(SPECIAL_MP_GAIN_PER_HIT)
        defender.take_damage(dmg)
        defender.gain_mp(MP_GAIN_ON_HIT_TAKEN)

        # Apply stagger + knockback to defender (skill may override default)
        stagger_ms = skill.stagger_ms if skill.stagger_ms > 0 else STAGGER_MS
        defender.action_state = "hit_stagger"
        defender._stagger_remaining_ms = stagger_ms
        knockback_dir = 1 if attacker.pos_x < defender.pos_x else -1
        defender.vel_x = knockback_dir * 4.0
        # Cancel defender's attack if mid-swing
        if defender.attack_phase != "none":
            defender.attack_phase = "none"
            defender.attack_phase_t = 0

        attacker.last_attack_ms = self.elapsed_ms

        # Punch recoil — attacker gets a small backward velocity reading as reaction force
        recoil_dir = -1 if attacker.pos_x < defender.pos_x else 1
        attacker.vel_x = recoil_dir * 1.5

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
        """Simple AI: pursue → attack → react → retreat. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
        # P5: windup stun — defender is briefly frozen while attacker casts
        if self.elapsed_ms < char.windup_stun_until_ms:
            return

        # Retreat-timer expiry: if a previous retreat has run its course, clear and re-evaluate.
        # When we clear here, do NOT re-trigger a new retreat in the same tick — force the AI
        # to pursue/attack/idle so both sides can't lock each other against walls.
        retreat_just_cleared = False
        if char.retreat_until_ms > 0 and self.elapsed_ms >= char.retreat_until_ms:
            char.retreat_until_ms = 0
            retreat_just_cleared = True

        # Update facing toward opponent
        if opp.pos_x > char.pos_x:
            char.facing = 1
        else:
            char.facing = -1

        distance = abs(char.pos_x - opp.pos_x)
        at_wall = (char.pos_x - ARENA_LEFT < WALL_STUCK_PX or
                   ARENA_RIGHT - char.pos_x < WALL_STUCK_PX)
        can_retreat = (not at_wall
                       and char.retreat_until_ms == 0
                       and not retreat_just_cleared)

        # Strategic retreat: MP near full and opponent very close → brief space-out safely
        if (char.mp >= char.mp_max * 0.92 and distance < MELEE_RANGE * 0.9
                and can_retreat):
            self._start_retreat(char, opp)
            char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
            return

        # Defensive retreat: low HP and opponent building ult
        if (char.hp < DEFENSIVE_RETREAT_HP and opp.mp >= opp.mp_max * 0.7
                and can_retreat):
            self._start_retreat(char, opp)
            char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
            return

        if distance > MELEE_RANGE * 0.95:
            # Approach — too far to fight
            self._start_walk(char, char.facing)
            # Small jump chance while approaching
            if char.on_ground and self.rng.roll_check(AI_JUMP_APPROACH_PROB):
                self._start_jump(char)
        elif distance < MELEE_RANGE * 0.55 and not at_wall:
            # Too close — back off slightly so attacks/effects are visible
            self._start_walk(char, -char.facing)
        else:
            # Kill zone (0.55–0.95 * MELEE_RANGE) — mixed tactics
            roll = self.rng.uniform()
            if roll < AI_ATTACK_IN_RANGE_PROB:
                # Try to attack
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
            elif (roll < AI_ATTACK_IN_RANGE_PROB + AI_JUMP_IN_RANGE_PROB + AI_RETREAT_IN_RANGE_PROB
                  and can_retreat):
                # Retreat — create distance
                self._start_retreat(char, opp)
                char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
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

    def _start_retreat(self, char: Character, opp: Character) -> None:
        """Walk AWAY from opponent for ~400ms or until at arena edge."""
        # Direction away from opponent: if char is right of opp, retreat right (+1); else left (-1)
        direction = 1 if char.pos_x > opp.pos_x else -1
        char.vel_x = WALK_SPEED * direction
        char.action_state = "walking"
        char.facing = -direction  # face opponent while backpedaling

    def _start_attack(self, char: Character, opp: Character) -> None:
        """Begin windup phase. Decide skill: CD-skill > special > basic."""
        if char.action_state == "attacking":
            return  # already mid-attack
        skill = self._choose_attack_skill(char)
        char.attack_used_kind = skill
        # Set anim hint from skill_type for renderer
        if skill.skill_type is SkillType.BASIC:
            char.attack_anim_hint = "jab"
        elif skill.skill_type is SkillType.COOLDOWN:
            char.attack_anim_hint = "cooldown"
        elif skill.skill_type is SkillType.SPECIAL:
            char.attack_anim_hint = "special"
        else:
            char.attack_anim_hint = "jab"
        char.attack_phase = "windup"
        char.attack_phase_t = 0
        char.action_state = "attacking"
        char.vel_x = 0.0  # plant feet during attack
        # Emit windup event for non-basic skills so the renderer can show charge FX
        if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
            self._emit(
                EventType.ATTACK_WINDUP,
                actor=char.id,
                extra={"skill_id": skill.id,
                       "skill_type": skill.skill_type.value},
            )
            # P5: Stronger cast pushback + freeze defender so the skill is visible
            char.vel_x = -7.0 * char.facing       # attacker hops back (P5: 2x)
            opp.vel_x += 5.0 * char.facing        # defender drifts away (P5: 2.5x)
            opp.windup_stun_until_ms = self.elapsed_ms + 200  # P5: 200ms freeze

    def _start_attack_with_kind(self, char: Character, opp: Character,
                                  kind: str) -> None:
        """RL-friendly attack initiator: skip the random selection in
        _choose_attack_skill and pick by category instead.

        kind: "basic" | "cooldown" | "special" | "kick"
          - basic: always picks the first BASIC skill (always available)
          - cooldown: picks first off-cooldown COOLDOWN skill; no-op if none
          - special: picks first affordable SPECIAL skill (mp >= mp_cost);
            no-op if none affordable. MP deduction happens on hit.
          - kick: reuses the BASIC skill stats but tags attack_anim_hint
            so the renderer can switch to a leg-based pose.
        Unknown kinds are a no-op.
        """
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
        if self.elapsed_ms < char.last_attack_ms + char.attack_interval_ms:
            return  # respect attack interval gate

        if kind == "basic":
            skill = char.skills_of_type(SkillType.BASIC)[0]
            char.attack_anim_hint = "jab"
        elif kind == "cooldown":
            cd_skills = char.skills_of_type(SkillType.COOLDOWN)
            available = [s for s in cd_skills
                          if char.skill_off_cooldown(s, self.elapsed_ms)]
            if not available:
                return  # no CD skill ready — no-op
            skill = available[0]
            char.attack_anim_hint = "cooldown"
        elif kind == "special":
            specials = char.skills_of_type(SkillType.SPECIAL)
            affordable = [s for s in specials if char.mp >= s.mp_cost]
            if not affordable:
                return
            skill = affordable[0]
            char.attack_anim_hint = "special"
        elif kind == "kick":
            # Kick reuses the BASIC skill stats but the renderer should show
            # a leg-based animation. We tag the character via attack_anim_hint.
            skill = char.skills_of_type(SkillType.BASIC)[0]
            char.attack_anim_hint = "kick"
        else:
            return

        # Mirror _start_attack body but with explicit skill choice
        char.attack_used_kind = skill
        char.attack_phase = "windup"
        char.attack_phase_t = 0
        char.action_state = "attacking"
        char.vel_x = 0.0

        if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
            self._emit(
                EventType.ATTACK_WINDUP,
                actor=char.id,
                extra={"skill_id": skill.id,
                       "skill_type": skill.skill_type.value},
            )
            # P5 cast pushback + defender freeze
            char.vel_x = -7.0 * char.facing
            opp.vel_x += 5.0 * char.facing
            opp.windup_stun_until_ms = self.elapsed_ms + 200

    def _choose_attack_skill(self, char: Character) -> Skill:
        """Priority: CD-skill (off-cd, 70%) > affordable special (40%) > basic."""
        # 1. CD skill if any off-cooldown
        cd_skills = char.skills_of_type(SkillType.COOLDOWN)
        for skill in cd_skills:
            if char.skill_off_cooldown(skill, self.elapsed_ms):
                if self.rng.roll_check(0.70):
                    return skill
                break  # rolled against — fall through, don't try other CD skills

        # 2. Affordable special
        specials = char.skills_of_type(SkillType.SPECIAL)
        affordable = [s for s in specials if char.mp >= s.mp_cost]
        if affordable and self.rng.roll_check(0.40):
            return affordable[self.rng.randint(0, len(affordable) - 1)]

        # 3. Basic
        return char.skills_of_type(SkillType.BASIC)[0]

    # ------------------------------------------------------------------ #
    # Ultimate                                                              #
    # ------------------------------------------------------------------ #

    def _trigger_ultimate(self, attacker: Character, defender: Character,
                          cinematic_pause: bool = True) -> None:
        ult = attacker.skills_of_type(SkillType.ULTIMATE)[0]
        attacker.spend_mp(ult.mp_cost)
        defender.take_damage(ult.dmg)
        # Cancel any ongoing attack
        attacker.action_state = "idle"
        attacker.attack_phase = "none"
        # cinematic_pause=True freezes the battle for ULTIMATE_DURATION_MS so a
        # scripted episode can play a cutscene. The RL renderer passes False:
        # there is no cutscene, so the pause is just a multi-second dead freeze
        # in the video. With it off the ultimate is an instant heavy hit and
        # the fight continues.
        if cinematic_pause:
            self.state = BattleState.ULTIMATE_PLAYING
            self._ultimate_resume_at = self.elapsed_ms + ULTIMATE_DURATION_MS
        duration_ms = ULTIMATE_DURATION_MS if cinematic_pause else 0
        self._emit(
            EventType.ULTIMATE_START,
            actor=attacker.id,
            target=defender.id,
            amount=ult.dmg,
            extra={"skill_id": ult.id, "anim": ult.anim, "duration_ms": duration_ms},
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
