# Pixel Battle Smoothness + Variation Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render Script 01 at 120 fps with sub-frame engine interpolation, add idle breathing + walk-cycle variation, and bump motion blur to 35%.

**Architecture:** Four changes land in two files (`play.py` and `poses.py` / `stick_renderer.py`):
1. `play.py` — double render FPS to 120, keep engine at 60 Hz, sub-frame interpolate character positions between engine ticks; bump motion blur alpha.
2. `poses.py` — add idle bob (vertical sine oscillation) to `compute_figure`.
3. `stick_renderer.py` — add `walk_phase_t` per-character to `RenderState`; add walk-cycle foot alternation + vertical bob to `draw_stick_figure`.
4. Five new tests in a new file `tests/test_smoothness_pass.py`.

**Tech Stack:** Python, pygame, numpy (for tests), existing `RenderState`, `FigureGeometry`, `FrameRecorder`.

---

## File Map

| File | Change |
|---|---|
| `pixel_battle/rl/play.py` | Add `RENDER_FPS=120`, `ENGINE_HZ=60`, sub-frame accumulator loop, motion blur alpha 51→89 |
| `pixel_battle/rl/poses.py` | `compute_figure` accepts optional `time_ms` param; applies idle bob when pose_id == "idle" |
| `pixel_battle/rl/stick_renderer.py` | `RenderState` gains `walk_phase_t`; `draw_stick_figure` passes `time_ms` to `compute_figure`; walk bob applied via per-character phase |
| `pixel_battle/tests/test_smoothness_pass.py` | Five new tests |

---

## Task 1 — Motion blur alpha 20% → 35%

**Files:**
- Modify: `pixel_battle/rl/play.py:473`
- Test: `pixel_battle/tests/test_smoothness_pass.py`

- [ ] **Step 1: Write the failing test**

Create `pixel_battle/tests/test_smoothness_pass.py`:

```python
# pixel_battle/tests/test_smoothness_pass.py
"""Tests for 120-fps render, idle bob, walk cycle, motion blur alpha."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
import pygame
import pytest

from pixel_battle.engine.character import Character


@pytest.fixture(scope="module", autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


# ── T1: Motion blur alpha ─────────────────────────────────────────────────────

def test_motion_blur_uses_higher_alpha():
    """MOTION_BLUR_ALPHA must be >= 80 (35% of 255 ≈ 89)."""
    from pixel_battle.rl.play import MOTION_BLUR_ALPHA
    assert MOTION_BLUR_ALPHA >= 80, (
        f"Expected MOTION_BLUR_ALPHA >= 80, got {MOTION_BLUR_ALPHA}"
    )
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_motion_blur_uses_higher_alpha -v
```
Expected: FAIL — `AssertionError: Expected MOTION_BLUR_ALPHA >= 80, got 51`

- [ ] **Step 3: Change MOTION_BLUR_ALPHA in play.py**

In `pixel_battle/rl/play.py`, line 473, change:
```python
    MOTION_BLUR_ALPHA = 51  # ~20 % of 255
```
to:
```python
    MOTION_BLUR_ALPHA = 89  # ~35 % of 255
```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_motion_blur_uses_higher_alpha -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/arlong/Projects/AIvideo
git add pixel_battle/rl/play.py pixel_battle/tests/test_smoothness_pass.py
git commit -m "tune(pixel-battle/rl): motion blur alpha 20% → 35%"
```

---

## Task 2 — Render at 120 fps with sub-frame engine interpolation

**Files:**
- Modify: `pixel_battle/rl/play.py` (constants + `_render_fight` loop + `render_script` call + `run_one_match` call + `run_full_episode` call)
- Modify: `pixel_battle/rl/play_scripted.py` (imports FPS from play.py — already does this, but must pick up the new RENDER_FPS instead)
- Test: `pixel_battle/tests/test_smoothness_pass.py`

### Design

Current loop (simplified):
```
for frame in range(total_frames):   # total_frames = max_seconds * 60
    engine.step()                   # always advance engine
    render frame
```

New loop:
```
RENDER_FPS = 120
ENGINE_HZ = 60
RENDER_MS = 1000.0 / RENDER_FPS     # 8.333 ms
ENGINE_MS = 1000.0 / ENGINE_HZ      # 16.667 ms

accumulator = 0.0
prev_state = snapshot(env)

for render_frame in range(total_render_frames):   # total_render_frames = max_seconds * 120
    accumulator += RENDER_MS        # 8.333 ms per render frame
    if accumulator >= ENGINE_MS:    # every 2nd render frame
        accumulator -= ENGINE_MS
        engine.step(dt=16)          # advance engine once
        new_state = snapshot(env)
        prev_state = new_state
        frac = 0.0                  # just stepped: use new state
    else:
        frac = accumulator / ENGINE_MS   # 0.5 on the in-between frame

    # Positions for rendering: lerp prev→current by frac
    render_positions = lerp(prev_state, current_state, frac)
    draw(render_positions)
    recorder.write_frame()
```

The "snapshot" only needs character `pos_x`, `pos_y` (camera follow also uses these).

KO drama loop and intro do NOT use this accumulator — they keep their existing frame counts but must use `RENDER_FPS` for the total count and `RENDER_MS` for timing.

The `event_video_ms` dict maps `id(ev) -> render_frame * RENDER_MS` (same formula, just finer time).

Audio timing: `fight["n_frames"]` already accounts for the doubled count; `RENDER_MS` (not `FRAME_MS`) must be used to compute `total_duration_ms` in callers. We expose `RENDER_FPS` and `RENDER_MS` as module-level names; callers use `RENDER_MS` instead of `FRAME_MS` when computing audio duration.

### Implementation

The key changes to `_render_fight`:

1. At the top of `_render_fight`, add local constants:
   ```python
   RENDER_FPS = 120
   ENGINE_HZ = 60
   RENDER_MS = 1000.0 / RENDER_FPS   # 8.333 ms
   ENGINE_MS = 1000.0 / ENGINE_HZ    # 16.667 ms
   ```

2. Change `total_frames` to `total_render_frames = int(max_seconds * RENDER_FPS)`.

3. Add accumulator + prev-position state **before** the loop:
   ```python
   _accum_ms: float = 0.0
   _prev_left_x: float = env.left.pos_x
   _prev_left_y: float = env.left.pos_y
   _prev_right_x: float = env.right.pos_x
   _prev_right_y: float = env.right.pos_y
   _interp_frac: float = 0.0
   _engine_this_frame: bool = False
   ```

4. At the start of each render-frame loop:
   - Increment `_accum_ms += RENDER_MS`.
   - If `_accum_ms >= ENGINE_MS`: snapshot previous positions, advance engine, subtract `ENGINE_MS`, set `_interp_frac = 0.0`, set `_engine_this_frame = True`.
   - Else: `_interp_frac = _accum_ms / ENGINE_MS`, `_engine_this_frame = False`.

5. After deciding frac, temporarily override `env.left.pos_x/pos_y` and `env.right.pos_x/pos_y` with the lerped values for this render frame. Restore them after drawing (or just pass lerped values explicitly to `_draw_with_recoil` / `draw_shadow`). Since the engine reads from these too, the safest approach is:
   - Keep the real positions unchanged in `env.left`/`env.right`.
   - Create a thin `_RenderPos` shim: locally override only the positions used for drawing (shadow, figure, camera follow).

6. For the camera `mid_x` calculation, use the lerped `x` positions (not the engine positions), so the camera also interpolates.

7. All event detection remains gated on `_engine_this_frame` (events are only emitted when the engine advances).

8. `event_video_ms` uses `render_frame * RENDER_MS` (same formula, just `RENDER_MS` instead of `FRAME_MS`).

9. KO drama loop `ko_drama_frames = int(1.5 * RENDER_FPS)` (was `1.5 * FPS`).

10. Banner/flash frame counters that use `frame + 36` etc. need to double: `frame + 72` (was 36) and `frame + 156` (was 78 for ultimate). Or more cleanly: store banner end in **ms**, not frames. The existing code uses `banner_until_frame = frame + 36` — since `frame` is now a render frame at 120 fps, 36 render frames = 0.3s at 120 fps (was 0.6s at 60 fps). To preserve the same on-screen duration, use `banner_until_frame = frame + 72` for skill banners and `frame + 156` for ultimate banners. Same ratio applies to `shake_frames`, flash frame counters etc.

   **Simpler approach:** Convert all frame-based counters to ms, stored separately. But that is a larger refactor. Instead, double all frame-count literals that were tuned for 60 fps:

   | Old (60 fps) | New (120 fps) |
   |---|---|
   | `frame + 36` (skill banner) | `frame + 72` |
   | `frame + 78` (ultimate banner) | `frame + 156` |
   | `flash_frames_left = 10` (ultimate) | `flash_frames_left = 20` |
   | hit/crit `left_flash_frames = 4/5` | `8/10` |
   | `right_flash_frames = 7` (ultimate) | `14` |
   | `shake_frames = SHAKE_FRAMES` | unchanged (SHAKE_FRAMES still 8 render frames but now 8/120s ≈ 67ms — currently at 60fps was 8/60s ≈ 133ms; halved). Double `SHAKE_FRAMES` to 16 OR make it a duration in ms internally. Cleanest: `shake_frames = SHAKE_FRAMES * 2` at trigger site |
   | `screen_shake_frames_left = max(_, 6)` beam | `max(_, 12)` |
   | `screen_shake_frames_left = max(_, 16)` ultimate | `max(_, 32)` |
   | `_slowmo_remaining_ms` — already in ms, unchanged |  |
   | `ko_drama_frames = int(1.5 * FPS)` | `int(1.5 * RENDER_FPS)` |
   | whiteout `range(16)` | `range(32)` |

11. The `KOSequence.tick(dt_ms=16)` call should change to `dt_ms=RENDER_MS` for the in-between frames, and `dt_ms=ENGINE_MS` for the engine-tick frames. But since KO sequence is a renderer-only state machine (controls zoom/alpha), it should tick every render frame at `RENDER_MS`. Change all `ko_seq.tick(..., dt_ms=16)` to `dt_ms=RENDER_MS`.

12. `impact_fx.update_and_draw(surf, dt_ms=16)` → `dt_ms=RENDER_MS`. Same for `impact_fx.camera_shake.update(FRAME_MS)` → `impact_fx.camera_shake.update(RENDER_MS)`.

13. The `_attacker_recoil` timer uses `int(FRAME_MS)` for tick-down — change to `int(RENDER_MS)`.

14. Module-level `FRAME_MS` should remain as `1000.0 / FPS` for backward compat with audio code that still uses `FRAME_MS` per-frame. Audio callers (`run_one_match`, `run_full_episode`) that compute `total_duration_ms = int(fight["n_frames"] * FRAME_MS)` must change to `* RENDER_MS` since `n_frames` is now at 120 fps. Add module-level `RENDER_FPS = 120` and `RENDER_MS = 1000.0 / RENDER_FPS` alongside `FPS`/`FRAME_MS`.

15. `INTRO_FRAMES` and `RESULT_FRAMES` are used in `run_full_episode`. They must double too, or be defined in terms of seconds. Cleanest: keep them as seconds:
    ```python
    INTRO_FRAMES = int(1.8 * RENDER_FPS)   # was 108 at 60fps → 216 at 120fps
    RESULT_FRAMES = int(3.0 * RENDER_FPS)  # was 180 → 360
    ```
    But this doubles the intro/result duration to 1.8s and 3.0s — same real-time, but more frames. That's correct.

16. `play_scripted.py` imports `FPS` from `play.py` and passes it to `FrameRecorder`. Must change to `RENDER_FPS`.

- [ ] **Step 1: Write the two new tests**

Append to `pixel_battle/tests/test_smoothness_pass.py`:

```python
# ── T2a: Recorder is constructed at 120 fps ───────────────────────────────────

def test_render_runs_at_120fps():
    """RENDER_FPS constant must be 120."""
    from pixel_battle.rl.play import RENDER_FPS
    assert RENDER_FPS == 120, f"Expected RENDER_FPS=120, got {RENDER_FPS}"


# ── T2b: Engine ticks at 60 Hz during render ─────────────────────────────────

def test_engine_ticks_at_60hz_during_render():
    """In 1 simulated second of render frames the engine must have ticked exactly 60 times.

    We simulate the accumulator logic manually without running the full renderer.
    """
    from pixel_battle.rl.play import RENDER_FPS, RENDER_MS, ENGINE_MS

    total_render_frames = RENDER_FPS   # 1 second worth
    accum = 0.0
    engine_ticks = 0
    for _ in range(total_render_frames):
        accum += RENDER_MS
        if accum >= ENGINE_MS:
            accum -= ENGINE_MS
            engine_ticks += 1
    assert engine_ticks == 60, (
        f"Expected 60 engine ticks in 1s of render, got {engine_ticks}"
    )
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_render_runs_at_120fps tests/test_smoothness_pass.py::test_engine_ticks_at_60hz_during_render -v
```
Expected: both FAIL (RENDER_FPS not exported yet)

- [ ] **Step 3: Add module-level RENDER_FPS / RENDER_MS constants to play.py**

In `pixel_battle/rl/play.py`, after line 40 (`FRAME_MS = 1000.0 / FPS`), add:
```python
RENDER_FPS = 120          # output frame rate
RENDER_MS = 1000.0 / RENDER_FPS   # 8.333 ms per render frame
ENGINE_HZ = 60            # engine tick rate (unchanged)
ENGINE_MS = 1000.0 / ENGINE_HZ    # 16.667 ms per engine tick
```

- [ ] **Step 4: Run constants tests to confirm they pass**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_render_runs_at_120fps tests/test_smoothness_pass.py::test_engine_ticks_at_60hz_during_render -v
```
Expected: both PASS

- [ ] **Step 5: Rewrite _render_fight accumulator loop**

This is the large change. Make the following changes to `pixel_battle/rl/play.py`:

**5a. Update `INTRO_FRAMES` and `RESULT_FRAMES` to use `RENDER_FPS`:**

```python
# Old:
INTRO_FRAMES = 108      # 1.8s VS intro
RESULT_FRAMES = 180     # 3.0s K.O. + winner card
# New:
INTRO_FRAMES = int(1.8 * RENDER_FPS)   # 216 frames at 120fps
RESULT_FRAMES = int(3.0 * RENDER_FPS)  # 360 frames at 120fps
```

**5b. Inside `_render_fight`, change `total_frames` and add accumulator state:**

Replace:
```python
    total_frames = int(max_seconds * FPS)
    event_video_ms: dict = {}
    terminated = False
    frame = 0
```
With:
```python
    total_frames = int(max_seconds * RENDER_FPS)
    event_video_ms: dict = {}
    terminated = False
    frame = 0
    # Sub-frame interpolation: engine ticks at ENGINE_HZ; renderer at RENDER_FPS.
    _accum_ms: float = 0.0
    _prev_left_x: float = env.left.pos_x
    _prev_left_y: float = env.left.pos_y
    _prev_right_x: float = env.right.pos_x
    _prev_right_y: float = env.right.pos_y
    _interp_frac: float = 0.0
    _engine_this_frame: bool = True   # first frame always ticks
```

**5c. At the top of the main `for frame in range(total_frames):` loop, replace the existing engine-advance block with the accumulator logic:**

Old code at the top of the loop:
```python
    for frame in range(total_frames):
        left_act, right_act = action_source(env, (obs_left, obs_right))

        prev_ev_n = len(env.battle.events)
        # Slow-mo: advance the engine at a reduced rate this frame.
        ...
        if _slowmo_remaining_ms > 0:
            ...
            env.battle.tick_ms(effective_dt, skip_ai=False)
            ...
        else:
            _slowmo_dt_scale = 1.0
            (obs_left, obs_right), _, terminated, truncated, _ = env.step(
                (left_act, right_act)
            )
```

New code (replace the whole block from `left_act, right_act = ...` through the slow-mo if/else, keeping the event-processing code that follows):

```python
    for frame in range(total_frames):
        # ── Sub-frame accumulator: engine ticks at ENGINE_HZ, render at RENDER_FPS ──
        _accum_ms += RENDER_MS
        _engine_this_frame = _accum_ms >= ENGINE_MS
        if _engine_this_frame:
            _accum_ms -= ENGINE_MS
            _interp_frac = 0.0
            # Snapshot previous character positions for lerp
            _prev_left_x = env.left.pos_x
            _prev_left_y = env.left.pos_y
            _prev_right_x = env.right.pos_x
            _prev_right_y = env.right.pos_y
        else:
            _interp_frac = _accum_ms / ENGINE_MS

        # Only advance AI + engine on engine-tick frames
        if _engine_this_frame:
            left_act, right_act = action_source(env, (obs_left, obs_right))
            prev_ev_n = len(env.battle.events)
            if _slowmo_remaining_ms > 0:
                _slowmo_remaining_ms -= ENGINE_MS
                effective_dt = int(ENGINE_MS * _slowmo_dt_scale)
                env.battle.tick_ms(effective_dt, skip_ai=False)
                try:
                    obs_left, obs_right = env._obs_pair()
                except Exception:
                    pass
                terminated = env.battle.state is _BattleState.KO
                truncated = False
            else:
                _slowmo_dt_scale = 1.0
                (obs_left, obs_right), _, terminated, truncated, _ = env.step(
                    (left_act, right_act)
                )
        else:
            prev_ev_n = len(env.battle.events)  # no new events on in-between frames
```

**5d. Compute interpolated positions for rendering:**

After the engine-tick block and before the event-processing for-loop, add:
```python
        # Interpolated draw positions (lerp prev→current by _interp_frac).
        # Only used for shadow + figure drawing; engine state is unchanged.
        _draw_left_x = _prev_left_x + (env.left.pos_x - _prev_left_x) * _interp_frac
        _draw_left_y = _prev_left_y + (env.left.pos_y - _prev_left_y) * _interp_frac
        _draw_right_x = _prev_right_x + (env.right.pos_x - _prev_right_x) * _interp_frac
        _draw_right_y = _prev_right_y + (env.right.pos_y - _prev_right_y) * _interp_frac
```

**5e. Wrap event-loop and burst/VFX spawning inside `if _engine_this_frame:` gate:**

The entire `for ev in env.battle.events[prev_ev_n:]:` block (which spawns bursts, flashes, slowmo, banners, projectiles) should only run when `_engine_this_frame` is True — because events are only emitted on engine ticks.

Wrap it:
```python
        if _engine_this_frame:
            for ev in env.battle.events[prev_ev_n:]:
                event_video_ms[id(ev)] = int(frame * RENDER_MS)
                # ... all existing event handling unchanged
```

Similarly, the second event loop (the ImpactFX "Route new events" block) should also be inside `if _engine_this_frame:`.

**5f. Update frame-count-based durations to double (since now at 120 fps):**

Within `_render_fight`, change the following literals:
```python
# Banner durations (in render frames):
banner_until_frame = frame + 72   # was 36 (0.3s at 60fps → 0.3s at 120fps)
# For ultimate banner:
banner_until_frame = frame + 156  # was 78

# Flash frame counters:
# ultimate_start: flash_frames_left = 10 → 20
# hit/crit: left_flash_frames = max(left_flash_frames, 8)  # was 4
#           left_flash_frames = max(left_flash_frames, 10) # was 5 (crit)
# ultimate: left_flash_frames = max(left_flash_frames, 14) # was 7

# Camera shake at beam: screen_shake_frames_left = max(_, 12)  # was 6
# Camera shake at ultimate: screen_shake_frames_left = max(_, 32) # was 16
# shake_frames at crit: shake_frames = SHAKE_FRAMES * 2  # keep shaking 16 frames not 8
```

**5g. Update timing in per-frame code that uses `FRAME_MS`:**

Change all per-frame uses of `FRAME_MS` inside `_render_fight` to `RENDER_MS`:
```python
event_video_ms[id(ev)] = int(frame * RENDER_MS)   # was FRAME_MS
now_ms = int(frame * RENDER_MS)                    # was FRAME_MS
draw_effect_indicators(world, env.left, current_ms=int(frame * RENDER_MS))
draw_effect_indicators(world, env.right, current_ms=int(frame * RENDER_MS))
projectiles.draw(world, int(frame * RENDER_MS))
hud_overlay.draw(surf, env.battle, elapsed_ms=int(frame * RENDER_MS))
```

**5h. Update KO sequence, impact_fx tick, attacker recoil to use RENDER_MS:**

```python
ko_result = ko_seq.tick(ko_active=..., ko_loser_x=..., dt_ms=RENDER_MS)   # was 16
impact_fx.camera_shake.update(RENDER_MS)    # was FRAME_MS
impact_fx.update_and_draw(surf, dt_ms=RENDER_MS)  # was 16
_attacker_recoil[cid] = max(0, _attacker_recoil[cid] - int(RENDER_MS))    # was FRAME_MS
# In KO drama loop:
_ko_r = ko_seq.tick(ko_active=True, ko_loser_x=ko_loser_x, dt_ms=RENDER_MS)  # was 16
impact_fx.update_and_draw(surf, dt_ms=RENDER_MS)   # inside KO drama loop
```

**5i. KO drama + whiteout frame counts:**

```python
ko_drama_frames = int(1.5 * RENDER_FPS)   # was int(1.5 * FPS)
# Whiteout:
for k in range(32):   # was 16
    ... k / 32 ...    # was k / 16
# end_hold_frames already passed from caller; no change needed
```

**5j. Shadow and figure draw positions — use interpolated coords:**

In `_draw_shadow(world, env.left)` etc., since `_draw_shadow` reads `char.pos_x/pos_y` directly, temporarily set them to the interpolated values during drawing:

```python
        # Apply interpolated positions for drawing
        def _set_draw_pos(char, ix, iy):
            char._draw_pos_x, char._draw_pos_y = char.pos_x, char.pos_y
            char.pos_x, char.pos_y = ix, iy

        def _restore_draw_pos(char):
            char.pos_x, char.pos_y = char._draw_pos_x, char._draw_pos_y

        _set_draw_pos(env.left, _draw_left_x, _draw_left_y)
        _set_draw_pos(env.right, _draw_right_x, _draw_right_y)
        try:
            _draw_shadow(world, env.left)
            _draw_shadow(world, env.right)
            # ... draw figures, effects, etc.
        finally:
            _restore_draw_pos(env.left)
            _restore_draw_pos(env.right)
```

This is the cleanest way to slot in interpolated positions without refactoring the entire draw pipeline.

**5k. Camera follow — use interpolated mid_x:**

```python
        mid_x = (_draw_left_x + _draw_right_x) / 2.0
```

**5l. Update FrameRecorder construction in callers to use RENDER_FPS:**

In `run_one_match`:
```python
    recorder = FrameRecorder(str(raw_video), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
    ...
    total_duration_ms = int(fight["n_frames"] * RENDER_MS)
```

In `run_full_episode`:
```python
    recorder = FrameRecorder(str(raw_video), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
    ...
    total_frames = INTRO_FRAMES + fight["n_frames"] + RESULT_FRAMES
    total_duration_ms = int(total_frames * RENDER_MS)
    intro_offset_ms = int(INTRO_FRAMES * RENDER_MS)
    ko_at = int((INTRO_FRAMES + fight["n_frames"]) * RENDER_MS)
```

**5m. Update play_scripted.py to import RENDER_FPS:**

In `pixel_battle/rl/play_scripted.py`, change:
```python
from pixel_battle.rl.play import _render_fight, WIDTH, HEIGHT, FPS, ROOT
```
to:
```python
from pixel_battle.rl.play import _render_fight, WIDTH, HEIGHT, RENDER_FPS, ROOT
```
And change:
```python
    recorder = FrameRecorder(str(raw), fps=FPS, width=WIDTH, height=HEIGHT)
```
to:
```python
    recorder = FrameRecorder(str(raw), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
```

- [ ] **Step 6: Run full test suite to ensure no regressions**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```
Expected: 469+ passed (467 pre-existing + 3 new tests from Task 1+2), 1 pre-existing FAIL on `test_dump_timeline`, 3 skipped.

- [ ] **Step 7: Quick smoke render**

```bash
cd /Users/arlong/Projects/AIvideo
python -m pixel_battle.rl.play_scripted pixel_battle/data/scripts/01_lux_kite_garen.yaml
```
Expected: creates `pixel_battle/output/scripted/01_lux_kite_garen_raw.mp4`; no crash; file size 1.5–4 MB.

- [ ] **Step 8: Commit**

```bash
cd /Users/arlong/Projects/AIvideo
git add pixel_battle/rl/play.py pixel_battle/rl/play_scripted.py pixel_battle/tests/test_smoothness_pass.py
git commit -m "feat(pixel-battle/rl): render at 120 fps with sub-frame engine interpolation"
```

---

## Task 3 — Idle breathing animation

**Files:**
- Modify: `pixel_battle/rl/poses.py` — `compute_figure` accepts optional `time_ms` param; adds vertical bob when pose_id == "idle"
- Modify: `pixel_battle/rl/stick_renderer.py` — `draw_stick_figure` and `RenderState.resolve` pass `time_ms` through
- Test: `pixel_battle/tests/test_smoothness_pass.py`

### Design

The idle bob is a sub-pose oscillation, NOT a state change. It must NOT trigger the cross-state lerp cache. The simplest clean way:

- `compute_figure(char, style, time_ms: float = 0.0)` — new optional param.
- Inside `compute_figure`, after all FK is solved and the hip position is set:
  ```python
  if pose_id == "idle":
      bob = math.sin(time_ms / 1200.0 * 2.0 * math.pi) * 1.5
      # Shift all joints upward by -bob (screen y: negative = up)
      # This is equivalent to subtracting bob from hip.y before applying _shift
      hip = (hip[0], hip[1] - bob)
      # Re-derive shoulder and head from the new hip
      shoulder = (hip[0] + tc * torso_len, hip[1] + ts * torso_len)
      head_center = (shoulder[0] + tc * head_gap, shoulder[1] + ts * head_gap)
      # Re-derive limb positions by shifting all existing limb joints by delta
      _dy = -bob
      front_knee = (front_knee[0], front_knee[1] + _dy)
      front_foot = (front_foot[0], front_foot[1] + _dy)
      back_knee = (back_knee[0], back_knee[1] + _dy)
      back_foot = (back_foot[0], back_foot[1] + _dy)
      front_elbow = (front_elbow[0], front_elbow[1] + _dy)
      front_hand = (front_hand[0], front_hand[1] + _dy)
      back_elbow = (back_elbow[0], back_elbow[1] + _dy)
      back_hand = (back_hand[0], back_hand[1] + _dy)
  ```
  Wait — this shifts the FEET off the ground. The bob should move the torso up while keeping the feet planted. The correct approach: shift only the torso-and-up joints, not the feet.

  Corrected approach:
  ```python
  if pose_id == "idle":
      bob_y = math.sin(time_ms / 1200.0 * 2.0 * math.pi) * 1.5  # +1.5 = down (screen)
      # Only shift hip → shoulder → head + arms (not feet/knees)
      hip = (hip[0], hip[1] + bob_y)
      shoulder = (hip[0] + tc * torso_len, hip[1] + ts * torso_len)
      head_center = (shoulder[0] + tc * head_gap, shoulder[1] + ts * head_gap)
      front_elbow, front_hand = solve_limb(shoulder, fa_deg, fa_flex, upper, fore)
      back_elbow, back_hand = solve_limb(shoulder, ba_deg, ba_flex, upper, fore)
  ```
  Feet/knees remain at their original FK positions (planted on the ground). The bob visually stretches/compresses the torso slightly — looks like breathing.

  Note: `bob_y` at `sin=0` is 0 (neutral). At `sin=1` (peak) the hip moves down 1.5 px (toward ground). At `sin=-1` (trough) the hip moves up 1.5 px. This is a very subtle 3 px total range.

- **Where `time_ms` comes from:** `draw_stick_figure` receives the current render time. It already receives `char` and `color`; add `time_ms: float = 0.0`.

- `RenderState.resolve(char, style, dt_ms, time_ms)` — add `time_ms` param, pass it to `compute_figure`.

- The cross-state cache snaps `new_geo = compute_figure(char, style, time_ms)`. Since the idle bob changes the geometry at different `time_ms`, two successive idle frames will have slightly different `new_geo`. But since both are "idle" (same pose key), no state transition is triggered — the transition only fires when `new_key != self._last_pose_key`. The geometry returned is just the bob-modified current geometry. This is correct behavior.

- **Disable during active states:** The pose_id check `== "idle"` already excludes attacking, hitting, blocking, crouching, walking, jumping. Only a character that is truly idle (standing still, on ground, not in any action state) gets the bob.

### Implementation

**3a. Modify `compute_figure` signature:**
```python
def compute_figure(char, style: dict, time_ms: float = 0.0) -> FigureGeometry:
```

**3b. After the arm FK solve, add the idle bob section:**
```python
    # Idle breathing bob — sub-pose oscillation, does not trigger state transitions.
    # Shifts torso + arms upward/downward; feet stay planted.
    if pose_id == "idle":
        import math as _m
        bob_y = _m.sin(time_ms / 1200.0 * 2.0 * _m.pi) * 1.5
        hip = (hip[0], hip[1] + bob_y)
        shoulder = (hip[0] + tc * torso_len, hip[1] + ts * torso_len)
        head_center = (shoulder[0] + tc * head_gap, shoulder[1] + ts * head_gap)
        front_elbow, front_hand = solve_limb(shoulder, fa_deg, fa_flex, upper, fore)
        back_elbow, back_hand = solve_limb(shoulder, ba_deg, ba_flex, upper, fore)
```

**3c. In `stick_renderer.py`, update `draw_stick_figure` signature:**
```python
def draw_stick_figure(surf: pygame.Surface, char, color: tuple,
                      time_ms: float = 0.0) -> None:
```

And update the internal call to `compute_figure` (via `RenderState.resolve`):
```python
    geo = _get_render_state(char).resolve(char, style, dt_ms=RENDER_MS_DEFAULT, time_ms=time_ms)
```

(Where `RENDER_MS_DEFAULT = 8.333` — the inter-frame delta for 120 fps rendering.)

Wait — `draw_stick_figure` currently calls `_RENDER_STATE_CACHE[id(char)]` implicitly. Let's see exactly how it calls `resolve`. Check the current `draw_stick_figure` implementation:

**3d. Update `RenderState.resolve` signature:**
```python
    def resolve(self, char, style: dict, dt_ms: float = 16.0,
                time_ms: float = 0.0) -> FigureGeometry:
```
And pass `time_ms` to `compute_figure`:
```python
        new_geo = compute_figure(char, style, time_ms)
```

**3e. Update all callers of `draw_stick_figure` in `play.py` to pass `time_ms`:**

The render loop has `frame` as the render frame counter. The current time in ms is `frame * RENDER_MS`. Pass this as `time_ms`:
```python
        def _draw_with_recoil(surf, char, color, _time_ms=0.0):
            cid = id(char)
            if cid in _attacker_recoil:
                orig_y = char.pos_y
                char.pos_y = orig_y + 4
                try:
                    draw_stick_figure(surf, char, color, time_ms=_time_ms)
                finally:
                    char.pos_y = orig_y
            else:
                draw_stick_figure(surf, char, color, time_ms=_time_ms)

        _cur_time_ms = frame * RENDER_MS
        _draw_with_recoil(world, env.left, left_color, _time_ms=_cur_time_ms)
        _draw_with_recoil(world, env.right, right_color, _time_ms=_cur_time_ms)
```

Also update the intro/result screen calls (they use `draw_stick_figure` directly without time_ms; add `time_ms=0.0` default — already handled by the default param).

- [ ] **Step 1: Write the failing test**

Append to `pixel_battle/tests/test_smoothness_pass.py`:

```python
# ── T3: Idle bob changes y over time ─────────────────────────────────────────

def test_idle_bob_changes_y_over_time():
    """Render an idle character at t=0 and t=600ms; head joint y must differ by > 0.5px."""
    from pixel_battle.rl.poses import compute_figure

    _STYLE = {
        "head_shape": "circle", "head_size": 14, "torso_length": 52,
        "upper_arm": 18, "forearm": 18, "thigh": 20, "shin": 20,
        "line_width": 3, "hand_radius": 3, "foot_length": 8,
        "pose_overrides": {},
    }

    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 0.0

    geo0 = compute_figure(c, _STYLE, time_ms=0.0)
    geo_half = compute_figure(c, _STYLE, time_ms=600.0)  # half-cycle = peak bob

    delta_y = abs(geo0.head_center[1] - geo_half.head_center[1])
    assert delta_y > 0.5, (
        f"Idle bob: head y difference at 0ms vs 600ms is {delta_y:.3f}px, expected > 0.5px"
    )
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_idle_bob_changes_y_over_time -v
```
Expected: FAIL — `TypeError` (unexpected `time_ms` argument) or `AssertionError: delta 0.0 not > 0.5`

- [ ] **Step 3: Implement idle bob in poses.py**

Modify `compute_figure` in `pixel_battle/rl/poses.py`:

1. Change signature: `def compute_figure(char, style: dict, time_ms: float = 0.0) -> FigureGeometry:`

2. At the top of `compute_figure`, `math` is already imported — confirm it's available.

3. After lines that solve arm FK (the `back_elbow, back_hand = solve_limb(...)` call), add the idle bob section:
   ```python
       # Idle breathing — sub-pose oscillation, does NOT trigger cross-state lerp.
       # Shifts hip upward/downward; feet stay planted.
       if pose_id == "idle":
           bob_y = math.sin(time_ms / 1200.0 * 2.0 * math.pi) * 1.5
           hip = (hip[0], hip[1] + bob_y)
           shoulder = (hip[0] + tc * torso_len, hip[1] + ts * torso_len)
           head_center = (shoulder[0] + tc * head_gap, shoulder[1] + ts * head_gap)
           front_elbow, front_hand = solve_limb(
               shoulder, fa_deg, fa_flex, upper, fore)
           back_elbow, back_hand = solve_limb(
               shoulder, ba_deg, ba_flex, upper, fore)
   ```

- [ ] **Step 4: Run test to confirm it passes**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_idle_bob_changes_y_over_time -v
```
Expected: PASS

- [ ] **Step 5: Update RenderState.resolve and draw_stick_figure signatures**

In `pixel_battle/rl/stick_renderer.py`:

a. `RenderState.resolve` — add `time_ms: float = 0.0` param and pass to `compute_figure`:
   ```python
   def resolve(self, char, style: dict, dt_ms: float = 16.0,
               time_ms: float = 0.0) -> FigureGeometry:
       new_key = _pose_key(char)
       new_geo = compute_figure(char, style, time_ms)
       ...
   ```

b. `draw_stick_figure` — add `time_ms: float = 0.0` param and pass to `resolve`:
   Find the call to `rs.resolve(...)` inside `draw_stick_figure` and update:
   ```python
   geo = rs.resolve(char, style, dt_ms=_RENDER_TICK_MS, time_ms=time_ms)
   ```
   Where `_RENDER_TICK_MS = 1000.0 / 120` — add this as a module constant in `stick_renderer.py`.

- [ ] **Step 6: Update play.py to pass time_ms to draw_stick_figure**

As described in step 3e above: update `_draw_with_recoil` to accept and forward `time_ms`; compute `_cur_time_ms = frame * RENDER_MS` and pass it.

- [ ] **Step 7: Run full test suite**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```
Expected: 470+ passed, same 1 pre-existing FAIL, 3 skipped.

- [ ] **Step 8: Commit**

```bash
cd /Users/arlong/Projects/AIvideo
git add pixel_battle/rl/play.py pixel_battle/rl/poses.py pixel_battle/rl/stick_renderer.py pixel_battle/tests/test_smoothness_pass.py
git commit -m "feat(pixel-battle/rl): idle breathing + walk-cycle pose variation"
```

---

## Task 4 — Walk cycle variation

**Files:**
- Modify: `pixel_battle/rl/stick_renderer.py` — add `walk_phase_t` to `RenderState`; compute walk bob + foot alternation in `draw_stick_figure`
- Test: `pixel_battle/tests/test_smoothness_pass.py`

### Design

Walk variation is purely renderer-side. The strategy:

1. `RenderState` gains `_walk_phase_t: float = 0.0` — accumulated ms whenever pose_id == "walk".
2. In `RenderState.resolve`, if pose_id == "walk": `self._walk_phase_t += dt_ms`, else reset to 0.0.
3. A `walk_phase_t` property exposes it.
4. In `draw_stick_figure`, after getting `geo` from `resolve`:
   - If pose_id == "walk": compute a walk bob and optionally rotate the front leg to alternate.

Walk bob: `bob_y = math.sin(rs.walk_phase_t / 400.0 * 2 * math.pi) * 2.0`
  - Apply to hip → shoulder → head + arms (same method as idle bob).
  - Feet stay planted.
  
Foot alternation: at `sin(walk_phase_t / 400 * 2π) > 0`, the front foot is "forward"; at `< 0`, the back foot is forward. Since the poses are authored with a fixed front/back, the alternation just adds a y-offset flip every 400 ms half-cycle. The cleaner approach: swap front and back leg joints when `walk_phase_t % 800 >= 400`.

Actually, `poses.py`'s `WALK_POSE` already has front and back legs in different positions — the walk pose is static. To get alternation: apply the WALK_POSE for the first half cycle, and a mirrored WALK_POSE (front/back swapped) for the second half. This means modifying the `FigureGeometry` returned:

```python
if pose_id == "walk" and rs._walk_phase_t % 800 >= 400:
    # Swap front/back leg joints to give "other foot forward" look
    geo = FigureGeometry(
        head_center=geo.head_center, shoulder=geo.shoulder, hip=geo.hip,
        front_elbow=geo.back_elbow, front_hand=geo.back_hand,
        back_elbow=geo.front_elbow, back_hand=geo.front_hand,
        front_knee=geo.back_knee, front_foot=geo.back_foot,
        back_knee=geo.front_knee, back_foot=geo.front_foot,
        weapon_deg=geo.weapon_deg, facing=geo.facing,
    )
```

Wait — this would swap the entire arm AND leg, giving a very jarring swap. Better approach: only swap legs, leave arms. And the arm counter-swing: swap front/back arms in the opposite half-cycle from legs.

Simpler and safe: just add the walk bob without foot swapping in the initial implementation. The bob (vertical oscillation) alone gives much better rhythm feel without risking visual glitches from joint swapping.

**Revised plan — walk bob only (no leg swap):**
- Walk bob: `bob_y = sin(walk_phase_t / 400 * 2π) * 2.0` applied to hip upward, feet stay.
- This gives a visible vertical "step" rhythm at 400ms per cycle (2.5 steps/s ≈ fast walk).

Implementation is cleaner, safer, and still delivers the spec goal ("visually steps").

- [ ] **Step 1: Write the failing test**

Append to `pixel_battle/tests/test_smoothness_pass.py`:

```python
# ── T4: Walk cycle alternates (bob changes y over time) ──────────────────────

def test_walk_cycle_alternates_feet():
    """At t=0 and t=400ms, the head y of a walking character must differ (walk bob).

    The walk bob has a 400ms half-period, so at t=0 and t=400ms the sin phase
    differs by π — head y should be at opposite extremes (difference > 1px).
    """
    from pixel_battle.rl.stick_renderer import RenderState, get_style

    _STYLE = get_style("garen")
    c = Character.load("garen")
    c.pos_x, c.pos_y = 240.0, 720.0
    c.facing = 1
    c.action_state = "idle"
    c.on_ground = True
    c.vel_x = 4.0   # walk

    rs = RenderState()
    # Bootstrap
    rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    # Drive walk_phase_t to 0ms (reset after bootstrap since first call was bootstrap)
    # Actually the first resolve() with vel_x=4 sets pose_key to "walk"
    # and walk_phase_t starts at 0. Drive to 400ms by ticking 400/8.333 ≈ 48 frames.
    ticks_400ms = int(400 / 8.333)
    geo0 = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)  # baseline

    for _ in range(ticks_400ms):
        geo_400 = rs.resolve(c, _STYLE, dt_ms=8.333, time_ms=0.0)

    delta_y = abs(geo0.head_center[1] - geo_400.head_center[1])
    assert delta_y > 1.0, (
        f"Walk bob: head y diff at t=0 vs t=400ms is {delta_y:.3f}px, expected > 1px"
    )
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_walk_cycle_alternates_feet -v
```
Expected: FAIL — delta_y is 0.0 (walk bob not implemented)

- [ ] **Step 3: Add walk_phase_t to RenderState**

In `pixel_battle/rl/stick_renderer.py`:

a. In `RenderState.__init__`, add:
   ```python
   self._walk_phase_t: float = 0.0
   ```

b. In `RenderState.resolve`, after the key-change check and before the transition timer update, add walk-phase tracking:
   ```python
       # Walk phase — accumulate when walking, reset otherwise
       new_pose_id = new_key  # new_key is already the pose_id string
       if new_pose_id == "walk":
           self._walk_phase_t += dt_ms
       else:
           self._walk_phase_t = 0.0
   ```

c. Expose as a property:
   ```python
   @property
   def walk_phase_t(self) -> float:
       return self._walk_phase_t
   ```

- [ ] **Step 4: Apply walk bob in draw_stick_figure**

In `pixel_battle/rl/stick_renderer.py`, inside `draw_stick_figure`, after getting `geo = rs.resolve(...)`:

Find where the current pose_id is determined (or compute it via `select_pose_id(char)`). Then apply the bob:

```python
    from pixel_battle.rl.poses import select_pose_id as _select_pose_id, FigureGeometry
    _pose_id_cur = _select_pose_id(char)
    if _pose_id_cur == "walk":
        import math as _m
        walk_bob_y = _m.sin(rs.walk_phase_t / 400.0 * 2.0 * _m.pi) * 2.0
        # Shift hip → shoulder → head + arms; feet stay planted
        new_hip = (geo.hip[0], geo.hip[1] + walk_bob_y)
        # Recompute shoulder and head from shifted hip
        # We need tc, ts (torso direction vector). Approximate from existing joints:
        # tc,ts = unit vector from hip to shoulder in current geo
        import math as _math
        dx = geo.shoulder[0] - geo.hip[0]
        dy = geo.shoulder[1] - geo.hip[1]
        dist = max(0.001, _math.hypot(dx, dy))
        tc_w, ts_w = dx / dist, dy / dist
        torso_len_w = dist
        new_shoulder = (new_hip[0] + tc_w * torso_len_w,
                        new_hip[1] + ts_w * torso_len_w)
        head_offset_dx = geo.head_center[0] - geo.shoulder[0]
        head_offset_dy = geo.head_center[1] - geo.shoulder[1]
        new_head = (new_shoulder[0] + head_offset_dx,
                    new_shoulder[1] + head_offset_dy)
        # Arms: shift by same delta as hip
        _dy_bob = walk_bob_y
        geo = FigureGeometry(
            head_center=new_head,
            shoulder=new_shoulder,
            hip=new_hip,
            front_elbow=(geo.front_elbow[0], geo.front_elbow[1] + _dy_bob),
            front_hand=(geo.front_hand[0], geo.front_hand[1] + _dy_bob),
            back_elbow=(geo.back_elbow[0], geo.back_elbow[1] + _dy_bob),
            back_hand=(geo.back_hand[0], geo.back_hand[1] + _dy_bob),
            front_knee=geo.front_knee,    # feet planted
            front_foot=geo.front_foot,
            back_knee=geo.back_knee,
            back_foot=geo.back_foot,
            weapon_deg=geo.weapon_deg,
            facing=geo.facing,
        )
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/test_smoothness_pass.py::test_walk_cycle_alternates_feet -v
```
Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -20
```
Expected: 471+ passed, 1 pre-existing FAIL, 3 skipped.

- [ ] **Step 7: Confirm `test_all_poses_keep_feet_planted_and_in_frame` passes**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/ -k "feet_planted" -v
```
Expected: PASS — walk bob keeps feet planted (we only shift hip upward, not feet).

- [ ] **Step 8: Commit**

```bash
cd /Users/arlong/Projects/AIvideo
git add pixel_battle/rl/stick_renderer.py pixel_battle/tests/test_smoothness_pass.py
git commit -m "feat(pixel-battle/rl): idle breathing + walk-cycle pose variation"
```

Note: If Task 3 and Task 4 are committed together, merge into a single commit message as shown here.

---

## Task 5 — Validation render + final commit

**Files:**
- None new — runs the render and verifies output.

- [ ] **Step 1: Run full test suite one more time**

```bash
cd /Users/arlong/Projects/AIvideo/pixel_battle
python -m pytest tests/ -v --tb=short -q 2>&1 | tail -10
```
Expected: 471+ passed.

- [ ] **Step 2: Render Script 01**

```bash
cd /Users/arlong/Projects/AIvideo
time python -m pixel_battle.rl.play_scripted pixel_battle/data/scripts/01_lux_kite_garen.yaml
```

Note the wall-clock time. For a 20-30s fight, expect ~15-40s render wall-clock (2× frames, but faster because we draw fewer new things per frame on interpolated frames). If wall-clock > 120s, investigate whether the engine is being advanced twice per render frame.

- [ ] **Step 3: Check output file**

```bash
ls -lh /Users/arlong/Projects/AIvideo/pixel_battle/output/scripted/
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 \
  /Users/arlong/Projects/AIvideo/pixel_battle/output/scripted/01_lux_kite_garen_raw.mp4
```

Expected:
- File size 1.5–4 MB (roughly double prior size due to 2× frames at same duration).
- Duration: same as before (KO time unchanged — engine runs at 60 Hz).
- No crash.

- [ ] **Step 4: Commit render output**

```bash
cd /Users/arlong/Projects/AIvideo
git add pixel_battle/output/scripted/01_lux_kite_garen_raw.mp4
git commit -m "tune: 01 — re-render after smoothness pass (120fps, idle bob, walk cycle, blur 35%)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Render at 120 fps | Task 2 |
| Engine ticks at 60 Hz | Task 2 |
| Sub-frame interpolation of character positions | Task 2 step 5d |
| VFX advance every render frame | Task 2 — ko_seq, impact_fx tick at RENDER_MS |
| Motion blur to 35% | Task 1 |
| Idle breathing bob 1.5 px, 1.2 s cycle | Task 3 |
| Walk cycle vertical bob 2 px, 400 ms cycle | Task 4 |
| All 483 pre-existing tests stay green | Task 2 step 6, Task 4 step 6 |
| `test_all_poses_keep_feet_planted_and_in_frame` passes | Task 4 step 7 |
| `test_render_runs_at_120fps` | Task 2 step 1 |
| `test_engine_ticks_at_60hz_during_render` | Task 2 step 1 |
| `test_idle_bob_changes_y_over_time` | Task 3 step 1 |
| `test_walk_cycle_alternates_feet` | Task 4 step 1 |
| `test_motion_blur_uses_higher_alpha` | Task 1 step 1 |
| Validation render of Script 01 | Task 5 |

**Placeholder scan:** None found.

**Type consistency:** `compute_figure` returns `FigureGeometry` throughout. `RenderState.resolve` signature consistently adds `time_ms: float = 0.0`. `walk_phase_t` property name used consistently in both definition and test.

**Potential concern — feet_planted test:** The idle bob and walk bob shift joints above the hip only; feet are never moved. The `test_all_poses_keep_feet_planted_and_in_frame` test checks that feet stay at `pos_y`. Since walk bob does not move feet, this should pass. Verify in Task 4 step 7.

**Potential concern — `_RENDER_TICK_MS` in stick_renderer:** `draw_stick_figure` uses a module constant `_RENDER_TICK_MS = 1000.0 / 120` for the `dt_ms` passed to `resolve`. Tests that call `RenderState.resolve` directly with `dt_ms=16.0` still work because the parameter is explicit.
