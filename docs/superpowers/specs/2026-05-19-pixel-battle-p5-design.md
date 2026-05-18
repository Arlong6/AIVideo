# Pixel Battle — P5 Stronger Spacing + Audio Drift + Visible Release Spec

**Date**: 2026-05-19
**Status**: Approved
**Trigger**: User feedback on P4 — "重疊好一點 / 空間不夠開 / 音效還是沒有對齊 / 招式閃光看不太到"

## Goal

Three small but pointed fixes:
1. Cast pushback was too weak AND defender's AI immediately closed the gap → double pushback strength + freeze defender's AI for 200ms during attacker windup.
2. Audio still drifts — root cause is `TICK_MS = 1000 // 60 = 16ms` (int truncation) vs real video frame time `1000/60 ≈ 16.667ms`. Use float FRAME_MS in audio paths.
3. Release flash is too short (50ms) and too small (radius 80) — bump lifetime, radius, particle count, and add a brief screen flash.

## Three blocks

### A. Stronger spacing + freeze defender

**A1. Bump cast pushback magnitudes**

In `engine/battle.py::_start_attack`, find the existing pushback block (P4):
```python
            # Cast pushback — creates visible space for the skill animation
            char.vel_x = -3.5 * char.facing       # attacker hops back
            opp.vel_x += 2.0 * char.facing        # defender drifts away
```

Replace with:
```python
            # Cast pushback — creates visible space for the skill animation
            char.vel_x = -7.0 * char.facing       # attacker hops back (P5: doubled)
            opp.vel_x += 5.0 * char.facing        # defender drifts away (P5: 2.5x)
```

**A2. Freeze defender's AI during attacker windup**

Root cause of P4 failure: even with pushback, defender's AI re-walks toward attacker the next tick (distance increased → "approach" branch fires).

Solution: add `Character.windup_stun_until_ms: int = 0` field. When attacker fires CD/special, set `opp.windup_stun_until_ms = self.elapsed_ms + 200`. Battle's `_ai_choose_action` adds an early-return guard at the top: if `self.elapsed_ms < char.windup_stun_until_ms`, skip AI logic this tick (no walking, no jumping, no attacking).

Character field addition:
```python
@dataclass
class Character:
    # ...existing fields
    windup_stun_until_ms: int = 0
```

Plus clear it in `reset_physics` (alongside other timers):
```python
        self.windup_stun_until_ms = 0
```

Battle `_ai_choose_action` early-return:
```python
    def _ai_choose_action(self, char: Character, opp: Character, dt_ms: int) -> None:
        """Simple AI: pursue → attack → react → retreat. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
        # P5: windup stun — defender is briefly frozen while attacker casts
        if self.elapsed_ms < char.windup_stun_until_ms:
            return
        # ... rest of existing AI logic
```

Battle `_start_attack` sets the stun on the opponent (same block as the pushback):
```python
        if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
            self._emit(EventType.ATTACK_WINDUP, ...)
            # Cast pushback + defender freeze
            char.vel_x = -7.0 * char.facing
            opp.vel_x += 5.0 * char.facing
            opp.windup_stun_until_ms = self.elapsed_ms + 200    # P5: 200ms freeze
```

This combination should create ~50px of visible space during the 200ms windup. Defender's velocity decays under friction during the freeze; AI takes over again right at the moment the hit lands.

### B. Audio drift — TICK_MS truncation fix

**Root cause** (newly diagnosed):
- `TICK_MS = 1000 // FPS = 1000 // 60 = 16ms` (integer truncation; real value is 16.6667ms)
- Audio track length set via `total_duration_ms = N_frames * 16ms`
- Video plays at FPS=60, real time per frame = 16.667ms → video is N_frames × 16.667ms long
- After mux with `-shortest`, output uses min of the two — but the audio positioning is wrong by 4.2%
- Over a 40s match, that's ~1.7s of audio drift (audio plays earlier than the visual moment)

**Fix**: Introduce `FRAME_MS = 1000.0 / FPS` (float = 16.6667) and use it for audio-timing paths only. Keep `TICK_MS=16` as the integer game-physics step (changing physics tick is risky; only audio cares about real-time alignment).

In `episodes/ep01_brick_vs_glass.py`:
```python
FPS = 60
TICK_MS = 1000 // FPS    # 16 — used for battle physics (integer)
FRAME_MS = 1000.0 / FPS  # 16.6667 — used for real-time audio alignment
```

Replace:
```python
    total_ms = (INTRO_FRAMES * TICK_MS) + battle.elapsed_ms + (30 * TICK_MS) + (180 * TICK_MS)
    intro_offset_ms = INTRO_FRAMES * TICK_MS
```

With:
```python
    # P5 audio fix: use real-time FRAME_MS (1000/60) so audio length matches video playback time.
    # Total frames in the video = intro (180) + battle frames + 30 hold + 180 result.
    battle_frames = battle.elapsed_ms // TICK_MS  # how many physics ticks ran
    total_frames = INTRO_FRAMES + battle_frames + 30 + 180
    total_ms = int(total_frames * FRAME_MS)
    intro_offset_ms = int(INTRO_FRAMES * FRAME_MS)
```

Replace the `event_video_ms` population:
```python
            event_video_ms[id(ev)] = frame_no * TICK_MS
```
With:
```python
            event_video_ms[id(ev)] = int(frame_no * FRAME_MS)
```

The audio_event_video_ms shift line stays correct since `intro_offset_ms` is now also FRAME_MS-based.

### C. Visible release flash

**C1. Bump release ring lifetime + radius**

In `engine/impact_fx.py::spawn_release_flash`:
```python
    def spawn_release_flash(self, x: float, y: float,
                            color: Tuple[int, int, int]) -> None:
        """Bigger, shorter ring used at skill release (vs hit landing)."""
        self.rings.append(ImpactRing(
            x=x, y=y, color=color,
            lifetime=3, max_radius=80,
        ))
```

Replace with:
```python
    def spawn_release_flash(self, x: float, y: float,
                            color: Tuple[int, int, int]) -> None:
        """Bigger, longer-lived ring used at skill release (vs hit landing)."""
        self.rings.append(ImpactRing(
            x=x, y=y, color=color,
            lifetime=6, max_radius=120,   # P5: was lifetime=3, max_radius=80
        ))
```

**C2. Add screen flash on release**

In `episodes/ep01_brick_vs_glass.py::_release_callback` (inside ATTACK_WINDUP handler), find:
```python
                def _release_callback(rx=actor_x_int, ry=actor_y_int - 80,
                                       c=color):
                    renderer.impact_fx.spawn_release_flash(rx, ry, c)
                    renderer.particles.emit_hit_burst(rx, ry, color=c,
                                                       count=8, speed=8.0)
                    # Reset zoom when charge finishes
                    renderer.set_zoom(1.0, (WIDTH // 2, HEIGHT // 2))
```

Replace with:
```python
                def _release_callback(rx=actor_x_int, ry=actor_y_int - 80,
                                       c=color):
                    renderer.impact_fx.spawn_release_flash(rx, ry, c)
                    # P5: add screen flash on release for visibility
                    renderer.impact_fx.request_screen_flash(c, alpha=120, frames=4)
                    # P5: bigger burst (was count=8, speed=8.0)
                    renderer.particles.emit_hit_burst(rx, ry, color=c,
                                                       count=16, speed=10.0)
                    # Reset zoom when charge finishes
                    renderer.set_zoom(1.0, (WIDTH // 2, HEIGHT // 2))
```

## Architecture

No new modules. Three sets of surgical edits:
- `engine/battle.py` — pushback magnitudes + windup_stun trigger + AI early-return
- `engine/character.py` — add `windup_stun_until_ms` field + clear in reset_physics
- `engine/impact_fx.py` — tweak `spawn_release_flash` constants
- `episodes/ep01_brick_vs_glass.py` — FRAME_MS for audio + bumped release callback
- `video/compose.py` — unchanged (already accepts event_video_ms map from P4)

## Error handling

- New `windup_stun_until_ms` field defaults to 0 → never blocks AI by default
- `_ai_choose_action` early-return on stun is additive — doesn't change behavior when stun is 0
- FRAME_MS is a float; `int()` cast prevents subpixel ms artifacts
- Existing P4 `event_video_ms` map handles missing entries via fallback — still works

## Testing

### Unit tests (new)

- `tests/test_windup_stun.py`
  - Character starts with `windup_stun_until_ms == 0`
  - `_start_attack` for CD/special sets opp.windup_stun_until_ms to elapsed_ms + 200
  - `_ai_choose_action` skips logic when elapsed_ms < windup_stun_until_ms
  - `_ai_choose_action` resumes after stun expires
  - `reset_physics` clears stun

- `tests/test_audio_frame_ms.py`
  - Episode FRAME_MS constant equals 1000.0 / FPS (60) = 16.6667
  - FRAME_MS != TICK_MS (regression check that we don't accidentally collapse them)

### Visual regression

Re-run `python -m pixel_battle.episodes.ep01_brick_vs_glass`. Confirm:
- During CD/special skill cast, defender stops/freezes for ~200ms (visible separation grows)
- Audio impact sounds align tightly with visible hit moments (subjective)
- Release flash is visibly bigger and longer (look for ~100ms cyan/orange ring expansion + ~70ms screen tint)

## Implementation order

1. **A2 windup_stun** — Character field + Battle AI gate + trigger (TDD)
2. **A1 stronger pushback** — single-line bumps (no test needed; covered by visual regression)
3. **C1+C2 release flash** — impact_fx constants + episode callback bump
4. **B FRAME_MS audio** — episode runner constant + 2 usage sites
5. **Visual regression** — regenerate final.mp4

## Out of scope

- Refactor battle physics to use float TICK_MS (risky; only audio cares about real-time)
- Multi-frame ramp-down for windup_stun (binary on/off is enough)
- Per-skill release flash variation (one shape for all)

## Tuning knobs

- Cast pushback: attacker `-7.0`, defender `+5.0`
- `windup_stun_until_ms` duration: `200ms`
- Release flash: `lifetime=6`, `max_radius=120`, burst `count=16`, `speed=10.0`, screen flash `alpha=120`, `frames=4`
- `FRAME_MS = 1000.0 / FPS`
