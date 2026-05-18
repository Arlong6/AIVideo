# Pixel Battle — P4 Spacing + Audio Sync + Cast Spectacle Spec

**Date**: 2026-05-19
**Status**: Approved
**Trigger**: User feedback on P3 video — "兩個角色過度重疊 / 施放技能時可以拉開空間 / 音效還是有些沒對到 / 表現可以再華麗一點 / 施展的時候可以再多點音效"

## Goal

Fix four pain points that survived P3:
1. **Character overlap** — sprites stack on each other so skill effects are invisible.
2. **Audio drift** — accumulated hit-stop frames push video behind battle-time, so SFX play earlier than the visual.
3. **Missing cast SFX** — only ultimates have skill-specific sound; CD/special skills cast silently.
4. **Cast performance is flat** — release moment lacks visual punctuation.

## Four blocks

### A. Character spacing — no overlap + cast-time pushback

**A1. Physical collision in `_update_physics`**

In `engine/battle.py`, after both characters' physics update each tick, add a collision resolution pass:

```python
MIN_CHAR_DISTANCE = 70  # px; sprite ~60px wide + 10px buffer

def _resolve_character_collision(self) -> None:
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
```

Call from `tick_ms` after the two `_update_physics` calls.

**A2. AI maintains comfortable melee distance**

Current `_ai_choose_action`:
```python
if distance > MELEE_RANGE * 0.8:
    self._start_walk(char, char.facing)
```

Replace with:
```python
# Stay in the comfort band — walk to close, idle once inside
if distance > MELEE_RANGE * 0.95:
    self._start_walk(char, char.facing)
elif distance < MELEE_RANGE * 0.55:
    # Too close — back off slightly
    self._start_walk(char, -char.facing)
else:
    # In the kill zone (0.55 .. 0.95 * MELEE_RANGE) — go straight to attack tactics
    ...  # existing in-range mixed tactics block stays
```

**A3. Cast pushback in `_start_attack`**

For COOLDOWN and SPECIAL skills, after emitting `ATTACK_WINDUP`:
```python
if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
    # Cast pushback creates space so the projectile + impact are visible
    char.vel_x = -3.5 * char.facing            # attacker hops back
    opp.vel_x += 2.0 * char.facing             # defender drifts away from attacker
    self._emit(EventType.ATTACK_WINDUP, ...)
```

Existing friction decay (`* 0.7` per frame) settles in ~10 frames, creating ~25px space window for the skill animation.

### B. Audio sync drift fix

**B1. Track video time per event in episode runner**

Maintain a dict `event_video_ms` keyed by `id(event)`. On the consume loop:
```python
for ev in new_events:
    event_video_ms[id(ev)] = frame_no * TICK_MS
    # ... existing event handling ...
```

This captures the actual video-frame time at which the event was processed, which already accumulates hit-stop and cinematic frames.

**B2. Pass map to `build_audio_track`**

Modify `pixel_battle/video/compose.py::build_audio_track` signature:
```python
def build_audio_track(
    events: List[Event],
    total_duration_ms: int,
    output_path: str,
    event_offset_ms: int = 0,
    event_video_ms: dict | None = None,
) -> None:
```

In the per-event loop, replace `pos = ev.t_ms + event_offset_ms` with:
```python
if event_video_ms is not None and id(ev) in event_video_ms:
    pos = event_video_ms[id(ev)]
else:
    pos = ev.t_ms + event_offset_ms
```

Episode runner passes the map when calling `build_audio_track`.

### C. Cast SFX (procedural numpy)

**C1. New script `pixel_battle/scripts/gen_cast_sfx.py`**

Generates two shared SFX (all CD skills use cooldown, all specials use special — not per-skill):
- `cast_cooldown.wav` (~0.25s): 220Hz triangle wave with quick fade + white noise hiss + decay. Reads as "tssht!"
- `cast_special.wav` (~0.35s): 400→1200Hz chirp UP + 1760Hz crystal-bell overtone + short attack. Reads as "zwoom!"

Numbers and envelopes mirror P3's `gen_ult_sfx.py` style. Files written to `pixel_battle/assets/sfx/`.

**C2. compose.py: play cast SFX on ATTACK_WINDUP**

Add new branch in `build_audio_track` for-loop:
```python
elif ev.type is EventType.ATTACK_WINDUP:
    st = ev.extra.get("skill_type", "")
    cast_name = f"cast_{st}"  # cast_cooldown / cast_special
    cast_sfx = _load_sfx_or_none(cast_name)
    if cast_sfx:
        track = track.overlay(cast_sfx, position=pos)
```

### D. Cast performance — flair on skill release

**D1. Release flash at end of charge**

When `ChargeFXSystem` calls `on_complete` (existing — currently unused), spawn a "release flash":
- White-core expanding ring: max_radius=80, lifetime=3, color=(255,255,255) but tinted to skill color outside
- 8 burst particles flying outward (skill color, random angles, speed 8.0)

Add method `ImpactFXSystem.spawn_release_flash(x, y, color)`:
```python
def spawn_release_flash(self, x: float, y: float,
                        color: Tuple[int, int, int]) -> None:
    """Bigger, faster ring used at skill release (vs hit landing)."""
    self.rings.append(ImpactRing(
        x=x, y=y, color=color,
        lifetime=3, max_radius=80,
    ))
```

Episode runner ATTACK_WINDUP handler passes `on_complete` callback when spawning charge_fx:
```python
def _release_callback(x=actor.pos_x, y=actor.pos_y, c=color, tgt=actor.id):
    renderer.impact_fx.spawn_release_flash(int(x), int(y - 80), c)
    renderer.particles.emit_hit_burst(int(x), int(y - 80),
                                       color=c, count=8, speed=8.0)

renderer.charge_fx.spawn(x=int(actor.pos_x), y=int(actor.pos_y),
                          color=color, on_complete=_release_callback)
```

**D2. Camera zoom on attacker during windup**

Add `Renderer.set_zoom(factor: float, center: Tuple[int, int])` and apply in `render_frame`:
```python
def set_zoom(self, factor: float, center: Tuple[int, int]) -> None:
    self._zoom_factor = factor
    self._zoom_center = center

# In render_frame, AFTER all drawing but BEFORE _apply_shake:
if self._zoom_factor != 1.0:
    self._apply_zoom()

def _apply_zoom(self) -> None:
    w, h = self.surface.get_size()
    zoom = self._zoom_factor
    cx, cy = self._zoom_center
    # Scale up the whole surface
    scaled = pygame.transform.smoothscale(self.surface,
                                           (int(w * zoom), int(h * zoom)))
    # Compute crop region centered on (cx*zoom, cy*zoom)
    crop_x = max(0, min(int(cx * zoom - w / 2), scaled.get_width() - w))
    crop_y = max(0, min(int(cy * zoom - h / 2), scaled.get_height() - h))
    self.surface.fill((0, 0, 0))
    self.surface.blit(scaled, (-crop_x, -crop_y))
```

Episode runner sets zoom on ATTACK_WINDUP:
```python
renderer.set_zoom(1.04, (int(actor.pos_x), int(actor.pos_y - 80)))
```

And clears it on charge `on_complete` callback (when release fires):
```python
def _release_callback(...):
    renderer.set_zoom(1.0, (240, 427))  # reset
    ...
```

`Renderer.__init__` initializes `_zoom_factor = 1.0` and `_zoom_center = (WIDTH // 2, HEIGHT // 2)`.

Performance cost: one `smoothscale` per frame during the ~200ms windup window. Negligible at 60fps for 480×854.

**D3. Motion lines during windup**

In `engine/charge_fx.py`, add motion lines drawn behind the attacker during the windup. Each line is a short horizontal streak (length 12-20px, color = skill color, alpha decay). Spawned per frame from positions slightly behind the attacker (opposite to facing direction), drifting "into" the attacker.

Implementation: extend `ChargeFXSystem.update_and_render` to also draw 4 streak lines per frame at semi-random offsets behind `eff.x`:
```python
# Motion lines (drawn before sparkles)
for i in range(4):
    offset_x = -40 - (i * 8) + eff.age  # pull in toward attacker
    offset_y = -50 - i * 20
    line_alpha = max(0, 200 - i * 50 - eff.age * 8)
    if line_alpha > 0:
        line_surface = pygame.Surface((16, 2), pygame.SRCALPHA)
        line_surface.fill((*eff.color, line_alpha))
        surface.blit(line_surface, (int(eff.x + offset_x), int(eff.y + offset_y)))
```

## Architecture

No new modules. Surgical extensions to:
- `engine/battle.py` — collision resolver + AI band + cast pushback
- `engine/charge_fx.py` — motion lines
- `engine/impact_fx.py` — `spawn_release_flash` (just a parameterized `spawn_ring`)
- `engine/renderer.py` — zoom transform
- `episodes/ep01_brick_vs_glass.py` — track `event_video_ms`, charge release callback, zoom set/reset
- `video/compose.py` — accept `event_video_ms`, cast SFX overlay
- `scripts/gen_cast_sfx.py` — new (mirrors `gen_ult_sfx.py`)

## Data flow additions

```
Battle.tick_ms()
  → _update_physics(both)
  → NEW: _resolve_character_collision()       # A1
  → ... existing ...

Battle._start_attack(CD/special)
  → emit ATTACK_WINDUP
  → NEW: cast pushback (vel_x change on both chars)   # A3

Episode runner ATTACK_WINDUP handler
  → NEW: event_video_ms[id(ev)] = frame_no * TICK_MS   # B1
  → charge_fx.spawn(..., on_complete=_release_callback)  # D1 hook
  → NEW: renderer.set_zoom(1.04, (attacker_x, attacker_y - 80))   # D2

charge_fx on_complete fires after windup (~12 frames)
  → impact_fx.spawn_release_flash(...)   # D1
  → particles.emit_hit_burst(...)         # D1 burst
  → renderer.set_zoom(1.0, ...)           # D2 reset

compose.build_audio_track(events, event_video_ms=event_video_ms)
  → for each event, use event_video_ms[id(ev)] if present  # B2
  → ATTACK_WINDUP → overlay cast_cooldown.wav or cast_special.wav   # C2
```

## Error handling

- Collision: `clamp_x` ensures pushed positions stay in arena bounds.
- Audio map: if `event_video_ms[id(ev)]` missing, fall back to `ev.t_ms + offset` (preserves existing behavior).
- Cast SFX files missing → `_load_sfx_or_none` returns None, silently skips.
- Zoom: factor=1.0 is no-op; bounds-checked crop_x/crop_y can't go out of frame.

## Testing

### Unit tests (new)

- `tests/test_character_collision.py`
  - Two characters placed within `MIN_CHAR_DISTANCE` get pushed apart after a tick
  - Characters at exactly `MIN_CHAR_DISTANCE` are not pushed
  - Pushed positions stay within arena bounds
- `tests/test_cast_pushback.py`
  - When `_start_attack` selects CD skill, attacker.vel_x becomes negative-toward-defender
  - Defender gets a small vel_x push
  - Basic skill: no pushback
- `tests/test_audio_video_ms_map.py`
  - `build_audio_track` with `event_video_ms` map uses map value for positioning
  - Without map, falls back to `ev.t_ms + offset_ms`
- `tests/test_charge_fx_motion_lines.py`
  - smoke render that motion lines don't crash

### Visual regression

Re-run `python -m pixel_battle.episodes.ep01_brick_vs_glass`. Confirm:
- No frame where left/right sprites visibly overlap
- During CD/special windup, attacker hops back, defender drifts back
- Audio SFX align with visible hit moments (subjective — re-watch)
- "tssht" / "zwoom" sound on every CD/special skill cast
- Brief white burst at attacker when charge completes
- Screen zooms in slightly during windup, snaps back on release
- Motion lines visible behind attacker during windup

## Implementation order

1. **A1+A2+A3 collision + AI band + cast pushback** — single battle.py edit + tests
2. **B1+B2 audio drift fix** — runner map + compose signature
3. **C1+C2 cast SFX** — gen script + compose overlay
4. **D1 release flash** — impact_fx method + charge on_complete wiring
5. **D2 zoom** — renderer set_zoom + episode runner trigger/reset
6. **D3 motion lines** — charge_fx extension
7. **Visual regression** — regenerate final.mp4

## Out of scope

- Per-skill cast SFX (shared cast_cooldown / cast_special files are good enough)
- Camera zoom on KO or ult (just windup for now)
- Replacing AI with RL (P5+ track)
- New sprite PNG assets

## Tuning knobs (single-constant changes for iteration)

- `MIN_CHAR_DISTANCE = 70`
- AI band: `MELEE_RANGE * 0.55` (inner) / `MELEE_RANGE * 0.95` (outer)
- Cast pushback: `attacker.vel_x = -3.5 * facing`, `defender.vel_x += 2.0 * facing`
- Release flash: `max_radius=80`, `lifetime=3`
- Zoom factor: `1.04`
- Motion lines: 4 lines per frame, length 16px, alpha decay 50/line
- Cast SFX duration: 250ms cooldown / 350ms special
