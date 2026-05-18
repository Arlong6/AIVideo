# Pixel Battle — P1 "Watchable Polish" Spec

**Date**: 2026-05-18
**Status**: Approved for implementation
**Trigger**: Friend feedback on `ep01_brick_vs_glass/final.mp4` — "都是打拳有點無聊", needs HUD data overlays and richer skill variety. Music/SFX explicitly deferred.

## Goal

Make the pixel-battle output **watchable on first viewing** by addressing three core gaps:

1. **Visual monotony** — every melee exchange looks the same. Add a new skill tier (cooldown-gated) and per-skill hit-effect colors so viewers can tell skills apart at a glance.
2. **Missing readable info** — no skill cooldown UI, no live damage rate. Add HUD layer with skill icons, CD arcs, and DPS counter.
3. **Lack of impact feedback** — hits read flat. Add damage popups, hit-stop on big hits, and a charged-MP particle ring.

Visual language target: **Smash Bros style** — color-coded particle rings, scale-pop damage popups, hit-stop on crit/special. Stays in current pixel-art aesthetic.

Out of scope:
- Music / SFX (deferred per user)
- Skill name banners, camera zoom, KO slow-mo (extras tier explicitly declined)
- Sprite animation frame count (P2 — separate session)

## Architecture

Existing engine has clean separation:
- `engine/battle.py` — pure logic, event log
- `engine/character.py`, `engine/skill.py` — data + runtime state
- `engine/renderer.py` — pygame Surface painter
- `engine/particles.py` — particle bursts
- `engine/cinematic.py` — ultimate cutscenes
- `episodes/ep01_brick_vs_glass.py` — wires everything, drives frame loop

This spec **adds one new module** (`engine/hud.py`) and **extends** the four marked files plus `data/characters.json`. No restructure.

### New module: `engine/hud.py`

Houses HUD-layer renderers as small classes, each owning its own state and `render(surface, ...)` method:

- `SkillIconBar` — draws skill icons + CD arc countdown for one character.
- `DPSCounter` — rolling 3-second damage window, renders live `X.X/s` number.
- `DamagePopupLayer` — spawn-and-update list of floating damage numbers.
- `MPChargeRing` — orbiting sparkles around character when MP full.

These are pure renderers — no Battle dependency beyond reading `Character` state and a small `record_hit(skill_id, dmg, is_crit, t_ms)` API.

## Data Model Changes

### `engine/skill.py`

```python
class SkillType(Enum):
    BASIC = "basic"
    COOLDOWN = "cooldown"   # NEW
    SPECIAL = "special"
    ULTIMATE = "ultimate"

@dataclass
class Skill:
    id: str
    skill_type: SkillType
    anim: str
    mp_cost: int = 0
    dmg: int = 0
    cooldown_ms: int = 0       # NEW — 0 = no CD (basic, MP-gated specials)
    range: str = "melee"       # NEW — "melee" or "special" (mapped to physics ranges)
    stagger_ms: int = 0        # NEW — extra stagger on hit (default = engine STAGGER_MS)
```

### `engine/character.py`

```python
@dataclass
class Character:
    # ...existing fields
    skill_cd_ready_at: dict[str, int] = field(default_factory=dict)

    def skill_off_cooldown(self, skill: Skill, now_ms: int) -> bool:
        return self.skill_cd_ready_at.get(skill.id, 0) <= now_ms
```

`reset_physics()` clears `skill_cd_ready_at`.

### `data/characters.json`

Add one COOLDOWN skill per character, slot between basic and special:

```jsonc
"brick_phone": {
  ...
  "skills": [
    {"id": "headbutt",      "type": "basic",    "anim": "attack"},
    {"id": "screw_dart",    "type": "cooldown", "cooldown_ms": 4000,
                             "dmg": 5, "range": "special", "anim": "screw_dart"},
    {"id": "snake_strike",  "type": "special", "mp_cost": 30, "dmg": 8,
                             "anim": "snake_strike"},
    {"id": "ringtone_blast","type": "special", "mp_cost": 25, "dmg": 6,
                             "anim": "ringtone_blast"},
    {"id": "indestructible_throw", "type": "ultimate", "mp_cost": 100, "dmg": 25,
                             "anim": "indestructible_throw"}
  ]
}

"glass_slab": {
  ...
  "skills": [
    {"id": "swipe",         "type": "basic",    "anim": "attack"},
    {"id": "shard_scatter", "type": "cooldown", "cooldown_ms": 4000,
                             "dmg": 4, "range": "special", "stagger_ms": 500,
                             "anim": "shard_scatter"},
    {"id": "ringtone_shock","type": "special", "mp_cost": 30, "dmg": 7,
                             "anim": "ringtone_shock"},
    {"id": "ad_popup_spam", "type": "special", "mp_cost": 25, "dmg": 6,
                             "anim": "ad_popup_spam"},
    {"id": "force_update",  "type": "ultimate", "mp_cost": 100, "dmg": 22,
                             "anim": "force_update"}
  ]
}
```

**Visual semantics** (no new sprite art required):
- Both skills use `"special_charge"` pose during attack windup (existing sprite).
- Hit lands at defender position with **cyan-blue particle burst** (distinct from basic's white-yellow and special's orange).
- `screw_dart` — landing fires cyan sparks + small dust kick at defender's feet.
- `shard_scatter` — landing fires cyan sparks + 500ms stagger (vs default 300ms) — visually reads as a heavier interrupt.
- Both use `range: "special"` so they connect from farther than basic melee range — gives the AI a reason to fire them at mid-distance instead of clinching.

## Battle Logic Changes

### AI skill choice (`Battle._start_attack`)

New priority order, applied per attack decision:

```python
def _choose_skill(char, opp, now_ms) -> Skill:
    # 1. CD skill (if off cooldown AND in range)
    cd_skills = char.skills_of_type(SkillType.COOLDOWN)
    for skill in cd_skills:
        if char.skill_off_cooldown(skill, now_ms):
            if self.rng.roll_check(0.70):
                return skill
    # 2. MP-gated special (if affordable)
    affordable = [s for s in char.skills_of_type(SkillType.SPECIAL)
                  if char.mp >= s.mp_cost]
    if affordable and self.rng.roll_check(0.40):
        return affordable[self.rng.randint(0, len(affordable) - 1)]
    # 3. Basic punch
    return char.skills_of_type(SkillType.BASIC)[0]
```

Ultimate is still triggered separately in `tick_ms` when MP=100 (unchanged).

### Hit resolution

`_resolve_attack_hit` extended:
- Use `skill.range` to pick MELEE_RANGE vs SPECIAL_RANGE
- After hit lands, set `attacker.skill_cd_ready_at[skill.id] = self.elapsed_ms + skill.cooldown_ms` (only when `cooldown_ms > 0`)
- Use `skill.stagger_ms or STAGGER_MS` for stagger duration
- Event `extra` dict now always includes `skill_id`, `skill_type`, `is_crit`, `dmg`

## Renderer Changes

### `engine/renderer.py`

**HUD bar repositioned to bottom**: HP/MP bars stay at top. New bottom bar (height 80px) hosts skill icons + DPS.

`Renderer.__init__` instantiates:
```python
self.hud = HUDOverlay(left_char_id, right_char_id)
```

`render_frame` calls `self.hud.render(surface, left, right, elapsed_ms)` after sprite blits, before screen shake.

### `engine/hud.py` (new)

```python
class SkillIconBar:
    """Per-character row: [basic_icon] [cd_icon]
    Icons are 28x28 colored squares with a 1-letter glyph and CD arc overlay."""
    def __init__(self, character: Character, color_map: dict): ...
    def render(self, surface, x: int, y: int, now_ms: int): ...

class DPSCounter:
    """Rolling damage record. window_ms = 3000.
    record_hit(dmg, t_ms) appends; render() shows current sum / 3.0."""
    WINDOW_MS = 3000
    def __init__(self): ...
    def record_hit(self, dmg: int, t_ms: int): ...
    def render(self, surface, x: int, y: int, label: str): ...

class DamagePopup:
    """One floating number."""
    x: float; y: float; dmg: int; is_crit: bool; age: int

class DamagePopupLayer:
    LIFETIME_FRAMES = 30
    def spawn(self, x, y, dmg, is_crit): ...
    def update_and_render(self, surface): ...

class MPChargeRing:
    """3 orbiting sparkles around a character when char.mp == mp_max."""
    def render(self, surface, char: Character, char_x: int, char_y: int, t_ms: int): ...

class HUDOverlay:
    """Composes the above."""
    def __init__(self, left_id: str, right_id: str): ...
    def record_hit(self, actor_id: str, dmg: int, is_crit: bool,
                    target_x: int, target_y: int, t_ms: int): ...
    def render(self, surface, left, right, t_ms: int): ...
```

### Particle color routing

Add `_HIT_COLOR_BY_TYPE` in episode runner:
```python
_HIT_COLOR_BY_TYPE = {
    "basic":    (220, 220, 180),  # white-yellow
    "cooldown": ( 80, 180, 255),  # cyan
    "special":  (255, 140,  40),  # orange
    # ultimate uses emit_ultimate_burst (existing, rainbow)
}
```

On HIT event, episode runner picks color from `event.extra["skill_type"]` and calls `renderer.particles.emit_hit_burst(x, y, color, count=10+dmg, speed=6.0)`.

### Hit-stop integration

Episode runner reads HIT event extra and calls:
```python
if event.extra.get("crit"):       renderer.request_hit_stop(4)
elif st == "special":             renderer.request_hit_stop(3)
elif st == "cooldown":            renderer.request_hit_stop(2)
# basic → no stop
```

Frame loop skips `battle.tick_ms()` while `renderer.hit_stop_frames > 0`; renderer still draws and decrements counter each frame.

## Episode Runner Changes

`episodes/ep01_brick_vs_glass.py` event-handling block, additions:

```python
for event in newly_emitted_events:
    if event.type is EventType.HIT:
        st = event.extra.get("skill_type", "basic")
        color = _HIT_COLOR_BY_TYPE.get(st, (220, 220, 180))
        target = left if event.target == left.id else right
        renderer.particles.emit_hit_burst(
            target.pos_x, target.pos_y - 80,
            color=color, count=10 + event.amount, speed=6.0 + event.amount * 0.2)
        renderer.hud.record_hit(event.actor, event.amount,
                                 event.extra.get("crit", False),
                                 target.pos_x, target.pos_y - 80, battle.elapsed_ms)
        if event.extra.get("crit"):       renderer.request_hit_stop(4)
        elif st == "special":             renderer.request_hit_stop(3)
        elif st == "cooldown":            renderer.request_hit_stop(2)
```

Frame loop becomes:
```python
if renderer.hit_stop_frames > 0:
    renderer.hit_stop_frames -= 1
else:
    battle.tick_ms(FRAME_MS)
# render always
renderer.render_frame(...)
recorder.add_frame(renderer.surface)
```

## Error Handling

Mostly N/A — this is a deterministic offline render. Defensive coding:
- `characters.json` schema: if new fields missing, defaults (`cooldown_ms=0`, `range="melee"`) keep existing behavior.
- AI never picks a CD skill that has no entry yet in `skill_cd_ready_at` — `.get(skill.id, 0)` defaults to 0 (always off-CD).
- DPS window prunes entries older than `WINDOW_MS` on each `record_hit` to bound memory.

## Testing

### Unit tests (new)

- `tests/test_skill_cooldown.py`
  - Off-cooldown CD skill is usable
  - On-cooldown CD skill is gated out of AI choice
  - Hit landing sets `skill_cd_ready_at` correctly
  - Cooldown clears on `reset_physics`
- `tests/test_hud_dps.py`
  - `DPSCounter` rolling window math (entries older than 3s drop out)
  - Empty window → 0.0/s
  - Single 10-dmg hit → 3.3/s
- `tests/test_battle_ai_priority.py`
  - Force RNG to confirm priority: ult > CD-off > special-affordable > basic
  - CD-on-cooldown falls through to special

### Visual regression

- Run `python -m pixel_battle.episodes.ep01_brick_vs_glass`
- Compare to current `final.mp4` — verify:
  - Skill icons visible at bottom of frame for both characters
  - DPS counter ticks during exchanges
  - CD arc visibly counts down after each CD skill use
  - Damage popups appear and rise on every hit
  - Cyan sparks for CD skills, orange for specials, white-yellow for basic
  - MP charge ring orbits character when MP=100

## Implementation Order

1. **Data + model** — `Skill.cooldown_ms/range/stagger_ms`, `Character.skill_cd_ready_at`, JSON update
2. **Battle** — AI priority, cooldown gating, event extras
3. **HUD module** — `engine/hud.py` with all 5 classes + unit tests
4. **Renderer wiring** — instantiate HUD, render call placement, repositioned bars
5. **Episode runner** — event handlers for color routing + hit-stop + popup spawn
6. **Visual run** — regenerate `ep01` final.mp4, diff and tune

Each step is testable in isolation. Steps 1-3 can land before any visual change is seen.

## Open Questions

None blocking — user approved "go full force, we'll iterate" 2026-05-18.

Tuning that may need a pass after visual run:
- CD value (4s) — may feel too rare or too spammy
- DPS window size (3s) — may need smoothing
- Hit-stop frame counts (2/3/4) — may need to halve or double
- Damage popup font size and rise distance
- MP charge ring particle count

All of these are single-constant changes; iterate after first watch.
