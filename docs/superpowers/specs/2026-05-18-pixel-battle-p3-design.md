# Pixel Battle — P3 VFX Spectacle Spec

**Date**: 2026-05-18
**Status**: Approved
**Trigger**: User feedback on P2 video — "招式只有把招式打出來 並沒有其他特效 / 應該是可以做一些遠攻特效 / 動作流暢度還是不夠 / 放大招可以加入特定音效"

## Goal

Make every CD-skill / special / ultimate moment visually big — attack windup gets a charge animation, projectiles leave trails, impacts get screen flash + impact rings + bigger particles. Sprite motion adds squash-and-stretch + body lean + jump tilt. Ultimates get distinct skill-specific SFX.

Explicit reframing from user: **「我們的目的不是為了輸贏，是為了那視覺效果」** — visual punch is the goal, not gameplay balance.

Out of scope for P3:
- Audio sync drift fix (deferred to P4) — user said "聲音徒步處理" (handle sound step-by-step)
- New sprite PNG assets — all motion stays procedural via pygame.transform
- Replacing AI with RL — separate project track

## Three blocks

### A. CD-skill / Special VFX upgrade (priority — biggest visual win)

**A1. Attack charge-up animation**

New module `pixel_battle/engine/charge_fx.py` (~60 lines):

```python
@dataclass
class ChargeEffect:
    x: float; y: float            # attacker's feet position
    color: Tuple[int, int, int]
    age: int = 0
    lifetime: int = 12             # ~200ms at 60fps, matches ATTACK_WINDUP_MS
    on_complete: Optional[Callable] = None  # called when age >= lifetime (muzzle flash)

class ChargeFXSystem:
    def spawn(self, x, y, color, on_complete=None) -> None: ...
    def update_and_render(self, surface: pygame.Surface) -> None: ...
```

Per-frame rendering:
- 6 small sparkles orbiting attacker's feet at angles `(2π * i/6 + age*0.3)` for i in [0,5]
- Orbit radius shrinks from 30px → 0 over `lifetime` (radius = 30 * (1 - age/lifetime))
- Sparkle color = skill color, alpha = 255 * (age/lifetime) (gets brighter as it converges)
- At `age == lifetime`: invoke `on_complete` (the muzzle flash trigger) and drop

Triggered from episode runner on CD-skill / special `EventType.HIT` events: spawn ChargeEffect at the attacker's position with color from `_HIT_COLOR_BY_SKILL_TYPE`. Wait — actually we get the HIT event AFTER the hit lands. The windup is BEFORE.

**Reality check**: Battle emits HIT events only at the START of the active phase, after windup completed. To pre-show the windup charge, we'd need either:
(a) A new `EventType.ATTACK_WINDUP` emitted at the start of attack windup
(b) Episode runner polls `char.action_state == "attacking"` + `attack_phase == "windup"` and detects skill type

(b) is intrusive (poll-based, repeated work). (a) is cleaner.

**Decision**: Add `EventType.ATTACK_WINDUP` to Battle (emitted when `_start_attack` runs for cooldown/special skills). Episode runner handles this event → spawns ChargeEffect.

```python
# In Battle._start_attack, after attack_used_kind / phase set:
if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
    self._emit(EventType.ATTACK_WINDUP, actor=char.id,
               extra={"skill_id": skill.id, "skill_type": skill.skill_type.value})
```

Episode runner:
```python
elif ev.type is EventType.ATTACK_WINDUP:
    actor = left if ev.actor == left.id else right
    st = ev.extra.get("skill_type", "basic")
    color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))
    renderer.charge_fx.spawn(x=int(actor.pos_x), y=int(actor.pos_y),
                              color=color)
```

The `on_complete` callback is left None for now (the actual muzzle flash happens implicitly when the projectile spawns from `EventType.HIT` 200ms later).

**A2. Projectile trail**

Modify `engine/projectile.py::ProjectileSystem.update`:
- Each frame, before lerping main projectile, spawn a trail particle at the projectile's CURRENT position
- Trail particles use the existing `ParticleSystem` (we already inject one — but Projectile doesn't have direct access). Instead, give `ProjectileSystem` an optional `trail_callback: Callable[[float, float, tuple], None]` that the renderer wires to `particles.emit_hit_burst(x, y, color=color, count=1, speed=0.5)` (a single weak particle).

Simpler: add `trail_particles: List[TrailParticle]` directly inside ProjectileSystem; each is a small fading dot. Self-contained, no cross-module coupling.

```python
@dataclass
class TrailParticle:
    x: float; y: float
    color: Tuple[int, int, int]
    age: int = 0
    lifetime: int = 8  # short trail
```

In `ProjectileSystem.update`:
```python
for p in self.projectiles:
    if p.age % 2 == 0:  # spawn trail every 2 frames
        self.trails.append(TrailParticle(x=p.x, y=p.y, color=p.color))
    # ... existing lerp logic ...

# Age trail particles + drop expired
self.trails = [t for t in self.trails if (t.age := t.age + 1) < t.lifetime]
```

In `render`:
```python
for t in self.trails:
    alpha = int(180 * (1.0 - t.age / t.lifetime))
    radius = max(1, 4 - t.age // 2)
    tmp = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    pygame.draw.circle(tmp, (*t.color, alpha), (radius + 1, radius + 1), radius)
    surface.blit(tmp, (int(t.x - radius), int(t.y - radius)))
```

**A3. Impact upgrade**

New `ImpactRing` system. Could live in `engine/projectile.py` (since impact follows projectile) or a new `engine/impact_fx.py` module. To keep modules tight, **put it in `engine/impact_fx.py`**.

```python
@dataclass
class ImpactRing:
    x: float; y: float
    color: Tuple[int, int, int]
    age: int = 0
    lifetime: int = 8       # ~130ms at 60fps
    max_radius: int = 60

class ImpactFXSystem:
    def __init__(self):
        self.rings: List[ImpactRing] = []

    def spawn_ring(self, x, y, color) -> None: ...

    def request_screen_flash(self, color, alpha=80, frames=4) -> None: ...

    def update_and_render(self, surface) -> None:
        # Draw expanding rings + screen-wide flash if pending
        ...
```

Screen flash:
```python
def update_and_render(self, surface):
    # 1. Rings
    survivors = []
    for r in self.rings:
        r.age += 1
        if r.age >= r.lifetime:
            continue
        t = r.age / r.lifetime
        radius = int(r.max_radius * t)
        alpha = int(200 * (1 - t))
        layer = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*r.color, alpha), (radius + 2, radius + 2),
                            radius, width=3)
        surface.blit(layer, (int(r.x - radius), int(r.y - radius)))
        survivors.append(r)
    self.rings = survivors

    # 2. Screen flash
    if self._flash_frames_remaining > 0:
        flash = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        flash.fill((*self._flash_color, self._flash_alpha))
        surface.blit(flash, (0, 0))
        self._flash_frames_remaining -= 1
```

Particle count multiplier in episode runner's `_land_callback`: change `1.8` → `2.5`. Hit-stop frames: CD-skill 2 → 3.

**A4. Banner upgrades**

Modify `engine/banner.py`:
- `FONT_SIZE = 48` → `64`
- Add white outline: render text 4 times at (-2,0),(2,0),(0,-2),(0,2) offsets in white before drawing main color text on top
- `SLIDE_IN_FRAMES = 10` → `8`
- `FADE_OUT_START = 26` → `30` (longer hold)
- `LIFETIME_FRAMES = 36` → `42`

### B. Ultimate-specific SFX

Use **numpy procedural generation** (chosen B-2 from proposal).

**B1. New script** `scripts/gen_ult_sfx.py`:
- Loads numpy + writes WAV via scipy.io.wavfile (or stdlib `wave` + struct)
- Two SFX, 44.1kHz mono, 16-bit:
  - `indestructible_throw.wav` — metallic clang: 880Hz triangle wave + noise burst envelope + 0.6s exponential decay
  - `force_update.wav` — glass shatter + system error: white noise 0.1s + downward sweep 1500→200Hz + 3 square-wave beep pulses

Generated files saved to `pixel_battle/assets/sfx/`.

**B2. compose.py changes**

Modify `_load_sfx` to fail gracefully:
```python
def _load_sfx_or_none(name: str) -> Optional[AudioSegment]:
    path = SFX_DIR / f"{name}.wav"
    if not path.exists():
        return None
    return AudioSegment.from_file(path)
```

In the ULTIMATE_START handler:
```python
elif ev.type is EventType.ULTIMATE_START:
    charge_pos = max(0, pos - 600)
    charge_sfx = _load_sfx_or_none("charge")
    if charge_sfx:
        track = track.overlay(charge_sfx, position=charge_pos)
    # Try skill-specific ult SFX first, fall back to generic
    skill_id = ev.extra.get("skill_id", "")
    specific = _load_sfx_or_none(skill_id)
    fallback = _load_sfx_or_none("ultimate")
    sfx = specific if specific else fallback
    if sfx:
        track = track.overlay(sfx, position=pos)
```

### C. Sprite fluidity boost

All changes inside `engine/renderer.py::_draw_sprite_char` + `engine/renderer.py` top-level helpers.

**C1. Walk enhancement**
- Walk bob amplitude `3` → `5`
- New helper `_walk_lean_angle(anim_frame) -> float`: `math.sin(anim_frame * 0.6) * 3.0` (degrees)
- Rotate sprite by lean angle when WALKING: `sprite = pygame.transform.rotate(sprite, lean_deg * char.facing)` — facing flips lean direction so the character leans into walk direction
- Dust step particles: every 12 frames during walking, spawn a small light-brown circle particle at character's feet via `renderer.particles.emit_hit_burst(x=feet_x, y=feet_y, color=(160,130,100), count=2, speed=2.0)`

**C2. Attack scale-pop**
- During `ATTACK` clip's strike phase only (frames 8-11 of the 22-frame clip), apply scale `1.0 → 1.15 → 1.0`
- New helper `_attack_scale(anim_frame, clip_def) -> float`:
  ```python
  def _attack_scale(anim_frame: int) -> float:
      strike_start = 8  # after 8-frame windup
      strike_len = 4
      if not (strike_start <= anim_frame < strike_start + strike_len):
          return 1.0
      t = (anim_frame - strike_start) / strike_len  # 0..1
      # Triangle wave: 0 → 1 at t=0.5 → 0 at t=1
      tri = 1.0 - abs(t * 2 - 1)  # peaks at 0.5
      return 1.0 + 0.15 * tri
  ```
- In `_draw_sprite_char`: when `anim_state is AnimationState.ATTACK`, scale sprite by `_attack_scale(anim_frame)` before blit (preserves feet position — use `pygame.transform.smoothscale` to new size, anchor midbottom).

**C3. Hit-stagger squash**
- During first 4 frames of HIT clip: vertical scale 0.85 (squash flat from being hit)
- New helper `_hit_squash_scale(anim_frame) -> Tuple[float, float]` returns (sx, sy):
  ```python
  def _hit_squash_scale(anim_frame: int) -> Tuple[float, float]:
      if anim_frame < 4:
          return (1.05, 0.85)
      return (1.0, 1.0)
  ```
- Apply only when `anim_state is AnimationState.HIT`.

**C4. Jump tilt**
- When `anim_state is AnimationState.JUMPING`:
  - During upward phase (vel_y < 0 in screen coords, i.e., rising): tilt `-8° * facing` (leans into the rise)
  - During falling phase (vel_y >= 0): tilt `+8° * facing`
- Need access to `char.vel_y` from inside `_draw_sprite_char` (already passes `char`). Compute tilt inline.

## Architecture

Three new modules, each small and single-purpose:
- `pixel_battle/engine/charge_fx.py` — `ChargeEffect` + `ChargeFXSystem`
- `pixel_battle/engine/impact_fx.py` — `ImpactRing` + `ImpactFXSystem`
- `pixel_battle/engine/projectile.py` — extended with `TrailParticle` + `trails` list

One new event type in `engine/battle.py`:
- `EventType.ATTACK_WINDUP` — emitted by `Battle._start_attack` for non-basic skills

One new generator script:
- `scripts/gen_ult_sfx.py` — runs once to produce 2 new WAVs

Touched existing files:
- `engine/renderer.py` — instantiate ChargeFXSystem + ImpactFXSystem; render them in chain; add walk/attack/hit/jump sprite transform logic; expose dust step emission
- `engine/banner.py` — bigger font, white outline, longer hold/lifetime
- `engine/projectile.py` — add `trails` mechanism
- `engine/battle.py` — emit ATTACK_WINDUP
- `episodes/ep01_brick_vs_glass.py` — handle ATTACK_WINDUP event; spawn impact ring + screen flash on CD/special HIT; bump particle multiplier to 2.5×; bump CD hit-stop to 3 frames
- `video/compose.py` — graceful SFX loading + skill-specific ultimate lookup

## Data flow

```
Battle._start_attack (skill_type ∈ {COOLDOWN, SPECIAL})
  → emits ATTACK_WINDUP event with skill_id + skill_type

Episode runner consumes ATTACK_WINDUP
  → renderer.charge_fx.spawn(x=attacker_x, y=attacker_y, color=skill_color)

Battle._resolve_attack_hit fires
  → emits HIT event (existing)

Episode runner consumes HIT (cooldown/special):
  → renderer.projectiles.spawn(... lifetime=8, on_land=land_cb)
  → renderer.banners.spawn(skill_name, color)
  → renderer.hud.record_hit(...)  [existing]

Projectile lerps for 8 frames, trailing TrailParticles each tick

projectile.on_land fires:
  → particles.emit_hit_burst(..., count=2.5x_base, speed=...)
  → impact_fx.spawn_ring(target_x, target_y, color)
  → impact_fx.request_screen_flash(color, alpha=80, frames=4)
  → renderer.add_shake(4.0)
  → renderer.request_hit_stop(3)   # bumped from 2
  → renderer.add_char_flash(target, 1.0)

Renderer.render_frame draw chain:
  bg → bars → sprites → charge_fx.update_and_render
  → particles → projectiles (incl. trails) → impact_fx.update_and_render (rings)
  → HUD → banners → impact_fx screen flash (drawn last for max impact)
  → screen shake (composited surface)
```

## Error handling

- Missing SFX file → `_load_sfx_or_none` returns None, compose silently skips. No crash.
- `ChargeFXSystem` / `ImpactFXSystem` empty state → render is a no-op.
- `EventType.ATTACK_WINDUP` for chars not in event handler → defensive `if actor` check.
- Hit-stop while charge fx is animating → `ChargeFXSystem.update_and_render` should still age even when battle is paused (so animation doesn't freeze mid-charge). Confirm runner behavior: when hit-stop is active, `renderer.render_frame` IS called (just battle tick is skipped). So charge_fx ages normally. Good.

## Testing

### Unit tests (new)

- `tests/test_charge_fx.py`
  - spawn adds to list
  - update advances age, radius shrinks toward 0
  - aged-out effects are removed
  - on_complete fires once at lifetime
- `tests/test_impact_fx.py`
  - spawn_ring adds; rings expand each tick
  - screen flash decays alpha or frames; cannot stack same color twice → newer call replaces
  - aged-out rings dropped
- `tests/test_projectile_trail.py`
  - trails spawn at projectile position every N frames
  - trails age and drop
- `tests/test_battle_attack_windup_event.py`
  - When `_start_attack` runs with cooldown/special skill, emits ATTACK_WINDUP event
  - When basic skill, no ATTACK_WINDUP event
  - Event extra includes skill_id, skill_type

### Integration

- `tests/test_battle_no_lock.py` (existing P2 test) — should still pass
- `tests/test_renderer.py` — add smoke test that render_frame works with charge/impact systems active

### Visual regression

Re-run `python -m pixel_battle.episodes.ep01_brick_vs_glass`. Confirm visually:
- Before CD/special hits, swirling sparkles converge on attacker
- Projectiles leave fading trails
- On impact: expanding ring + brief screen-color flash
- Skill banner text is bigger with white outline
- Walking characters lean side-to-side as they bob
- Attacks visibly squash/stretch sprite
- Jumps tilt sprite forward/back
- Ult sound differs between brick (clang) and glass (shatter)

## Implementation order

1. **B (Ult SFX procedural gen)** — fastest delivery, zero dependencies, ship as Task 1
2. **A1 ChargeFX module + ATTACK_WINDUP event + episode wiring**
3. **A2 Projectile trail** (modifies existing projectile.py)
4. **A3 ImpactFX module + episode integration (rings + screen flash)**
5. **A4 Banner upgrades** (small)
6. **C1 Walk lean + dust** (modifies renderer)
7. **C2 Attack scale-pop** (modifies renderer)
8. **C3 Hit squash** (modifies renderer)
9. **C4 Jump tilt** (modifies renderer)
10. **Visual regression** — regenerate final.mp4, eyeball

Each step is testable in isolation. Visual regression at end consolidates all of them.

## Out of scope

- Audio sync drift fix (P4) — needs video-time tracking, separate work
- New sprite PNG assets — all sprite-side changes use `pygame.transform`
- RL AI — separate spec track
- Multi-banner queue (still single active banner)
- New screen-wide cinematic effects beyond brief impact flash

## Tuning knobs

Single-constant changes for post-render iteration:
- ChargeEffect: `lifetime=12`, `orbit_radius_start=30`, `sparkle_count=6`
- TrailParticle: `lifetime=8`, spawn every `2` frames, `radius_decay=2`
- ImpactRing: `lifetime=8`, `max_radius=60`, `ring_alpha=200`
- Screen flash: `alpha=80`, `frames=4`
- Particle count multiplier on CD impact: `2.5×`
- Banner: `FONT_SIZE=64`, `LIFETIME_FRAMES=42`, `FADE_OUT_START=30`
- Walk lean: `5px bob` + `3° rotate`
- Attack scale-pop: `1.15` peak, `4` frames
- Hit squash: `(1.05, 0.85)`, `4` frames
- Jump tilt: `±8°` rise/fall threshold = `vel_y == 0`

All exposed as named module constants.
