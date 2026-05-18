# Pixel Battle P1 "Watchable Polish" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cooldown-gated skill tier and Smash-Bros-style HUD/effects to make `ep01_brick_vs_glass/final.mp4` watchable on first viewing.

**Architecture:** Extend the existing data-driven engine: `Skill` gets `cooldown_ms`/`range`/`stagger_ms`, `Character` tracks per-skill CD readiness, `Battle` AI prioritizes CD-skills, a new `engine/hud.py` module owns skill-icons / DPS / damage-popups / MP-charge-ring, episode runner routes per-skill particle colors. No new sprite art.

**Tech Stack:** Python 3, pygame (headless via `SDL_VIDEODRIVER=dummy`), pytest. All rendering targets 480×854 vertical (TikTok).

**Spec:** `docs/superpowers/specs/2026-05-18-pixel-battle-p1-design.md`

---

## File Structure

**Create:**
- `pixel_battle/engine/hud.py` — `DamagePopup`, `DamagePopupLayer`, `DPSCounter`, `SkillIconBar`, `MPChargeRing`, `HUDOverlay`
- `pixel_battle/tests/test_hud.py` — unit tests for HUD pieces
- `pixel_battle/tests/test_skill_cooldown.py` — CD gating tests
- `pixel_battle/tests/test_battle_ai_priority.py` — AI choice tests

**Modify:**
- `pixel_battle/engine/skill.py` — new fields + new `SkillType.COOLDOWN`
- `pixel_battle/engine/character.py` — `skill_cd_ready_at` + `skill_off_cooldown`
- `pixel_battle/engine/battle.py` — AI priority + cooldown gating + range/stagger from skill
- `pixel_battle/engine/renderer.py` — instantiate HUDOverlay, call its `render`
- `pixel_battle/data/characters.json` — add `screw_dart` + `shard_scatter`
- `pixel_battle/episodes/ep01_brick_vs_glass.py` — HIT-event color routing + popup spawn + per-skill hit-stop
- `pixel_battle/tests/test_skill.py` — extend with new-field tests

---

## Task 1: Extend `Skill` with `cooldown_ms`, `range`, `stagger_ms` + new `SkillType.COOLDOWN`

**Files:**
- Modify: `pixel_battle/engine/skill.py`
- Modify: `pixel_battle/tests/test_skill.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_skill.py`:

```python
def test_cooldown_skill_type():
    s = Skill.from_dict({
        "id": "screw_dart", "type": "cooldown", "anim": "screw_dart",
        "cooldown_ms": 4000, "dmg": 5, "range": "special",
    })
    assert s.skill_type is SkillType.COOLDOWN
    assert s.cooldown_ms == 4000
    assert s.range == "special"
    assert s.stagger_ms == 0
    assert s.mp_cost == 0


def test_skill_defaults_for_new_fields():
    """Existing skill dicts without new fields still load with defaults."""
    s = Skill.from_dict({"id": "headbutt", "type": "basic", "anim": "attack"})
    assert s.cooldown_ms == 0
    assert s.range == "melee"
    assert s.stagger_ms == 0


def test_skill_stagger_ms():
    s = Skill.from_dict({
        "id": "shard_scatter", "type": "cooldown", "anim": "shard_scatter",
        "cooldown_ms": 4000, "dmg": 4, "range": "special", "stagger_ms": 500,
    })
    assert s.stagger_ms == 500
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_skill.py -v
```
Expected: 3 new tests FAIL (unknown skill type "cooldown" / no `cooldown_ms` attribute).

- [ ] **Step 3: Update `pixel_battle/engine/skill.py`**

Replace file contents with:

```python
"""Skill data model. Skills are pure data loaded from characters.json."""
from dataclasses import dataclass
from enum import Enum


class SkillType(Enum):
    BASIC = "basic"
    COOLDOWN = "cooldown"
    SPECIAL = "special"
    ULTIMATE = "ultimate"


@dataclass
class Skill:
    id: str
    skill_type: SkillType
    anim: str
    mp_cost: int = 0
    dmg: int = 0
    cooldown_ms: int = 0
    range: str = "melee"        # "melee" | "special"
    stagger_ms: int = 0          # 0 = use engine default STAGGER_MS

    @classmethod
    def from_dict(cls, d: dict) -> "Skill":
        try:
            skill_type = SkillType(d["type"])
        except ValueError as e:
            raise ValueError(f"Unknown skill type: {d['type']}") from e
        return cls(
            id=d["id"],
            skill_type=skill_type,
            anim=d["anim"],
            mp_cost=d.get("mp_cost", 0),
            dmg=d.get("dmg", 0),
            cooldown_ms=d.get("cooldown_ms", 0),
            range=d.get("range", "melee"),
            stagger_ms=d.get("stagger_ms", 0),
        )
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_skill.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/skill.py pixel_battle/tests/test_skill.py
git commit -m "feat(pixel-battle): add cooldown skill type + range/stagger fields"
```

---

## Task 2: `Character` tracks per-skill cooldown readiness

**Files:**
- Modify: `pixel_battle/engine/character.py`
- Modify: `pixel_battle/tests/test_character.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_character.py`:

```python
from pixel_battle.engine.skill import Skill, SkillType


def test_character_skill_cd_ready_at_starts_empty():
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=100, facing=1)
    assert c.skill_cd_ready_at == {}


def test_skill_off_cooldown_true_when_not_used():
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=100, facing=1)
    skill = Skill(id="screw_dart", skill_type=SkillType.COOLDOWN,
                  anim="screw_dart", cooldown_ms=4000, dmg=5)
    assert c.skill_off_cooldown(skill, now_ms=0) is True
    assert c.skill_off_cooldown(skill, now_ms=10_000) is True


def test_skill_off_cooldown_respects_ready_at():
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=100, facing=1)
    c.skill_cd_ready_at["screw_dart"] = 5000
    skill = Skill(id="screw_dart", skill_type=SkillType.COOLDOWN,
                  anim="screw_dart", cooldown_ms=4000, dmg=5)
    assert c.skill_off_cooldown(skill, now_ms=4999) is False
    assert c.skill_off_cooldown(skill, now_ms=5000) is True
    assert c.skill_off_cooldown(skill, now_ms=5001) is True


def test_reset_physics_clears_cooldowns():
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=100, facing=1)
    c.skill_cd_ready_at["screw_dart"] = 9999
    c.reset_physics(initial_x=100, facing=1)
    assert c.skill_cd_ready_at == {}
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_character.py -v
```
Expected: 4 new tests FAIL.

- [ ] **Step 3: Edit `pixel_battle/engine/character.py`**

Add `field` import + 2 changes:

Replace the import line:
```python
from dataclasses import dataclass
```
with:
```python
from dataclasses import dataclass, field
```

Add the new field — find the line `attack_used_kind: object = None` and add a line after it:
```python
    skill_cd_ready_at: dict = field(default_factory=dict)
```

Add a new method after `ultimate_ready` (last method of class):
```python
    def skill_off_cooldown(self, skill, now_ms: int) -> bool:
        return self.skill_cd_ready_at.get(skill.id, 0) <= now_ms
```

In `reset_physics`, after the line `self.last_attack_ms = -10000`, add:
```python
        self.skill_cd_ready_at = {}
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_character.py pixel_battle/tests/test_skill.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/character.py pixel_battle/tests/test_character.py
git commit -m "feat(pixel-battle): Character tracks per-skill cooldown readiness"
```

---

## Task 3: Add `screw_dart` + `shard_scatter` to `characters.json`

**Files:**
- Modify: `pixel_battle/data/characters.json`
- Create: `pixel_battle/tests/test_skill_cooldown.py`

- [ ] **Step 1: Write failing tests**

Create `pixel_battle/tests/test_skill_cooldown.py`:

```python
from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType


def test_brick_has_screw_dart_cd_skill():
    c = Character.load("brick_phone")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "screw_dart"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 5
    assert cd_skills[0].range == "special"


def test_glass_has_shard_scatter_cd_skill():
    c = Character.load("glass_slab")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "shard_scatter"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 4
    assert cd_skills[0].range == "special"
    assert cd_skills[0].stagger_ms == 500


def test_both_characters_still_have_basic_and_specials_and_ult():
    for char_id in ["brick_phone", "glass_slab"]:
        c = Character.load(char_id)
        assert len(c.skills_of_type(SkillType.BASIC)) == 1
        assert len(c.skills_of_type(SkillType.SPECIAL)) == 2
        assert len(c.skills_of_type(SkillType.ULTIMATE)) == 1
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_skill_cooldown.py -v
```
Expected: 3 tests FAIL (no cooldown skills yet).

- [ ] **Step 3: Update `pixel_battle/data/characters.json`**

Replace file contents with:

```json
{
  "brick_phone": {
    "display_name": "Brick Phone",
    "color": [70, 70, 70],
    "accent_color": [80, 200, 80],
    "attack_interval_ms": 1200,
    "accuracy": 0.80,
    "damage": [2, 3],
    "skills": [
      {"id": "headbutt", "type": "basic", "anim": "attack"},
      {"id": "screw_dart", "type": "cooldown", "cooldown_ms": 4000, "dmg": 5, "range": "special", "anim": "screw_dart"},
      {"id": "snake_strike", "type": "special", "mp_cost": 30, "dmg": 8, "anim": "snake_strike"},
      {"id": "ringtone_blast", "type": "special", "mp_cost": 25, "dmg": 6, "anim": "ringtone_blast"},
      {"id": "indestructible_throw", "type": "ultimate", "mp_cost": 100, "dmg": 25, "anim": "indestructible_throw"}
    ]
  },
  "glass_slab": {
    "display_name": "Glass Slab",
    "color": [220, 220, 235],
    "accent_color": [50, 130, 255],
    "attack_interval_ms": 900,
    "accuracy": 0.75,
    "damage": [2, 3],
    "skills": [
      {"id": "swipe", "type": "basic", "anim": "attack"},
      {"id": "shard_scatter", "type": "cooldown", "cooldown_ms": 4000, "dmg": 4, "range": "special", "stagger_ms": 500, "anim": "shard_scatter"},
      {"id": "ringtone_shock", "type": "special", "mp_cost": 30, "dmg": 7, "anim": "ringtone_shock"},
      {"id": "ad_popup_spam", "type": "special", "mp_cost": 25, "dmg": 6, "anim": "ad_popup_spam"},
      {"id": "force_update", "type": "ultimate", "mp_cost": 100, "dmg": 22, "anim": "force_update"}
    ]
  }
}
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_skill_cooldown.py pixel_battle/tests/test_character.py pixel_battle/tests/test_skill.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/data/characters.json pixel_battle/tests/test_skill_cooldown.py
git commit -m "feat(pixel-battle): add screw_dart + shard_scatter CD skills"
```

---

## Task 4: Battle uses skill.range + skill.stagger_ms in hit resolution + records CD readiness

**Files:**
- Modify: `pixel_battle/engine/battle.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_skill_cooldown.py`:

```python
from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import SPECIAL_RANGE, MELEE_RANGE


def _setup_close_battle(seed=42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    # Past intro
    bat.tick_ms(2500)
    return bat, a, b


def test_cd_skill_hit_sets_ready_at():
    """When CD skill lands a hit, attacker.skill_cd_ready_at gets set."""
    from pixel_battle.engine.skill import SkillType
    bat, a, b = _setup_close_battle(seed=42)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    # Place attacker in range, force attack with the CD skill
    a.pos_x = 200
    b.pos_x = 200 + int(SPECIAL_RANGE * 0.5)
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0  # guarantee hit
    # Tick through windup -> active (windup is 200ms)
    for _ in range(20):
        bat.tick_ms(16)
    # Either skill_cd_ready_at["screw_dart"] is set OR attack rolled out of range (shouldn't here)
    assert "screw_dart" in a.skill_cd_ready_at
    assert a.skill_cd_ready_at["screw_dart"] >= bat.elapsed_ms


def test_cd_skill_connects_at_special_range():
    """CD skill has range='special' so it lands beyond MELEE_RANGE."""
    from pixel_battle.engine.skill import SkillType
    bat, a, b = _setup_close_battle(seed=99)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    # Place attacker JUST beyond MELEE_RANGE but inside SPECIAL_RANGE
    a.pos_x = 200
    b.pos_x = 200 + int((MELEE_RANGE + SPECIAL_RANGE) / 2)  # mid-zone
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0
    starting_hp = b.hp
    for _ in range(20):
        bat.tick_ms(16)
        if b.hp < starting_hp:
            break
    assert b.hp < starting_hp, "CD skill should connect at special range"


def test_cd_skill_uses_custom_stagger_ms():
    """shard_scatter has stagger_ms=500, so defender stagger is longer than default 300."""
    from pixel_battle.engine.skill import SkillType
    a = Character.load("glass_slab")
    b = Character.load("brick_phone")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(2500)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    assert cd_skill.stagger_ms == 500
    a.pos_x = 200
    b.pos_x = 200 + int(SPECIAL_RANGE * 0.4)
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0
    for _ in range(20):
        bat.tick_ms(16)
        if b.action_state == "hit_stagger":
            break
    assert b.action_state == "hit_stagger"
    assert getattr(b, "_stagger_remaining_ms", 0) >= 480  # ~500ms minus a tick
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_skill_cooldown.py -v
```
Expected: 3 new tests FAIL (battle doesn't use skill.range / stagger_ms yet).

- [ ] **Step 3: Edit `pixel_battle/engine/battle.py`**

Update `_resolve_attack_hit` — find the block:

```python
        distance = abs(attacker.pos_x - defender.pos_x)
        range_limit = SPECIAL_RANGE if skill.skill_type is SkillType.SPECIAL else MELEE_RANGE
```

Replace with:

```python
        distance = abs(attacker.pos_x - defender.pos_x)
        # Range: use skill.range field if set, else fall back to type-based
        if skill.range == "special":
            range_limit = SPECIAL_RANGE
        elif skill.skill_type is SkillType.SPECIAL:
            range_limit = SPECIAL_RANGE
        else:
            range_limit = MELEE_RANGE
```

Find the block:
```python
        use_special = skill.skill_type is SkillType.SPECIAL
        if use_special:
            dmg += skill.dmg
            attacker.spend_mp(skill.mp_cost)

        attacker.gain_mp(SPECIAL_MP_GAIN_PER_HIT)
```

Replace with:
```python
        use_special = skill.skill_type is SkillType.SPECIAL
        use_cooldown = skill.skill_type is SkillType.COOLDOWN
        if use_special:
            dmg += skill.dmg
            attacker.spend_mp(skill.mp_cost)
        elif use_cooldown:
            dmg += skill.dmg  # CD skills also use their static dmg as a boost
            attacker.skill_cd_ready_at[skill.id] = self.elapsed_ms + skill.cooldown_ms

        attacker.gain_mp(SPECIAL_MP_GAIN_PER_HIT)
```

Find the block:
```python
        # Apply stagger + knockback to defender
        defender.action_state = "hit_stagger"
        defender._stagger_remaining_ms = STAGGER_MS
```

Replace with:
```python
        # Apply stagger + knockback to defender (skill may override default)
        stagger_ms = skill.stagger_ms if skill.stagger_ms > 0 else STAGGER_MS
        defender.action_state = "hit_stagger"
        defender._stagger_remaining_ms = stagger_ms
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_skill_cooldown.py pixel_battle/tests/test_battle.py -v
```
Expected: all PASS (including pre-existing battle tests).

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_skill_cooldown.py
git commit -m "feat(pixel-battle): Battle uses skill range/stagger + records CD readiness"
```

---

## Task 5: Battle AI prioritizes CD skill > special > basic

**Files:**
- Modify: `pixel_battle/engine/battle.py`
- Create: `pixel_battle/tests/test_battle_ai_priority.py`

- [ ] **Step 1: Write failing tests**

Create `pixel_battle/tests/test_battle_ai_priority.py`:

```python
"""AI skill-choice priority: ultimate > CD-skill (off-cd) > special (affordable) > basic."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle_in_range(seed=42):
    """Make battle where attacker is in melee range of defender."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # within MELEE_RANGE (110)
    return bat, a, b


def test_cd_skill_chosen_when_off_cooldown():
    """When CD skill is off cooldown, AI picks it (with high probability) over basic."""
    bat, a, b = _battle_in_range(seed=42)
    # Drain MP so specials are unavailable
    a.mp = 0
    chosen = []
    for _ in range(20):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.last_attack_ms = -10000
        a.skill_cd_ready_at = {}  # always off CD
        bat._start_attack(a, b)
        chosen.append(a.attack_used_kind.id)
    assert "screw_dart" in chosen, f"Expected screw_dart in {chosen}"


def test_cd_skill_skipped_when_on_cooldown():
    """When CD skill is on cooldown, AI falls back to basic (MP=0)."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0
    a.skill_cd_ready_at["screw_dart"] = 999_999  # far future
    a.last_attack_ms = -10000
    bat._start_attack(a, b)
    assert a.attack_used_kind.id == "headbutt"


def test_special_chosen_when_affordable_and_no_cd():
    """No CD skills off-cd, but specials affordable → AI may pick special."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 50
    a.skill_cd_ready_at["screw_dart"] = 999_999  # gate out CD
    chosen = []
    for _ in range(20):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.last_attack_ms = -10000
        bat._start_attack(a, b)
        chosen.append(a.attack_used_kind.skill_type)
    # Should see at least one SPECIAL across 20 rolls (40% prob each)
    assert SkillType.SPECIAL in chosen, f"Expected SPECIAL in {chosen}"


def test_basic_chosen_when_nothing_else_available():
    bat, a, b = _battle_in_range(seed=1)
    a.mp = 0
    a.skill_cd_ready_at["screw_dart"] = 999_999
    a.last_attack_ms = -10000
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_battle_ai_priority.py -v
```
Expected: at least `test_cd_skill_chosen_when_off_cooldown` FAILs (no CD priority yet).

- [ ] **Step 3: Edit `pixel_battle/engine/battle.py`**

Find the `_start_attack` method:

```python
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
```

Replace the body (keep the signature + docstring + early-return) with:

```python
    def _start_attack(self, char: Character, opp: Character) -> None:
        """Begin windup phase. Decide skill: CD-skill > special > basic."""
        if char.action_state == "attacking":
            return  # already mid-attack
        skill = self._choose_attack_skill(char)
        char.attack_used_kind = skill
        char.attack_phase = "windup"
        char.attack_phase_t = 0
        char.action_state = "attacking"
        char.vel_x = 0.0  # plant feet during attack

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
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_battle_ai_priority.py pixel_battle/tests/test_battle.py pixel_battle/tests/test_skill_cooldown.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_battle_ai_priority.py
git commit -m "feat(pixel-battle): AI prioritizes CD-skill > special > basic"
```

---

## Task 6: HUD module — `DamagePopup` + `DamagePopupLayer`

**Files:**
- Create: `pixel_battle/engine/hud.py`
- Create: `pixel_battle/tests/test_hud.py`

- [ ] **Step 1: Write failing tests**

Create `pixel_battle/tests/test_hud.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.hud import DamagePopupLayer


def test_damage_popup_layer_starts_empty():
    layer = DamagePopupLayer()
    assert len(layer.popups) == 0


def test_spawn_adds_popup():
    layer = DamagePopupLayer()
    layer.spawn(x=240, y=400, dmg=12, is_crit=False)
    assert len(layer.popups) == 1
    p = layer.popups[0]
    assert p.dmg == 12
    assert p.is_crit is False
    assert p.age == 0


def test_popup_ages_out_after_lifetime():
    layer = DamagePopupLayer()
    pygame.init()
    surface = pygame.Surface((480, 854))
    layer.spawn(x=240, y=400, dmg=5, is_crit=False)
    # Tick through full lifetime
    for _ in range(DamagePopupLayer.LIFETIME_FRAMES + 2):
        layer.update_and_render(surface)
    assert len(layer.popups) == 0


def test_popup_drifts_upward_over_lifetime():
    layer = DamagePopupLayer()
    pygame.init()
    surface = pygame.Surface((480, 854))
    layer.spawn(x=240, y=400, dmg=5, is_crit=False)
    starting_y = layer.popups[0].y
    # Tick half lifetime
    for _ in range(DamagePopupLayer.LIFETIME_FRAMES // 2):
        layer.update_and_render(surface)
    assert layer.popups[0].y < starting_y, "popup should drift upward (y decreases)"
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: ImportError (no `pixel_battle.engine.hud` yet).

- [ ] **Step 3: Create `pixel_battle/engine/hud.py`**

```python
"""HUD overlay: skill icons + DPS counter + damage popups + MP charge ring.

Pure rendering — owns no game logic. Driven by record_hit() calls from the
episode runner, plus reading Character state during render().
"""
from dataclasses import dataclass, field
from typing import List, Tuple

import math
import pygame

from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType


# ---------------------------------------------------------------------------
# Damage popup — floating "-N" text that scale-pops and drifts up
# ---------------------------------------------------------------------------


@dataclass
class DamagePopup:
    x: float
    y: float
    dmg: int
    is_crit: bool
    age: int = 0


class DamagePopupLayer:
    LIFETIME_FRAMES = 30
    RISE_PX = 60          # total upward drift over lifetime
    PEAK_SCALE = 1.4
    PEAK_FRAME = 6        # frames to reach peak scale, then settle

    def __init__(self):
        self.popups: List[DamagePopup] = []
        self._font: pygame.font.Font | None = None
        self._font_big: pygame.font.Font | None = None

    def _get_fonts(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 28)
            self._font_big = pygame.font.Font(None, 36)
        return self._font, self._font_big

    def spawn(self, x: float, y: float, dmg: int, is_crit: bool) -> None:
        self.popups.append(DamagePopup(x=x, y=y, dmg=dmg, is_crit=is_crit, age=0))

    def update_and_render(self, surface: pygame.Surface) -> None:
        font_small, font_big = self._get_fonts()
        survivors: List[DamagePopup] = []
        for p in self.popups:
            p.age += 1
            if p.age >= self.LIFETIME_FRAMES:
                continue
            # Drift up
            t = p.age / self.LIFETIME_FRAMES
            p.y = p.y - (self.RISE_PX / self.LIFETIME_FRAMES)
            # Scale-pop
            if p.age < self.PEAK_FRAME:
                scale = 1.0 + (self.PEAK_SCALE - 1.0) * (p.age / self.PEAK_FRAME)
            else:
                # Settle from PEAK_SCALE to 1.0 over next 8 frames, then hold
                settle_t = min(1.0, (p.age - self.PEAK_FRAME) / 8.0)
                scale = self.PEAK_SCALE - (self.PEAK_SCALE - 1.0) * settle_t
            alpha = max(0, int(255 * (1.0 - t)))
            color = (255, 90, 90) if p.is_crit else (255, 230, 90)
            text = f"-{p.dmg}!" if p.is_crit else f"-{p.dmg}"
            base_font = font_big if p.is_crit else font_small
            text_img = base_font.render(text, True, color)
            tw, th = text_img.get_size()
            sw = max(1, int(tw * scale))
            sh = max(1, int(th * scale))
            text_img = pygame.transform.smoothscale(text_img, (sw, sh))
            # Black shadow
            shadow = base_font.render(text, True, (0, 0, 0))
            shadow = pygame.transform.smoothscale(shadow, (sw, sh))
            shadow.set_alpha(alpha)
            text_img.set_alpha(alpha)
            surface.blit(shadow, (int(p.x - sw / 2 + 2), int(p.y - sh / 2 + 2)))
            surface.blit(text_img, (int(p.x - sw / 2), int(p.y - sh / 2)))
            survivors.append(p)
        self.popups = survivors
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/hud.py pixel_battle/tests/test_hud.py
git commit -m "feat(pixel-battle): HUD damage popup layer"
```

---

## Task 7: HUD module — `DPSCounter`

**Files:**
- Modify: `pixel_battle/engine/hud.py`
- Modify: `pixel_battle/tests/test_hud.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_hud.py`:

```python
from pixel_battle.engine.hud import DPSCounter


def test_dps_counter_empty_is_zero():
    c = DPSCounter()
    assert c.current_dps(now_ms=10_000) == 0.0


def test_dps_counter_single_hit():
    c = DPSCounter()
    c.record_hit(10, t_ms=5_000)
    # Window is 3s. Total dmg = 10, dps = 10/3 ≈ 3.33
    assert abs(c.current_dps(now_ms=5_100) - (10.0 / 3.0)) < 0.01


def test_dps_counter_drops_old_entries():
    c = DPSCounter()
    c.record_hit(10, t_ms=0)
    c.record_hit(20, t_ms=4_000)  # 4s later
    # At t=5_000, the first hit (t=0) is 5s old, outside 3s window
    dps = c.current_dps(now_ms=5_000)
    # Only the 20-dmg hit counts → 20/3 ≈ 6.67
    assert abs(dps - (20.0 / 3.0)) < 0.01


def test_dps_counter_multiple_hits_in_window():
    c = DPSCounter()
    c.record_hit(5, t_ms=2_000)
    c.record_hit(7, t_ms=3_000)
    c.record_hit(8, t_ms=4_000)
    # At t=4_500, all three within 3s window. Sum=20, dps=20/3 ≈ 6.67
    dps = c.current_dps(now_ms=4_500)
    assert abs(dps - (20.0 / 3.0)) < 0.01
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: 4 new tests FAIL (no `DPSCounter` yet).

- [ ] **Step 3: Append to `pixel_battle/engine/hud.py`**

Add at the end of the file:

```python
# ---------------------------------------------------------------------------
# DPS counter — rolling 3-second window of damage dealt
# ---------------------------------------------------------------------------


class DPSCounter:
    WINDOW_MS = 3000

    def __init__(self):
        # entries: list of (t_ms, dmg)
        self._entries: List[Tuple[int, int]] = []
        self._font: pygame.font.Font | None = None

    def _get_font(self) -> pygame.font.Font:
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 18)
        return self._font

    def record_hit(self, dmg: int, t_ms: int) -> None:
        self._entries.append((t_ms, dmg))
        self._prune(t_ms)

    def _prune(self, now_ms: int) -> None:
        cutoff = now_ms - self.WINDOW_MS
        self._entries = [(t, d) for (t, d) in self._entries if t > cutoff]

    def current_dps(self, now_ms: int) -> float:
        self._prune(now_ms)
        if not self._entries:
            return 0.0
        total = sum(d for _, d in self._entries)
        return total / (self.WINDOW_MS / 1000.0)

    def render(self, surface: pygame.Surface, x: int, y: int, now_ms: int) -> None:
        font = self._get_font()
        dps = self.current_dps(now_ms)
        text = f"DPS {dps:4.1f}"
        img = font.render(text, True, (255, 230, 150))
        shadow = font.render(text, True, (0, 0, 0))
        surface.blit(shadow, (x + 1, y + 1))
        surface.blit(img, (x, y))
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/hud.py pixel_battle/tests/test_hud.py
git commit -m "feat(pixel-battle): HUD DPS counter (3s rolling window)"
```

---

## Task 8: HUD module — `SkillIconBar` + `MPChargeRing`

**Files:**
- Modify: `pixel_battle/engine/hud.py`
- Modify: `pixel_battle/tests/test_hud.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_hud.py`:

```python
from pixel_battle.engine.character import Character
from pixel_battle.engine.hud import SkillIconBar, MPChargeRing


def test_skill_icon_bar_renders_without_error():
    pygame.init()
    pygame.font.init()
    surface = pygame.Surface((480, 854))
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    bar = SkillIconBar(c)
    bar.render(surface, x=10, y=750, now_ms=1000)
    # Smoke test: doesn't crash; bar has 2 slots (basic + cd)
    assert bar.num_slots == 2


def test_skill_icon_bar_cd_arc_progresses():
    """When skill is on cooldown, fill_ratio should be between 0 and 1."""
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    c.skill_cd_ready_at["screw_dart"] = 5000
    bar = SkillIconBar(c)
    # At now_ms=3000, 2000ms remain of 4000 cd, so fill = 2/4 = 0.5
    assert abs(bar._cd_fill_ratio("screw_dart", now_ms=3000) - 0.5) < 0.02
    # At now_ms=5000, no CD remaining
    assert bar._cd_fill_ratio("screw_dart", now_ms=5000) == 0.0


def test_mp_charge_ring_renders_when_mp_full():
    pygame.init()
    surface = pygame.Surface((480, 854))
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=120, facing=1)
    c.mp = c.mp_max
    ring = MPChargeRing()
    # Smoke test
    ring.render(surface, c, char_x=120, char_y=500, t_ms=2000)
    # When mp not full, render should no-op (no error)
    c.mp = 50
    ring.render(surface, c, char_x=120, char_y=500, t_ms=2000)
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: 3 new tests FAIL (no `SkillIconBar` / `MPChargeRing`).

- [ ] **Step 3: Append to `pixel_battle/engine/hud.py`**

```python
# ---------------------------------------------------------------------------
# Skill icon bar — shows basic + CD skill icons with CD arc countdown
# ---------------------------------------------------------------------------


_ICON_COLOR_BY_TYPE = {
    SkillType.BASIC:    (220, 220, 180),
    SkillType.COOLDOWN: ( 80, 180, 255),
    SkillType.SPECIAL:  (255, 140,  40),
    SkillType.ULTIMATE: (255,  80, 200),
}

_ICON_GLYPH_BY_TYPE = {
    SkillType.BASIC:    "B",
    SkillType.COOLDOWN: "C",
    SkillType.SPECIAL:  "S",
    SkillType.ULTIMATE: "U",
}


class SkillIconBar:
    """Renders icons for character's basic + CD skills (the two non-MP slots).
    Specials live in the MP bar, ultimate has its own indicator.
    """
    ICON_SIZE = 28
    ICON_GAP = 6

    def __init__(self, character: Character):
        self.character = character
        # Display the basic + first cooldown skill (if any)
        self._slots = []
        basics = character.skills_of_type(SkillType.BASIC)
        cooldowns = character.skills_of_type(SkillType.COOLDOWN)
        if basics:
            self._slots.append(basics[0])
        if cooldowns:
            self._slots.append(cooldowns[0])
        self._font: pygame.font.Font | None = None

    @property
    def num_slots(self) -> int:
        return len(self._slots)

    def _get_font(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 22)
        return self._font

    def _cd_fill_ratio(self, skill_id: str, now_ms: int) -> float:
        """0.0 = ready (no CD), 1.0 = just used (full CD remaining)."""
        ready_at = self.character.skill_cd_ready_at.get(skill_id, 0)
        skill = next((s for s in self._slots if s.id == skill_id), None)
        if skill is None or skill.cooldown_ms <= 0:
            return 0.0
        remaining = max(0, ready_at - now_ms)
        return min(1.0, remaining / skill.cooldown_ms)

    def render(self, surface: pygame.Surface, x: int, y: int, now_ms: int) -> None:
        font = self._get_font()
        for i, skill in enumerate(self._slots):
            icon_x = x + i * (self.ICON_SIZE + self.ICON_GAP)
            color = _ICON_COLOR_BY_TYPE.get(skill.skill_type, (200, 200, 200))
            # Background tile
            pygame.draw.rect(surface, (40, 40, 50),
                             (icon_x, y, self.ICON_SIZE, self.ICON_SIZE),
                             border_radius=4)
            pygame.draw.rect(surface, color,
                             (icon_x, y, self.ICON_SIZE, self.ICON_SIZE),
                             width=2, border_radius=4)
            glyph = _ICON_GLYPH_BY_TYPE.get(skill.skill_type, "?")
            img = font.render(glyph, True, color)
            rect = img.get_rect(center=(icon_x + self.ICON_SIZE // 2,
                                         y + self.ICON_SIZE // 2))
            surface.blit(img, rect)
            # CD arc overlay (darken portion still on CD)
            fill = self._cd_fill_ratio(skill.id, now_ms)
            if fill > 0.02:
                overlay = pygame.Surface((self.ICON_SIZE, self.ICON_SIZE),
                                          pygame.SRCALPHA)
                overlay.fill((0, 0, 0, int(180 * fill)))
                surface.blit(overlay, (icon_x, y))
                # Small countdown numerals (seconds)
                ready_at = self.character.skill_cd_ready_at.get(skill.id, 0)
                rem_s = max(0, (ready_at - now_ms) / 1000.0)
                cd_text = font.render(f"{rem_s:.1f}", True, (255, 255, 255))
                cd_rect = cd_text.get_rect(center=(icon_x + self.ICON_SIZE // 2,
                                                    y + self.ICON_SIZE // 2))
                surface.blit(cd_text, cd_rect)


# ---------------------------------------------------------------------------
# MP charge ring — 3 orbiting sparkles around character when MP == max
# ---------------------------------------------------------------------------


class MPChargeRing:
    NUM_SPARKLES = 3
    ORBIT_RADIUS_PX = 80
    ORBIT_PERIOD_MS = 1000   # one rotation per second

    def render(self, surface: pygame.Surface, char: Character,
               char_x: int, char_y: int, t_ms: int) -> None:
        if char.mp < char.mp_max:
            return
        for i in range(self.NUM_SPARKLES):
            phase = (t_ms / self.ORBIT_PERIOD_MS + i / self.NUM_SPARKLES) * 2 * math.pi
            sx = int(char_x + math.cos(phase) * self.ORBIT_RADIUS_PX)
            sy = int(char_y - 70 + math.sin(phase) * self.ORBIT_RADIUS_PX * 0.5)
            # Sparkle: small bright circle with halo
            halo = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(halo, (120, 200, 255, 90), (10, 10), 9)
            pygame.draw.circle(halo, (200, 230, 255, 200), (10, 10), 5)
            pygame.draw.circle(halo, (255, 255, 255, 255), (10, 10), 2)
            surface.blit(halo, (sx - 10, sy - 10))
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/hud.py pixel_battle/tests/test_hud.py
git commit -m "feat(pixel-battle): HUD skill icons + MP charge ring"
```

---

## Task 9: HUD module — `HUDOverlay` composer

**Files:**
- Modify: `pixel_battle/engine/hud.py`
- Modify: `pixel_battle/tests/test_hud.py`

- [ ] **Step 1: Write failing tests**

Append to `pixel_battle/tests/test_hud.py`:

```python
from pixel_battle.engine.hud import HUDOverlay


def test_hud_overlay_smoke():
    """HUDOverlay composes all sub-renderers without crashing."""
    pygame.init()
    surface = pygame.Surface((480, 854))
    left = Character.load("brick_phone")
    left.reset_physics(initial_x=120, facing=1)
    right = Character.load("glass_slab")
    right.reset_physics(initial_x=360, facing=-1)
    hud = HUDOverlay(left, right)
    hud.record_hit(actor_id="brick_phone", dmg=8, is_crit=False,
                    target_x=360, target_y=400, t_ms=1500)
    hud.render(surface, left, right, t_ms=2000)
    # No assert needed beyond "no exceptions"


def test_hud_overlay_routes_record_hit_by_actor():
    """record_hit appends to the correct character's DPS counter."""
    left = Character.load("brick_phone")
    left.reset_physics(initial_x=120, facing=1)
    right = Character.load("glass_slab")
    right.reset_physics(initial_x=360, facing=-1)
    hud = HUDOverlay(left, right)
    hud.record_hit(actor_id="brick_phone", dmg=10, is_crit=False,
                    target_x=360, target_y=400, t_ms=1000)
    assert hud.dps_left.current_dps(now_ms=1100) > 0.0
    assert hud.dps_right.current_dps(now_ms=1100) == 0.0
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: 2 new tests FAIL.

- [ ] **Step 3: Append to `pixel_battle/engine/hud.py`**

```python
# ---------------------------------------------------------------------------
# HUDOverlay — composes skill icons / DPS / damage popups / MP charge ring
# ---------------------------------------------------------------------------


class HUDOverlay:
    """Composes the four HUD sub-layers.

    Layout (renders in this order):
      1. MP charge ring (around each character if MP full)
      2. Damage popups (above defender's head)
      3. Skill icon bars + DPS at screen bottom corners
    """

    BOTTOM_BAR_Y = 780  # 480x854 surface; bottom 74px reserved for HUD
    SIDE_PAD = 12

    def __init__(self, left: Character, right: Character):
        self.left_id = left.id
        self.right_id = right.id
        self.icons_left = SkillIconBar(left)
        self.icons_right = SkillIconBar(right)
        self.dps_left = DPSCounter()
        self.dps_right = DPSCounter()
        self.popups = DamagePopupLayer()
        self.charge_ring = MPChargeRing()

    def record_hit(self, actor_id: str, dmg: int, is_crit: bool,
                    target_x: int, target_y: int, t_ms: int) -> None:
        if actor_id == self.left_id:
            self.dps_left.record_hit(dmg, t_ms)
        elif actor_id == self.right_id:
            self.dps_right.record_hit(dmg, t_ms)
        self.popups.spawn(target_x, target_y, dmg, is_crit)

    def render(self, surface: pygame.Surface,
               left: Character, right: Character, t_ms: int) -> None:
        # 1. MP charge rings around each char's world position
        self.charge_ring.render(surface, left,
                                 int(left.pos_x), int(left.pos_y), t_ms)
        self.charge_ring.render(surface, right,
                                 int(right.pos_x), int(right.pos_y), t_ms)
        # 2. Damage popups
        self.popups.update_and_render(surface)
        # 3. Bottom bar — icons + DPS
        self.icons_left.render(surface, x=self.SIDE_PAD,
                                y=self.BOTTOM_BAR_Y, now_ms=t_ms)
        self.dps_left.render(
            surface,
            x=self.SIDE_PAD,
            y=self.BOTTOM_BAR_Y + SkillIconBar.ICON_SIZE + 6,
            now_ms=t_ms,
        )
        right_bar_w = self.icons_right.num_slots * SkillIconBar.ICON_SIZE + \
                      (self.icons_right.num_slots - 1) * SkillIconBar.ICON_GAP
        right_x = surface.get_width() - self.SIDE_PAD - right_bar_w
        self.icons_right.render(surface, x=right_x,
                                 y=self.BOTTOM_BAR_Y, now_ms=t_ms)
        self.dps_right.render(
            surface,
            x=right_x,
            y=self.BOTTOM_BAR_Y + SkillIconBar.ICON_SIZE + 6,
            now_ms=t_ms,
        )
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_hud.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/hud.py pixel_battle/tests/test_hud.py
git commit -m "feat(pixel-battle): HUDOverlay composer"
```

---

## Task 10: Wire `HUDOverlay` into `Renderer.render_frame`

**Files:**
- Modify: `pixel_battle/engine/renderer.py`
- Modify: `pixel_battle/tests/test_renderer.py`

- [ ] **Step 1: Read current `test_renderer.py` and append a failing test**

Append to `pixel_battle/tests/test_renderer.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
from pixel_battle.engine.character import Character
from pixel_battle.engine.renderer import Renderer, AnimationState


def test_renderer_has_hud_after_init():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    assert r.hud is not None
    assert r.hud.left_id == "brick_phone"


def test_render_frame_with_hud_smoke():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    # record a hit through the HUD then render — should not crash
    r.hud.record_hit("brick_phone", dmg=7, is_crit=False,
                      target_x=360, target_y=400, t_ms=1500)
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=4, elapsed_ms=2000)
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
python -m pytest pixel_battle/tests/test_renderer.py -v
```
Expected: FAIL — `Renderer` has no `set_hud` / `render_frame` signature doesn't accept `elapsed_ms`.

- [ ] **Step 3: Edit `pixel_battle/engine/renderer.py`**

In `Renderer.__init__`, after `self.hit_stop_frames = 0`, add:
```python
        # HUD overlay is installed via set_hud() after Renderer is constructed,
        # since HUD needs Character references.
        self.hud = None
```

Add a new method right after `request_hit_stop`:

```python
    def set_hud(self, left: "Character", right: "Character") -> None:
        from pixel_battle.engine.hud import HUDOverlay
        self.hud = HUDOverlay(left, right)
```

Change the `render_frame` method signature — find:
```python
    def render_frame(
        self,
        left: Character,
        right: Character,
        left_anim: AnimationState,
        right_anim: AnimationState,
        anim_frame: int,
    ) -> None:
```

Replace with:
```python
    def render_frame(
        self,
        left: Character,
        right: Character,
        left_anim: AnimationState,
        right_anim: AnimationState,
        anim_frame: int,
        elapsed_ms: int = 0,
    ) -> None:
```

Then inside `render_frame`, find the line:
```python
        self.particles.update()
        self.particles.render(self.surface)
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

Replace with:
```python
        self.particles.update()
        self.particles.render(self.surface)
        # HUD overlay (skill icons, DPS, damage popups, MP charge ring)
        if self.hud is not None:
            self.hud.render(self.surface, left, right, elapsed_ms)
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_renderer.py pixel_battle/tests/test_hud.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/renderer.py pixel_battle/tests/test_renderer.py
git commit -m "feat(pixel-battle): Renderer renders HUD overlay each frame"
```

---

## Task 11: Episode runner — route HIT events to HUD + per-skill particle colors + per-skill hit-stop

**Files:**
- Modify: `pixel_battle/episodes/ep01_brick_vs_glass.py`

- [ ] **Step 1: Read episode runner main loop**

Already familiar — the HIT event handler is at `ep01_brick_vs_glass.py:286-296`. We'll insert color routing, HUD.record_hit, and per-skill hit-stop here.

- [ ] **Step 2: Edit `pixel_battle/episodes/ep01_brick_vs_glass.py`**

Near the top of the file (after the imports), add the color-routing map:

```python
_HIT_COLOR_BY_SKILL_TYPE = {
    "basic":    (220, 220, 180),   # white-yellow
    "cooldown": ( 80, 180, 255),   # cyan
    "special":  (255, 140,  40),   # orange
}
```

In `main()`, after the `renderer = Renderer()` line, add:
```python
    renderer.set_hud(left, right)
```

Find the HIT-event particle/shake block:
```python
            # Screen shake + particles + hit-stop
            if ev.type is EventType.HIT:
                # Use world position: mid-character height
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 80
                renderer.particles.emit_hit_burst(target_x, target_y)
                if ev.extra.get("crit"):
                    renderer.add_shake(8.0)
                    renderer.request_hit_stop(3)
                else:
                    renderer.add_shake(3.0)
                renderer.add_char_flash(ev.target, 1.0)
```

Replace with:
```python
            # Screen shake + particles + hit-stop + HUD record
            if ev.type is EventType.HIT:
                # Use world position: mid-character height
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 80
                st = ev.extra.get("skill_type", "basic")
                color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))
                count = 10 + int(ev.amount)
                speed = 6.0 + ev.amount * 0.2
                renderer.particles.emit_hit_burst(target_x, target_y,
                                                   color=color,
                                                   count=count, speed=speed)
                # Per-skill hit-stop
                if ev.extra.get("crit"):
                    renderer.add_shake(8.0)
                    renderer.request_hit_stop(4)
                elif st == "special":
                    renderer.add_shake(5.0)
                    renderer.request_hit_stop(3)
                elif st == "cooldown":
                    renderer.add_shake(4.0)
                    renderer.request_hit_stop(2)
                else:
                    renderer.add_shake(3.0)
                renderer.add_char_flash(ev.target, 1.0)
                # Record into HUD (popup + DPS)
                renderer.hud.record_hit(
                    actor_id=ev.actor,
                    dmg=ev.amount,
                    is_crit=bool(ev.extra.get("crit")),
                    target_x=target_x,
                    target_y=target_y,
                    t_ms=battle.elapsed_ms,
                )
```

Now find the `renderer.render_frame(...)` call (there are two — one in the main loop, one in the hold-final loop, and one in the result screen). The main loop call:
```python
            renderer.render_frame(left, right, la, ra, anim_frame=frame_no % 8)
```
Replace with:
```python
            renderer.render_frame(left, right, la, ra, anim_frame=frame_no % 8,
                                   elapsed_ms=battle.elapsed_ms)
```

The hold-final loop call:
```python
        renderer.render_frame(left, right, _animation_for_actor(left), _animation_for_actor(right), anim_frame=hold_frame)
```
Replace with (use the final battle.elapsed_ms so HUD shows steady state):
```python
        renderer.render_frame(left, right, _animation_for_actor(left), _animation_for_actor(right), anim_frame=hold_frame, elapsed_ms=battle.elapsed_ms)
```

- [ ] **Step 3: Run all tests to verify no regression**

```bash
python -m pytest pixel_battle/tests/ -v
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add pixel_battle/episodes/ep01_brick_vs_glass.py
git commit -m "feat(pixel-battle): episode runner routes HIT events to HUD + per-skill colors"
```

---

## Task 12: Visual regression — regenerate `final.mp4` and inspect

**Files:**
- Output: `pixel_battle/output/ep01_brick_vs_glass/final.mp4`

- [ ] **Step 1: Run the episode**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pixel_battle.episodes.ep01_brick_vs_glass
```
Expected: completes without error, prints output paths, writes `final.mp4`.

- [ ] **Step 2: Open and review the video**

```bash
open /Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/final.mp4
```

Visual checklist to confirm:
- [ ] Bottom-left and bottom-right corners show 2 skill icons each (B and C glyphs).
- [ ] CD icon visibly dims and shows a countdown number after each `screw_dart` / `shard_scatter` lands.
- [ ] Damage popups appear above defender's head on every hit, rise and fade.
- [ ] Basic hits emit white-yellow particles.
- [ ] CD-skill hits emit cyan particles.
- [ ] Special hits emit orange particles.
- [ ] When a character's MP fills to 100, 3 sparkles orbit around them.
- [ ] DPS number ticks visibly during exchanges.
- [ ] Match still completes in under 60 seconds (KO or timer).

- [ ] **Step 3: If anything looks off, leave it for the iteration pass**

User explicitly said "全力做 我們再來修正". Capture issues in a follow-up TODO list rather than fixing in this plan.

- [ ] **Step 4: Final commit**

There should be no code changes from this task unless something visibly broke. The regenerated `final.mp4` typically isn't tracked — verify:

```bash
git status
```
If `final.mp4` shows as modified (it's tracked), commit it:

```bash
git add pixel_battle/output/ep01_brick_vs_glass/final.mp4
git commit -m "render(pixel-battle): regenerate ep01 with P1 HUD/effects"
```

Otherwise skip — the video is a build artifact.

---

## Self-Review

**Spec coverage:**
- New skill type + fields → Tasks 1, 2, 3 ✓
- Battle AI priority + cooldown gating → Tasks 4, 5 ✓
- HUD module (5 classes) → Tasks 6, 7, 8, 9 ✓
- Renderer integration → Task 10 ✓
- Episode runner color routing + hit-stop + popup spawn → Task 11 ✓
- Visual regression → Task 12 ✓
- Out-of-scope items (SFX, banners, slow-mo, sprite frames) → not included by design ✓

**Placeholder scan:** No TBDs, every step has concrete code or commands.

**Type consistency:**
- `Skill.cooldown_ms` / `range` / `stagger_ms` — used consistently across tasks 1, 2, 4, 5, 8, 11
- `Character.skill_cd_ready_at` — dict[str, int], used in tasks 2, 4, 5, 8
- `Character.skill_off_cooldown(skill, now_ms)` — signature consistent across tasks 2, 5
- `HUDOverlay.record_hit(actor_id, dmg, is_crit, target_x, target_y, t_ms)` — signature consistent across tasks 9, 10, 11
- `Renderer.set_hud(left, right)` + `Renderer.render_frame(..., elapsed_ms=0)` — consistent across tasks 10, 11
- Particle color keys: `"basic"` / `"cooldown"` / `"special"` (lowercase, matching `SkillType.value`) — consistent across tasks 8, 11

No issues found.
