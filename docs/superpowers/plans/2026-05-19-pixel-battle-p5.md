# Pixel Battle P5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Three small but pointed fixes to P4 — double cast pushback + freeze defender AI for 200ms during cast, fix audio drift caused by `TICK_MS=16` integer truncation (real frame time is 16.667ms), and make skill-release flash visibly bigger/longer with an added screen flash.

**Architecture:** Surgical edits to four existing modules. New `Character.windup_stun_until_ms` field (default 0) gates `_ai_choose_action` so defender stops walking while attacker casts. New `FRAME_MS = 1000.0 / FPS` float constant runs the audio-timing math only; physics keeps using integer `TICK_MS`. Release-flash tuning is pure parameter bumps.

**Tech Stack:** Python 3, pygame (headless), pytest, numpy/pydub (audio), ffmpeg (mux).

**Spec:** `docs/superpowers/specs/2026-05-19-pixel-battle-p5-design.md`

---

## File Structure

**Modified:**
- `pixel_battle/engine/character.py` — add `windup_stun_until_ms: int = 0` dataclass field; clear in `reset_physics`
- `pixel_battle/engine/battle.py` — early-return gate in `_ai_choose_action`; set stun + bump pushback in `_start_attack`
- `pixel_battle/engine/impact_fx.py` — tweak constants in `spawn_release_flash`
- `pixel_battle/episodes/ep01_brick_vs_glass.py` — introduce `FRAME_MS`, use it in audio paths; bump release callback

**New tests:**
- `pixel_battle/tests/test_windup_stun.py` — new field, AI gate, trigger, reset
- `pixel_battle/tests/test_audio_frame_ms.py` — episode-runner `FRAME_MS` constant correctness

**No changes:** `video/compose.py`, `engine/renderer.py`, `engine/charge_fx.py`, `engine/projectile.py`, asset files.

---

## Implementation Order

1. **Task 1** — Character field + reset (TDD; foundation)
2. **Task 2** — Battle AI early-return gate (TDD; uses Task 1's field)
3. **Task 3** — Battle `_start_attack` sets stun + stronger pushback (TDD; uses Tasks 1-2)
4. **Task 4** — `spawn_release_flash` lifetime/radius bumps (TDD against ImpactRing param)
5. **Task 5** — Episode runner `_release_callback` (screen flash + bigger burst)
6. **Task 6** — Episode runner `FRAME_MS` + audio-timing wiring (TDD against constant)
7. **Task 7** — Run full unit-test suite + visual regression (regenerate final.mp4)

---

### Task 1: Add `windup_stun_until_ms` field to Character

**Files:**
- Modify: `pixel_battle/engine/character.py:31-44` (dataclass fields), `:73-79` (`reset_physics` body)
- Test: `pixel_battle/tests/test_windup_stun.py` (new)

- [ ] **Step 1.1: Write the failing tests for the new field**

Create `pixel_battle/tests/test_windup_stun.py`:

```python
"""P5: Windup stun gates defender AI while attacker casts."""
from pixel_battle.engine.character import Character


def test_character_has_windup_stun_field_defaulting_to_zero():
    """New field defaults to 0 so existing code paths are unaffected."""
    c = Character.load("brick_phone")
    assert c.windup_stun_until_ms == 0


def test_reset_physics_clears_windup_stun():
    """reset_physics zeroes the stun timer (e.g., between rounds)."""
    c = Character.load("brick_phone")
    c.windup_stun_until_ms = 12345
    c.reset_physics(initial_x=100.0, facing=1)
    assert c.windup_stun_until_ms == 0
```

- [ ] **Step 1.2: Run tests to verify they fail**

Run: `pytest pixel_battle/tests/test_windup_stun.py::test_character_has_windup_stun_field_defaulting_to_zero pixel_battle/tests/test_windup_stun.py::test_reset_physics_clears_windup_stun -v`
Expected: FAIL — `AttributeError: 'Character' object has no attribute 'windup_stun_until_ms'`

- [ ] **Step 1.3: Add the field on the Character dataclass**

In `pixel_battle/engine/character.py`, find the field block ending with `retreat_until_ms: int = 0`:

```python
    skill_cd_ready_at: Dict[str, int] = field(default_factory=dict)
    retreat_until_ms: int = 0
```

Replace with:

```python
    skill_cd_ready_at: Dict[str, int] = field(default_factory=dict)
    retreat_until_ms: int = 0
    windup_stun_until_ms: int = 0
```

- [ ] **Step 1.4: Clear the field in `reset_physics`**

In `pixel_battle/engine/character.py`, find the line:

```python
        self.retreat_until_ms = 0
```

Replace with:

```python
        self.retreat_until_ms = 0
        self.windup_stun_until_ms = 0
```

- [ ] **Step 1.5: Run tests to verify they pass**

Run: `pytest pixel_battle/tests/test_windup_stun.py -v`
Expected: PASS (2 passed)

- [ ] **Step 1.6: Run full unit-test suite — confirm no regressions**

Run: `pytest pixel_battle/tests/ -x --ignore=pixel_battle/tests/test_renderer.py -q 2>&1 | tail -20`
Expected: all green except the long-standing pre-existing failure `test_ai_retreats_when_mp_high_and_close` (predates P1, intentionally left). No NEW failures.

- [ ] **Step 1.7: Commit**

```bash
git add pixel_battle/engine/character.py pixel_battle/tests/test_windup_stun.py
git commit -m "feat(pixel-battle): Character.windup_stun_until_ms field (P5)"
```

---

### Task 2: AI early-return when `elapsed_ms < windup_stun_until_ms`

**Files:**
- Modify: `pixel_battle/engine/battle.py:319-322` (top of `_ai_choose_action`)
- Test: `pixel_battle/tests/test_windup_stun.py` (extend)

- [ ] **Step 2.1: Write the failing test for the AI gate**

Append to `pixel_battle/tests/test_windup_stun.py`:

```python
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.rng import BattleRNG


def test_ai_skips_when_within_windup_stun():
    """While elapsed_ms < windup_stun_until_ms, AI takes no action — pos_x unchanged."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(1000)  # past intro; elapsed_ms == 1000

    # Position out of range so the only thing AI could possibly do is walk toward opp
    a.pos_x = 100.0
    b.pos_x = 380.0
    a.vel_x = 0.0
    a.action_state = "idle"
    a.windup_stun_until_ms = bat.elapsed_ms + 200  # stun active

    bat._ai_choose_action(a, b, dt_ms=16)
    assert a.vel_x == 0.0, "AI should not have set walk velocity during stun"


def test_ai_resumes_after_stun_expires():
    """Once elapsed_ms >= windup_stun_until_ms, AI re-engages (walks toward opp)."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(1000)

    a.pos_x = 100.0
    b.pos_x = 380.0
    a.vel_x = 0.0
    a.action_state = "idle"
    a.windup_stun_until_ms = bat.elapsed_ms - 1  # already expired

    bat._ai_choose_action(a, b, dt_ms=16)
    # AI should walk right toward opp at b.pos_x=380 — vel_x positive
    assert a.vel_x > 0, f"AI should walk toward opponent after stun, got vel_x={a.vel_x}"
```

- [ ] **Step 2.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_windup_stun.py::test_ai_skips_when_within_windup_stun pixel_battle/tests/test_windup_stun.py::test_ai_resumes_after_stun_expires -v`
Expected: `test_ai_skips_when_within_windup_stun` FAILS — AI walks (vel_x > 0) despite stun set. `test_ai_resumes_after_stun_expires` may pass coincidentally; we still need the gate.

- [ ] **Step 2.3: Add the early-return guard**

In `pixel_battle/engine/battle.py`, find:

```python
    def _ai_choose_action(self, char: Character, opp: Character, dt_ms: int) -> None:
        """Simple AI: pursue → attack → react → retreat. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
```

Replace with:

```python
    def _ai_choose_action(self, char: Character, opp: Character, dt_ms: int) -> None:
        """Simple AI: pursue → attack → react → retreat. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
        # P5: windup stun — defender is briefly frozen while attacker casts
        if self.elapsed_ms < char.windup_stun_until_ms:
            return
```

- [ ] **Step 2.4: Run tests to verify they pass**

Run: `pytest pixel_battle/tests/test_windup_stun.py -v`
Expected: PASS (4 passed)

- [ ] **Step 2.5: Run full unit-test suite**

Run: `pytest pixel_battle/tests/ -x --ignore=pixel_battle/tests/test_renderer.py -q 2>&1 | tail -20`
Expected: same as Task 1 — only the pre-existing `test_ai_retreats_when_mp_high_and_close` failure. No new failures.

- [ ] **Step 2.6: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_windup_stun.py
git commit -m "feat(pixel-battle): AI early-return on windup_stun (P5)"
```

---

### Task 3: `_start_attack` sets stun + doubles cast pushback

**Files:**
- Modify: `pixel_battle/engine/battle.py:428-437` (existing cast pushback block)
- Test: `pixel_battle/tests/test_windup_stun.py` (extend)

- [ ] **Step 3.1: Write the failing test for the trigger**

Append to `pixel_battle/tests/test_windup_stun.py`:

```python
from pixel_battle.engine.skill import SkillType


def test_start_attack_sets_defender_windup_stun_for_cd_skill():
    """When attacker casts a CD skill, opp.windup_stun_until_ms is bumped to elapsed_ms + 200."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # in range
    a.mp = 0
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1
    b.windup_stun_until_ms = 0
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        b.windup_stun_until_ms = 0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found, "Couldn't force a CD skill choice"
    assert b.windup_stun_until_ms == bat.elapsed_ms + 200, \
        f"Expected stun = elapsed_ms+200, got {b.windup_stun_until_ms} (elapsed={bat.elapsed_ms})"


def test_start_attack_does_not_stun_on_basic():
    """Basic skill does not trigger windup_stun on defender."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280
    a.mp = 0
    # Force CD skills out of reach
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.last_attack_ms = -10000
    a.facing = 1
    a.vel_x = 0.0
    b.vel_x = 0.0
    b.windup_stun_until_ms = 0
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
    assert b.windup_stun_until_ms == 0
```

- [ ] **Step 3.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_windup_stun.py::test_start_attack_sets_defender_windup_stun_for_cd_skill pixel_battle/tests/test_windup_stun.py::test_start_attack_does_not_stun_on_basic -v`
Expected: `test_start_attack_sets_defender_windup_stun_for_cd_skill` FAILS — `b.windup_stun_until_ms` stays 0. `test_start_attack_does_not_stun_on_basic` PASSES (no change needed).

- [ ] **Step 3.3: Bump pushback + set stun in `_start_attack`**

In `pixel_battle/engine/battle.py`, find:

```python
        # Emit windup event for non-basic skills so the renderer can show charge FX
        if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
            self._emit(
                EventType.ATTACK_WINDUP,
                actor=char.id,
                extra={"skill_id": skill.id,
                       "skill_type": skill.skill_type.value},
            )
            # Cast pushback — creates visible space for the skill animation
            char.vel_x = -3.5 * char.facing       # attacker hops back
            opp.vel_x += 2.0 * char.facing        # defender drifts away
```

Replace with:

```python
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
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `pytest pixel_battle/tests/test_windup_stun.py pixel_battle/tests/test_cast_pushback.py -v`
Expected: PASS (all 6 pushback + stun tests). The existing P4 `test_cast_pushback` tests still check `vel_x < 0` / `vel_x > 0` (not exact magnitudes), so they remain green.

- [ ] **Step 3.5: Run full unit-test suite**

Run: `pytest pixel_battle/tests/ -x --ignore=pixel_battle/tests/test_renderer.py -q 2>&1 | tail -20`
Expected: only the pre-existing `test_ai_retreats_when_mp_high_and_close` failure. No new failures.

- [ ] **Step 3.6: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_windup_stun.py
git commit -m "feat(pixel-battle): 2x cast pushback + 200ms defender stun (P5)"
```

---

### Task 4: Bump `spawn_release_flash` lifetime + radius

**Files:**
- Modify: `pixel_battle/engine/impact_fx.py:34-40` (`spawn_release_flash`)
- Test: `pixel_battle/tests/test_impact_fx.py` (extend)

- [ ] **Step 4.1: Inspect existing `test_impact_fx.py` to follow its pattern**

Run: `cat pixel_battle/tests/test_impact_fx.py`
Read the existing assertions so the new test fits the conventions.

- [ ] **Step 4.2: Write the failing test**

Append to `pixel_battle/tests/test_impact_fx.py`:

```python
def test_release_flash_is_longer_and_bigger_than_default_ring():
    """P5: release flash bumped to lifetime=6, max_radius=120 for visibility."""
    from pixel_battle.engine.impact_fx import ImpactFXSystem
    fx = ImpactFXSystem()
    fx.spawn_release_flash(100.0, 100.0, (80, 180, 255))
    assert len(fx.rings) == 1
    ring = fx.rings[0]
    assert ring.lifetime == 6, f"expected lifetime=6, got {ring.lifetime}"
    assert ring.max_radius == 120, f"expected max_radius=120, got {ring.max_radius}"
```

- [ ] **Step 4.3: Run test to verify failure**

Run: `pytest pixel_battle/tests/test_impact_fx.py::test_release_flash_is_longer_and_bigger_than_default_ring -v`
Expected: FAIL — `assert 3 == 6` (current lifetime is 3).

- [ ] **Step 4.4: Bump the constants**

In `pixel_battle/engine/impact_fx.py`, find:

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

- [ ] **Step 4.5: Run test to verify pass**

Run: `pytest pixel_battle/tests/test_impact_fx.py -v`
Expected: PASS (existing + new test all green).

- [ ] **Step 4.6: Commit**

```bash
git add pixel_battle/engine/impact_fx.py pixel_battle/tests/test_impact_fx.py
git commit -m "feat(pixel-battle): release flash lifetime 3->6, radius 80->120 (P5)"
```

---

### Task 5: Episode runner — bigger release callback + screen flash

**Files:**
- Modify: `pixel_battle/episodes/ep01_brick_vs_glass.py:321-327` (inside `_release_callback`)

**Why no unit test:** `_release_callback` is a nested closure inside the episode runner's `ATTACK_WINDUP` event handler. Behavior verified by visual regression in Task 7.

- [ ] **Step 5.1: Update the release callback**

In `pixel_battle/episodes/ep01_brick_vs_glass.py`, find:

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

- [ ] **Step 5.2: Syntax check via import**

Run: `python -c "import pixel_battle.episodes.ep01_brick_vs_glass"`
Expected: no output (imports cleanly). Any IndentationError / SyntaxError surfaces here.

- [ ] **Step 5.3: Commit**

```bash
git add pixel_battle/episodes/ep01_brick_vs_glass.py
git commit -m "feat(pixel-battle): release callback — screen flash + bigger burst (P5)"
```

---

### Task 6: Episode runner — `FRAME_MS` audio drift fix

**Files:**
- Modify: `pixel_battle/episodes/ep01_brick_vs_glass.py:201-202` (constants), `:293` (event_video_ms population), `:503-504` (total_ms / intro_offset_ms)
- Test: `pixel_battle/tests/test_audio_frame_ms.py` (new)

- [ ] **Step 6.1: Write the failing test for the FRAME_MS constant**

Create `pixel_battle/tests/test_audio_frame_ms.py`:

```python
"""P5: episode runner uses float FRAME_MS for real-time audio alignment.

Root cause of P4 drift: TICK_MS = 1000 // 60 = 16 (int truncation), but
real frame time at FPS=60 is 1000/60 = 16.6667ms. Over a 40s match,
that 4% truncation cost ~1.7s of audio drift. Fix: use float FRAME_MS
for audio-positioning math; keep integer TICK_MS for physics.
"""
import importlib


def test_frame_ms_is_float_and_matches_fps():
    """FRAME_MS = 1000.0 / FPS, computed as float (no int truncation)."""
    mod = importlib.import_module("pixel_battle.episodes.ep01_brick_vs_glass")
    assert hasattr(mod, "FRAME_MS"), "Episode runner must expose FRAME_MS constant"
    assert isinstance(mod.FRAME_MS, float), \
        f"FRAME_MS must be float, got {type(mod.FRAME_MS).__name__}"
    expected = 1000.0 / mod.FPS
    assert abs(mod.FRAME_MS - expected) < 1e-9, \
        f"FRAME_MS={mod.FRAME_MS}, expected {expected}"


def test_frame_ms_differs_from_tick_ms_at_60_fps():
    """Regression: don't collapse FRAME_MS and TICK_MS to the same value."""
    mod = importlib.import_module("pixel_battle.episodes.ep01_brick_vs_glass")
    assert mod.FPS == 60, "Test assumes FPS=60"
    assert mod.TICK_MS == 16, "Physics tick should still be integer 16ms"
    assert mod.FRAME_MS != mod.TICK_MS, \
        "FRAME_MS must be float (16.6667), distinct from int TICK_MS (16)"
```

- [ ] **Step 6.2: Run tests to verify failure**

Run: `pytest pixel_battle/tests/test_audio_frame_ms.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'FRAME_MS'`.

- [ ] **Step 6.3: Add `FRAME_MS` constant**

In `pixel_battle/episodes/ep01_brick_vs_glass.py`, find:

```python
FPS = 60
TICK_MS = 1000 // FPS  # 16ms ≈ 60fps
```

Replace with:

```python
FPS = 60
TICK_MS = 1000 // FPS    # 16ms — used for battle physics (integer step)
FRAME_MS = 1000.0 / FPS  # 16.6667 — used for real-time audio alignment (P5)
```

- [ ] **Step 6.4: Run tests to verify constant passes**

Run: `pytest pixel_battle/tests/test_audio_frame_ms.py -v`
Expected: PASS (2/2).

- [ ] **Step 6.5: Wire `FRAME_MS` into `event_video_ms` population**

In `pixel_battle/episodes/ep01_brick_vs_glass.py`, find:

```python
            event_video_ms[id(ev)] = frame_no * TICK_MS
```

Replace with:

```python
            # P5 audio fix: use real-time FRAME_MS so audio aligns with video playback
            event_video_ms[id(ev)] = int(frame_no * FRAME_MS)
```

- [ ] **Step 6.6: Wire `FRAME_MS` into `total_ms` + `intro_offset_ms`**

In `pixel_battle/episodes/ep01_brick_vs_glass.py`, find:

```python
    total_ms = (INTRO_FRAMES * TICK_MS) + battle.elapsed_ms + (30 * TICK_MS) + (180 * TICK_MS)
    intro_offset_ms = INTRO_FRAMES * TICK_MS
```

Replace with:

```python
    # P5 audio fix: use real-time FRAME_MS (1000/60) for audio length so it
    # matches the video's wall-clock duration. Battle's elapsed_ms is physics
    # time — convert to frames first, then multiply by FRAME_MS.
    battle_frames = battle.elapsed_ms // TICK_MS
    total_frames = INTRO_FRAMES + battle_frames + 30 + 180
    total_ms = int(total_frames * FRAME_MS)
    intro_offset_ms = int(INTRO_FRAMES * FRAME_MS)
```

- [ ] **Step 6.7: Syntax check via import**

Run: `python -c "import pixel_battle.episodes.ep01_brick_vs_glass"`
Expected: no output.

- [ ] **Step 6.8: Verify existing audio-sync test still passes**

Run: `pytest pixel_battle/tests/test_audio_video_ms_map.py pixel_battle/tests/test_audio_frame_ms.py -v`
Expected: PASS (existing P4 map test + new FRAME_MS tests).

- [ ] **Step 6.9: Commit**

```bash
git add pixel_battle/episodes/ep01_brick_vs_glass.py pixel_battle/tests/test_audio_frame_ms.py
git commit -m "fix(pixel-battle): float FRAME_MS for audio drift (P5)"
```

---

### Task 7: Full test suite + visual regression

**Files:**
- Verify: all P5 changes interact cleanly; regenerate final.mp4 for human review.

- [ ] **Step 7.1: Run the full unit-test suite**

Run: `pytest pixel_battle/tests/ -q --ignore=pixel_battle/tests/test_renderer.py 2>&1 | tail -25`
Expected: All green EXCEPT the pre-existing failure `test_ai_retreats_when_mp_high_and_close` (predates P1 — explicitly out of scope this session). If any other test fails, stop and investigate.

- [ ] **Step 7.2: Regenerate the match video**

Run: `cd /Users/arlong/Projects/AIvideo && SDL_VIDEODRIVER=dummy python -m pixel_battle.episodes.ep01_brick_vs_glass 2>&1 | tail -30`
Expected: Final summary line shows `KO` (or `Draw`) + duration, plus `final.mp4` written.

- [ ] **Step 7.3: Confirm artifacts exist**

Run: `ls -la pixel_battle/output/ep01_brick_vs_glass/final.mp4 pixel_battle/output/ep01_brick_vs_glass/battle_events.json`
Expected: both files exist with recent mtime.

- [ ] **Step 7.4: Spot-check event log for P5 signals**

Run: `python -c "import json; e = json.load(open('pixel_battle/output/ep01_brick_vs_glass/battle_events.json')); awu = [x for x in e if x['type']=='attack_windup']; print('ATTACK_WINDUP count:', len(awu)); print('first 3 cast skill_types:', [x['extra'].get('skill_type') for x in awu[:3]])"`
Expected: ATTACK_WINDUP count > 15 (matches P4 baseline); skill_types include `cooldown` and `special`.

- [ ] **Step 7.5: Human review checklist (manual)**

Open `pixel_battle/output/ep01_brick_vs_glass/final.mp4`. Verify subjectively:
- During CD/special cast, defender visibly **stops** (not just gets pushed) for ~200ms
- Visible **gap** opens between attacker and defender before the projectile/banner appears
- Release flash is **clearly bigger** (cyan/orange ring expansion) and **briefly tints the screen**
- Cast SFX feels **tighter** with the visible flash (subjective — should be improved over P4)

- [ ] **Step 7.6: Final commit (only if any incidental fixups landed)**

If Steps 7.1–7.4 surfaced anything that required a tiny fix already covered by the implementation, commit it. Otherwise no commit needed — Tasks 1–6 cover all source changes.

```bash
# Only if needed:
git status
git add <fixup files>
git commit -m "fix(pixel-battle): <description> (P5)"
```

---

## Out of Scope (do not implement)

- Refactor physics to use float TICK_MS (risky; only audio paths need real-time alignment)
- Multi-frame ramp-down of windup_stun (binary on/off is enough)
- Per-skill release flash variation
- Re-enabling `BURN_SUBS_LONGFORM` (separate ticket; unrelated)
- Touching the pre-existing failing test `test_ai_retreats_when_mp_high_and_close`

## Tuning Knobs (for future iterations)

- Cast pushback magnitudes: attacker `-7.0`, defender `+5.0`
- `windup_stun_until_ms` duration: `200ms`
- Release flash: `lifetime=6`, `max_radius=120`, burst `count=16`, `speed=10.0`, screen flash `alpha=120`, `frames=4`
- `FRAME_MS = 1000.0 / FPS`
