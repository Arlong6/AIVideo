# Pixel Battle — P2 Polish Iteration Spec

**Date**: 2026-05-18
**Status**: Approved
**Trigger**: User feedback after P1 video review — "後面站著不動 / 小招式看不到 / 動作流暢度不夠"

## Goal

Close three gaps that surfaced in the P1 render of `ep01_brick_vs_glass/final.mp4`:

1. **AI lock-up at 36s** — both characters get stuck in defensive retreat against opposite walls for the remaining 23 seconds of the match.
2. **CD-skill visually invisible** — engine fires `screw_dart` × 5 and `shard_scatter` × 3, but they share the basic attack sprite + nearly identical particles, so viewers don't notice.
3. **Action stiffness** — sprite poses snap between keyframes; walking is just translation with no body motion; attack lunge feels flat.

Note: RL-trained AI is the long-term cure for issue (1) but is out of scope for this spec — a separate spec will design that track. P2 is a heuristic patch + visual polish so the immediate video iteration is watchable.

## Diagnosis (evidence from P1 render)

From `battle_events.json`:
- 21 HIT events, 9 MISS, 4 CRIT, 2 ULTIMATE_START/END
- CD-skill HITs: 8 (5 screw_dart, 3 shard_scatter) — mechanic works
- **Last event at t=36.4s; match runs to 60s timeout → 23.6s of zero events**
- After both ultimates fire (~11.5s and ~21s), both characters have HP < 30 and MP regenerates above 70% (from being hit), triggering simultaneous defensive retreat. Both walk to opposite arena walls, `clamp_x` pins them, AI keeps re-triggering retreat each tick.

## Scope — three blocks

### A. Retreat lock fix

Three changes in `engine/battle.py::_ai_choose_action`:

**A1. HP threshold 30 → 15**
Defensive retreat condition:
```python
if char.hp < 15 and opp.mp >= opp.mp_max * 0.7:
    self._start_retreat(char, opp)
    return
```
Fewer mutual-retreat collisions when both are low.

**A2. Retreat timer**
Add `Character.retreat_until_ms: int = 0` field. `_start_retreat` sets `char.retreat_until_ms = self.elapsed_ms + 800`. In `_ai_choose_action`, before the early-return for `action_state == "walking"`, check: if `char.retreat_until_ms > 0 and self.elapsed_ms > char.retreat_until_ms`, force `char.retreat_until_ms = 0` and skip the retreat branches this tick.

**A3. Wall-stuck guard**
Before each retreat trigger, check `if abs(char.pos_x - ARENA_LEFT) < 30 or abs(char.pos_x - ARENA_RIGHT) < 30: skip retreat, fall through to attack`. Prevents stick-against-wall pattern.

### B. CD-skill visual distinction

No new PNG sprite art. All procedural in pygame.

**B1. Projectile system** — new `engine/projectile.py` (~80 lines)
```python
@dataclass
class Projectile:
    x: float; y: float
    vx: float; vy: float
    shape: str          # "screw" or "shard"
    color: tuple[int, int, int]
    age: int = 0
    lifetime: int = 18  # ~0.3s at 60fps
    on_land: Optional[Callable] = None  # called once when age reaches lifetime

class ProjectileSystem:
    def update(self) -> None: ...   # age, motion, fire on_land at lifetime
    def render(self, surface) -> None: ...
    def spawn(self, ...) -> None: ...
```

Drawing per shape:
- `"screw"`: 6×3 px gray rect rotating at 0.4 rad/frame, plus 2 diagonal black lines (threads). Spawned with vx toward target, vy=0.
- `"shard"`: 3 semi-transparent triangles fanning out (different angles ±15°), light-blue. Each triangle is 8×4 px.

Renderer integration: `Renderer.__init__` adds `self.projectiles = ProjectileSystem()`. `render_frame` calls `self.projectiles.update()` and `self.projectiles.render(self.surface)` between particles and HUD.

**B2. Projectile spawn on CD-skill HIT** — modify `episodes/ep01_brick_vs_glass.py`

Currently, on `EventType.HIT` with skill_type=cooldown, the runner emits particles at defender position immediately. We want the projectile to read "thing flew across the screen and hit them," so we **defer the particle burst to `projectile.on_land`** instead of firing it at HIT time.

Episode-runner pseudo-flow on `EventType.HIT` with `skill_type == "cooldown"`:
```python
def land_callback():
    renderer.particles.emit_hit_burst(target_x, target_y, color=cyan,
                                       count=..., speed=...)
    renderer.add_shake(4.0)
    renderer.request_hit_stop(2)

renderer.projectiles.spawn(
    x_start=attacker.pos_x, y_start=attacker.pos_y - 80,
    x_end=target_x, y_end=target_y,
    shape="screw" if skill_id == "screw_dart" else "shard",
    color=(80, 180, 255),
    lifetime=8,                 # ~0.13s at 60fps
    on_land=land_callback,
)
# damage popup, DPS, char flash still fire immediately on HIT
renderer.hud.record_hit(...)
renderer.add_char_flash(ev.target, 1.0)
```

For non-cooldown HITs (basic, special), keep the existing immediate particle/shake/hit-stop path unchanged.

Projectile motion = linear lerp from start to end over `lifetime` frames (no gravity, no arc — keep it simple). `on_land` fires once when `age >= lifetime`.

**B3. Skill banner system** — new `engine/banner.py` (~40 lines)
```python
@dataclass
class Banner:
    text: str
    color: tuple
    age: int = 0
    lifetime: int = 36  # 0.6s
    x_start: int = -200
    x_end: int = 240    # screen center

class BannerSystem:
    def spawn(self, text: str, color: tuple) -> None: ...
    def update_and_render(self, surface) -> None: ...
```

Banner motion:
- Frames 0-10: x lerps from -200 → 240 (slide in from left)
- Frames 10-26: hold at center
- Frames 26-36: fade alpha 255 → 0
- Font: pygame default size 48, bold-feel via shadow + outline

Triggers (from episode runner):
- CD-skill HIT: `"SCREW DART!"` / `"SHARD SCATTER!"` (cyan-blue)
- Special HIT: `"SNAKE STRIKE!"` / `"RINGTONE SHOCK!"` / etc. (orange)
- ULTIMATE_START: keep existing CRITICAL HIT! caption pattern (don't double-banner)

Renderer integration: `Renderer.__init__` adds `self.banners = BannerSystem()`. Episode runner spawns banners; renderer calls update_and_render after HUD.

**B4. CD-skill particle scaling** — modify episode runner

For `EventType.HIT` with skill_type=cooldown, multiply particle count by 1.8 and speed by 1.3:
```python
elif st == "cooldown":
    count = int((10 + ev.amount) * 1.8)
    speed = (6.0 + ev.amount * 0.2) * 1.3
```

### C. Action fluidity

**C1. Walk bob** — modify `engine/renderer.py::_draw_sprite_char`

When `anim_state is AnimationState.WALKING`, before blitting, compute `bob_offset = int(math.sin(anim_frame * 0.6) * 3)` and shift sprite y by `bob_offset`. ±3px sinusoidal motion at ~10 Hz reads as walking.

**C2. Attack timing rebalance** — modify `engine/animator.py::CLIP_DEFINITIONS`

```python
AnimClip.ATTACK: [("attack_windup", 8), ("attack_strike", 4), ("attack_recover", 10)],
```
(Was 6/6/6 — total 18 frames, same total duration but more weight on windup/recover, which are the "anticipation" and "follow-through" frames where character should be visible.)

Note: this changes anim timing but Battle's `ATTACK_WINDUP_MS / ATTACK_ACTIVE_MS / ATTACK_RECOVER_MS` constants stay (they govern hit-resolution timing, not sprite playback). The new ratio gives sprite-side breathing room.

**C3. Attack recoil** — modify `engine/battle.py::_resolve_attack_hit`

After hit lands, add to attacker (just before the `self._emit(EventType.HIT, ...)` line):
```python
recoil_dir = -1 if attacker.pos_x < defender.pos_x else 1
attacker.vel_x = recoil_dir * 1.5
```
Existing friction (`* 0.7` per frame) decays it in ~10 frames. Reads as "punch reaction force."

## Architecture

Two new modules. Both small, single-purpose, isolated from Battle logic:

- `engine/projectile.py` — `Projectile` dataclass + `ProjectileSystem` (spawn/update/render). Consumed by Renderer + episode runner.
- `engine/banner.py` — `Banner` dataclass + `BannerSystem` (spawn/update_and_render). Consumed by Renderer + episode runner.

These mirror the existing `engine/particles.py` design — pure rendering, no Battle dependency, owned by `Renderer.__init__`.

Other changes are surgical edits inside existing modules (battle.py / animator.py / renderer.py / episodes/ep01).

## Data flow

```
Battle.tick_ms()
  → emits HIT event with extra={skill_type, skill_id, crit, ...}
  → emits action_state changes (attacking → walking → idle)

Episode runner (consumes events)
  → on HIT(cooldown): projectiles.spawn(attacker→defender, shape, color)
  → on HIT(cooldown|special|ultimate): banners.spawn(SKILL_NAME, color)
  → on HIT(cooldown): hud.record_hit(...)  [already wired in P1]
  → on HIT(any): particles.emit_hit_burst(...) [already wired]

Renderer.render_frame()
  → existing draw chain (bg, bars, sprites)
  → particles.update + render [existing]
  → projectiles.update + render [NEW]
  → hud.render [existing]
  → banners.update_and_render [NEW]
  → apply_shake [existing]
```

## Error handling

Mostly N/A — deterministic offline render. Defensive coding:
- `ProjectileSystem.update` skips entries past lifetime (no leak)
- `BannerSystem` caps to one banner active at a time — newer spawn replaces older
- `_ai_choose_action` retreat timer: if `retreat_until_ms` is 0 (default), no retreat logic change; if > 0 and elapsed, clears itself

## Testing

### Unit tests (new)

- `tests/test_projectile.py`
  - spawn adds to list
  - update advances position based on vx/vy
  - on_land callback fires exactly once at lifetime
  - aged-out projectiles are removed
- `tests/test_banner.py`
  - spawn appends banner
  - update advances age
  - banners past lifetime are dropped
  - x position lerps correctly across 3 phases
- `tests/test_ai_retreat_lock.py`
  - When both chars have HP < 30 and MP > 70%, repeated `_ai_choose_action` ticks do NOT keep them stuck in retreat past 800ms
  - Wall-stuck char skips retreat and attacks instead
  - Retreat timer expires correctly

### Integration test

- `tests/test_battle_no_lock.py` — run 60s simulated battle, assert that the longest event-free gap (excluding cinematics) is < 5s. This catches lock regressions even if the specific retreat fixes are bypassed by some other heuristic change.

### Visual regression

Re-run `python -m pixel_battle.episodes.ep01_brick_vs_glass`. Confirm:
- No 5+ second dead zones
- Projectiles visibly fly when CD skills fire
- Skill banners read at center of screen
- Walk has visible up/down bob
- Attack visibly winds up (frame longer at windup pose) and recovers (frame longer at recover pose)
- Match runs to KO (not draw) in under 60s

## Implementation order

1. **A1+A2+A3 retreat fix + unit tests** — lowest risk, biggest dead-zone payoff
2. **C1 walk bob + C3 recoil** — single-line edits, immediate fluidity win
3. **C2 attack timing rebalance** — single dict edit
4. **B1 projectile module + unit tests**
5. **B3 banner module + unit tests**
6. **B2+B4 episode runner: spawn projectiles + banners on HIT, scale CD particles**
7. **Visual regression run + tune**

Steps 1-3 deliver biggest user-facing wins fastest. Steps 4-6 add the visual punch. Each step commits independently.

## Out of scope

- New sprite PNG generation (requires asset pipeline — separate work)
- Per-character custom banner fonts / colors beyond the skill-type tiers
- Cinematic-quality projectile physics (real arc, ricochet, etc.) — current = simple lerp tracer
- Replacing AI with RL — covered in a future separate spec
- Music / SFX — still deferred from P1

## Tuning knobs (single-constant changes for post-render iteration)

- Retreat HP threshold (`15`)
- Retreat timer duration (`800ms`)
- Wall-stuck zone (`30px`)
- Walk bob amplitude (`3px`)
- Walk bob frequency (`0.6 rad/frame`)
- Banner lifetime (`36 frames`)
- Banner x_end (`240px`)
- Attack timing split (`8/4/10`)
- Recoil velocity (`1.5 px/frame`)
- CD particle multipliers (count `1.8x`, speed `1.3x`)
- Projectile lifetime for CD-skill (`8 frames`)

All exposed as named constants in their respective modules.
