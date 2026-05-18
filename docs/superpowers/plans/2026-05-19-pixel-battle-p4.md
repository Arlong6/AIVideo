# Pixel Battle P4 Spacing + Audio Sync + Cast Spectacle Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix character overlap, audio drift, missing cast SFX, and flat cast performance — push sprites apart on skill cast, align audio to video time, add cast SFX + release flash + zoom + motion lines.

**Architecture:** Surgical edits — physics collision + AI band + cast pushback in Battle; episode-runner tracks `event_video_ms` for audio sync; new procedural cast SFX script; extensions to ChargeFXSystem, ImpactFXSystem, and Renderer for release flash + zoom + motion lines.

**Tech Stack:** Python 3, pygame, numpy, pytest.

**Spec:** `docs/superpowers/specs/2026-05-19-pixel-battle-p4-design.md`

---

## File Structure

**Create:**
- `pixel_battle/scripts/gen_cast_sfx.py` — procedural cast SFX generator
- `pixel_battle/assets/sfx/cast_cooldown.wav` (via script)
- `pixel_battle/assets/sfx/cast_special.wav` (via script)
- `pixel_battle/tests/test_character_collision.py`
- `pixel_battle/tests/test_cast_pushback.py`
- `pixel_battle/tests/test_audio_video_ms_map.py`

**Modify:**
- `pixel_battle/engine/battle.py` — collision resolver, AI band, cast pushback
- `pixel_battle/engine/charge_fx.py` — motion lines (drawn behind sparkles)
- `pixel_battle/engine/impact_fx.py` — `spawn_release_flash` method
- `pixel_battle/engine/renderer.py` — `set_zoom` + `_apply_zoom`
- `pixel_battle/episodes/ep01_brick_vs_glass.py` — `event_video_ms` map, charge release callback, zoom set/reset
- `pixel_battle/video/compose.py` — accept `event_video_ms`, cast SFX overlay for ATTACK_WINDUP

---

## Task 1: Character collision in `_update_physics`

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`
- Create: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_character_collision.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_character_collision.py`:

```python
"""P4: Characters cannot overlap — physical collision after physics tick."""
from pixel_battle.engine.battle import Battle, MIN_CHAR_DISTANCE
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import ARENA_LEFT, ARENA_RIGHT


def _battle():
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    bat.tick_ms(2500)  # past intro
    return bat, a, b


def test_overlapping_chars_pushed_apart():
    """When two chars are closer than MIN_CHAR_DISTANCE, collision resolver pushes them apart."""
    bat, a, b = _battle()
    a.pos_x = 200
    b.pos_x = 220  # only 20px apart
    bat._resolve_character_collision()
    new_distance = abs(a.pos_x - b.pos_x)
    assert new_distance >= MIN_CHAR_DISTANCE


def test_chars_at_min_distance_unchanged():
    """When chars are at exactly MIN_CHAR_DISTANCE, no push."""
    bat, a, b = _battle()
    a.pos_x = 200
    b.pos_x = 200 + MIN_CHAR_DISTANCE
    before_a, before_b = a.pos_x, b.pos_x
    bat._resolve_character_collision()
    assert a.pos_x == before_a
    assert b.pos_x == before_b


def test_chars_far_apart_unchanged():
    """When chars are well separated, collision does nothing."""
    bat, a, b = _battle()
    a.pos_x = 100
    b.pos_x = 400
    before_a, before_b = a.pos_x, b.pos_x
    bat._resolve_character_collision()
    assert a.pos_x == before_a
    assert b.pos_x == before_b


def test_pushed_positions_stay_in_arena():
    """Even if char is at arena edge and other is on top, collision doesn't push outside."""
    bat, a, b = _battle()
    a.pos_x = ARENA_LEFT
    b.pos_x = ARENA_LEFT + 10  # very overlapping, both near left wall
    bat._resolve_character_collision()
    assert a.pos_x >= ARENA_LEFT
    assert b.pos_x <= ARENA_RIGHT


def test_tick_ms_runs_collision_after_physics():
    """tick_ms invokes _resolve_character_collision so overlap is corrected each frame."""
    bat, a, b = _battle()
    # Force overlap and let tick_ms run
    a.pos_x = 250
    b.pos_x = 260
    bat.tick_ms(16)
    assert abs(a.pos_x - b.pos_x) >= MIN_CHAR_DISTANCE
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_character_collision.py -v
```
Expected: ImportError for `MIN_CHAR_DISTANCE` and missing method.

- [ ] **Step 3: Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`**

Near the top of the file, find the constants block (around `RETREAT_DURATION_MS`). Add a new constant after the existing AI tuning constants:

```python
MIN_CHAR_DISTANCE = 70              # px; min horizontal distance between character centers
```

In `Battle` class, find `_update_physics` (called twice from `tick_ms` for left and right). After the second `_update_physics(self.right, dt_ms)` call (around line 121 area), add a call to a new method.

Find the block in `tick_ms`:
```python
        # Update physics for both characters
        self._update_physics(self.left, dt_ms)
        self._update_physics(self.right, dt_ms)
```

Add immediately after:
```python
        # Resolve character collision (no overlap)
        self._resolve_character_collision()
```

Add the new method on the `Battle` class. Place it right after `_update_physics`:

```python
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
```

`clamp_x` is already imported at the top of battle.py (verify import line near top includes it).

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_character_collision.py pixel_battle/tests/test_battle.py -v
```
Expected: all PASS (the pre-existing `test_ai_retreats_when_mp_high_and_close` may still fail — unrelated).

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_character_collision.py
git commit -m "feat(pixel-battle): character collision — no overlap"
```

---

## Task 2: AI maintains kill-zone band (no clinching)

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`

- [ ] **Step 1: Read the current `_ai_choose_action` body**

```bash
grep -n "distance > MELEE_RANGE" /Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py
```

Confirm: line `if distance > MELEE_RANGE * 0.8:` exists in `_ai_choose_action`.

- [ ] **Step 2: Edit `_ai_choose_action` for kill-zone band**

In `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`, find this block inside `_ai_choose_action`:

```python
        if distance > MELEE_RANGE * 0.8:
            # Close the distance
            self._start_walk(char, char.facing)
            # Small jump chance while approaching
            if char.on_ground and self.rng.roll_check(AI_JUMP_APPROACH_PROB):
                self._start_jump(char)
        else:
            # In range — mixed tactics
            roll = self.rng.uniform()
            if roll < AI_ATTACK_IN_RANGE_PROB:
```

Replace with:

```python
        if distance > MELEE_RANGE * 0.95:
            # Approach — too far to fight
            self._start_walk(char, char.facing)
            # Small jump chance while approaching
            if char.on_ground and self.rng.roll_check(AI_JUMP_APPROACH_PROB):
                self._start_jump(char)
        elif distance < MELEE_RANGE * 0.55:
            # Too close — back off slightly so attacks/effects are visible
            self._start_walk(char, -char.facing)
        else:
            # Kill zone (0.55–0.95 * MELEE_RANGE) — mixed tactics
            roll = self.rng.uniform()
            if roll < AI_ATTACK_IN_RANGE_PROB:
```

(Only the if/elif/else header changes; the existing in-range block underneath stays intact.)

- [ ] **Step 3: Run all battle tests for no regression**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_battle.py pixel_battle/tests/test_battle_ai_priority.py pixel_battle/tests/test_ai_retreat_lock.py pixel_battle/tests/test_battle_no_lock.py pixel_battle/tests/test_character_collision.py -v
```
Expected: all PASS (allow pre-existing `test_ai_retreats_when_mp_high_and_close`).

- [ ] **Step 4: Commit**

```bash
git add pixel_battle/engine/battle.py
git commit -m "feat(pixel-battle): AI maintains kill-zone band (back off when too close)"
```

---

## Task 3: Cast pushback on CD/special attack start

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`
- Create: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_cast_pushback.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_cast_pushback.py`:

```python
"""P4: Cast pushback creates space when CD/special attacks fire."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle_in_range(seed=42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)
    a.pos_x = 200
    b.pos_x = 280  # in range
    return bat, a, b


def test_cd_skill_attack_pushes_attacker_backward():
    """When a CD skill is chosen, attacker.vel_x becomes negative-toward-defender."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0  # gate out specials
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1  # facing right (defender is right)
    a.vel_x = 0.0
    b.vel_x = 0.0
    # Force CD path by leveraging _choose_attack_skill seeded RNG; retry up to 30 times
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found, "Couldn't force CD skill choice"
    # facing=1 means defender is right → attacker pushback should be leftward (negative vel_x)
    assert a.vel_x < 0, f"Expected attacker pushed back, got vel_x={a.vel_x}"


def test_cd_skill_attack_pushes_defender_slightly():
    """Defender gets a small push away from attacker."""
    bat, a, b = _battle_in_range(seed=42)
    a.mp = 0
    a.skill_cd_ready_at = {}
    a.last_attack_ms = -10000
    a.facing = 1
    found = False
    for _ in range(30):
        a.action_state = "idle"
        a.attack_phase = "none"
        a.vel_x = 0.0
        b.vel_x = 0.0
        bat._start_attack(a, b)
        if a.attack_used_kind.skill_type is SkillType.COOLDOWN:
            found = True
            break
    assert found
    # Defender should drift rightward (away from attacker who is left)
    assert b.vel_x > 0, f"Expected defender drifted away, got vel_x={b.vel_x}"


def test_basic_attack_does_not_pushback():
    """Basic skill: no cast pushback."""
    bat, a, b = _battle_in_range(seed=1)
    a.mp = 0
    a.skill_cd_ready_at[a.skills_of_type(SkillType.COOLDOWN)[0].id] = 999_999
    a.last_attack_ms = -10000
    a.facing = 1
    a.vel_x = 0.0
    b.vel_x = 0.0
    bat._start_attack(a, b)
    assert a.attack_used_kind.skill_type is SkillType.BASIC
    assert a.vel_x == 0.0
    assert b.vel_x == 0.0
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_cast_pushback.py -v
```
Expected: tests FAIL (no pushback in _start_attack yet).

- [ ] **Step 3: Edit `_start_attack` in battle.py**

In `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`, find `_start_attack`:

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
        # Emit windup event for non-basic skills so the renderer can show charge FX
        if skill.skill_type in (SkillType.COOLDOWN, SkillType.SPECIAL):
            self._emit(
                EventType.ATTACK_WINDUP,
                actor=char.id,
                extra={"skill_id": skill.id,
                       "skill_type": skill.skill_type.value},
            )
```

Replace with:

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

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_cast_pushback.py pixel_battle/tests/test_battle.py pixel_battle/tests/test_battle_attack_windup_event.py -v
```
Expected: PASS (allow pre-existing failure).

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_cast_pushback.py
git commit -m "feat(pixel-battle): cast pushback on CD/special — creates skill visibility space"
```

---

## Task 4: Audio sync — compose.py accepts `event_video_ms` map

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/video/compose.py`
- Create: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_audio_video_ms_map.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_audio_video_ms_map.py`:

```python
"""P4: build_audio_track accepts event_video_ms map for sync correction."""
import os
import tempfile
from pathlib import Path

from pydub import AudioSegment

from pixel_battle.engine.battle import Event, EventType
from pixel_battle.video.compose import build_audio_track


def test_build_audio_track_accepts_event_video_ms_map():
    """build_audio_track signature accepts event_video_ms keyword argument."""
    events = []
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        build_audio_track(events, total_duration_ms=2000,
                           output_path=str(out),
                           event_offset_ms=0,
                           event_video_ms={})
        assert out.exists()


def test_event_video_ms_overrides_t_ms_position():
    """When event_video_ms[id(ev)] is set, use that as audio position instead of ev.t_ms+offset."""
    ev = Event(type=EventType.HIT, t_ms=1000, actor="a", target="b", amount=5,
                extra={"crit": False})
    events = [ev]
    with tempfile.TemporaryDirectory() as tmp:
        # Without map: SFX positioned at t_ms + offset = 1000 + 500 = 1500ms
        out1 = Path(tmp) / "without_map.wav"
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out1), event_offset_ms=500)
        # With map: override position to 2000ms
        out2 = Path(tmp) / "with_map.wav"
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out2), event_offset_ms=500,
                           event_video_ms={id(ev): 2000})
        # Both succeed and produce non-empty output
        a1 = AudioSegment.from_file(out1)
        a2 = AudioSegment.from_file(out2)
        # Audio tracks have the same total duration
        assert abs(len(a1) - len(a2)) < 100
        # Different content — overlay position differs.
        # Simple proxy: dBFS values differ in the 1500ms vs 2000ms region.
        # Sample some frames around the two positions to confirm they differ.
        seg_at_1500_no_map = a1[1450:1550]
        seg_at_2000_no_map = a1[1950:2050]
        seg_at_1500_with_map = a2[1450:1550]
        seg_at_2000_with_map = a2[1950:2050]
        # In a1 (no map), 1500 has audio energy, 2000 is silent
        # In a2 (with map), 2000 has audio energy, 1500 is silent
        # Use RMS energy to verify
        assert seg_at_1500_no_map.rms > seg_at_1500_with_map.rms or \
               seg_at_2000_with_map.rms > seg_at_2000_no_map.rms


def test_event_video_ms_falls_back_to_t_ms_when_missing():
    """If event_video_ms map doesn't contain the event, fall back to t_ms + offset."""
    ev = Event(type=EventType.HIT, t_ms=1000, actor="a", target="b", amount=5,
                extra={"crit": False})
    events = [ev]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "audio.wav"
        # Empty map — event not in map, should fall back
        build_audio_track(events, total_duration_ms=3000,
                           output_path=str(out), event_offset_ms=500,
                           event_video_ms={})
        assert out.exists()
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_audio_video_ms_map.py -v
```
Expected: TypeError — `event_video_ms` is not a valid kwarg.

- [ ] **Step 3: Edit `/Users/arlong/Projects/AIvideo/pixel_battle/video/compose.py`**

Find the existing function signature:
```python
def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str,
                      event_offset_ms: int = 0) -> None:
```

Replace with:
```python
def build_audio_track(events: List[Event], total_duration_ms: int, output_path: str,
                      event_offset_ms: int = 0,
                      event_video_ms: dict | None = None) -> None:
    """Render BGM + SFX into a single wav matching total_duration_ms.

    event_offset_ms: time offset in audio at which battle starts.
                     Add to each event's t_ms when overlaying SFX (default path).
    event_video_ms:  optional {id(event): video_ms} map. When provided and
                     id(event) is in the map, use that value instead of
                     ev.t_ms + event_offset_ms. Used to correct for hit-stop
                     accumulation that pushes video behind battle-time.
    """
```

Find the position-computation block inside the events loop:
```python
    for ev in events:
        # Shift event position by intro offset so SFX aligns with video frame
        pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue  # off-end, skip
```

Replace with:
```python
    for ev in events:
        # Position: use event_video_ms[id(ev)] if provided (P4 sync correction),
        # else fall back to ev.t_ms + event_offset_ms
        if event_video_ms is not None and id(ev) in event_video_ms:
            pos = event_video_ms[id(ev)]
        else:
            pos = ev.t_ms + event_offset_ms
        if pos >= total_duration_ms:
            continue  # off-end, skip
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_audio_video_ms_map.py pixel_battle/tests/test_compose.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/video/compose.py pixel_battle/tests/test_audio_video_ms_map.py
git commit -m "feat(pixel-battle): compose.py accepts event_video_ms for audio sync"
```

---

## Task 5: Generate cast SFX (numpy)

**Files:**
- Create: `/Users/arlong/Projects/AIvideo/pixel_battle/scripts/gen_cast_sfx.py`
- Create (via script): `/Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_cooldown.wav`
- Create (via script): `/Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_special.wav`

- [ ] **Step 1: Create the script**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/scripts/gen_cast_sfx.py`:

```python
"""One-shot: generate cast SFX files via numpy.

Run once:  python3 -m pixel_battle.scripts.gen_cast_sfx

Outputs:
  pixel_battle/assets/sfx/cast_cooldown.wav  — short 'tssht' for CD skills (~0.25s)
  pixel_battle/assets/sfx/cast_special.wav   — bright 'zwoom' for specials (~0.35s)
"""
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44100
SFX_DIR = Path(__file__).resolve().parents[1] / "assets" / "sfx"


def _write_wav(path: Path, samples: np.ndarray) -> None:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def _gen_cast_cooldown() -> np.ndarray:
    """Short 'tssht!' — 220Hz triangle + white noise hiss, 250ms with sharp decay."""
    duration = 0.25
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # 220Hz triangle (low rumble), fast decay
    tri = 2 * np.abs(2 * (t * 220 - np.floor(t * 220 + 0.5))) - 1
    body_env = np.exp(-t * 12.0)
    # White noise hiss, faster decay
    hiss = np.random.uniform(-1, 1, n)
    hiss_env = np.exp(-t * 20.0)
    samples = tri * 0.45 * body_env + hiss * 0.35 * hiss_env
    return samples


def _gen_cast_special() -> np.ndarray:
    """Bright 'zwoom!' — 400→1200Hz chirp UP + 1760Hz bell, 350ms."""
    duration = 0.35
    n = int(SAMPLE_RATE * duration)
    t = np.linspace(0, duration, n, endpoint=False)
    # Upward chirp 400→1200Hz over first 150ms
    chirp_start, chirp_end = 0.00, 0.15
    freq = np.where(
        (t >= chirp_start) & (t < chirp_end),
        400 + (1200 - 400) * (t - chirp_start) / (chirp_end - chirp_start),
        0,
    )
    chirp_phase = 2 * np.pi * np.cumsum(freq) / SAMPLE_RATE
    chirp = np.sin(chirp_phase)
    chirp_env = np.where((t >= chirp_start) & (t < chirp_end), 1.0, 0.0)
    # 1760Hz bell tone after chirp, with exponential decay
    bell = np.sin(2 * np.pi * 1760 * t)
    bell_env = np.where(t >= 0.10, np.exp(-(t - 0.10) * 8.0), 0.0)
    samples = chirp * 0.50 * chirp_env + bell * 0.35 * bell_env
    return samples


def main() -> None:
    np.random.seed(7)
    SFX_DIR.mkdir(parents=True, exist_ok=True)
    _write_wav(SFX_DIR / "cast_cooldown.wav", _gen_cast_cooldown())
    _write_wav(SFX_DIR / "cast_special.wav", _gen_cast_special())
    print(f"Generated cast SFX in {SFX_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the script**

```bash
cd /Users/arlong/Projects/AIvideo && python3 -m pixel_battle.scripts.gen_cast_sfx
```
Expected: prints `Generated cast SFX in ...`.

- [ ] **Step 3: Verify files**

```bash
ls -la /Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_cooldown.wav /Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_special.wav
```
Expected: both files > 15KB.

- [ ] **Step 4: Commit**

```bash
git add pixel_battle/scripts/gen_cast_sfx.py pixel_battle/assets/sfx/cast_cooldown.wav pixel_battle/assets/sfx/cast_special.wav
git commit -m "feat(pixel-battle): procedural cast SFX (cooldown/special)"
```

---

## Task 6: compose.py plays cast SFX on ATTACK_WINDUP

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/video/compose.py`

- [ ] **Step 1: Edit `build_audio_track` to handle ATTACK_WINDUP**

In `/Users/arlong/Projects/AIvideo/pixel_battle/video/compose.py`, find the events loop. After the existing `if ev.type is EventType.HIT:` branch, before `elif ev.type is EventType.CRIT:`, add:

```python
        elif ev.type is EventType.ATTACK_WINDUP:
            st = ev.extra.get("skill_type", "") if ev.extra else ""
            cast_name = f"cast_{st}"  # cast_cooldown / cast_special
            cast_sfx = _load_sfx_or_none(cast_name)
            if cast_sfx:
                track = track.overlay(cast_sfx, position=pos)
```

The full event-handler if/elif chain after this change should be:
- `if ev.type is EventType.HIT:` (existing)
- `elif ev.type is EventType.ATTACK_WINDUP:` (NEW)
- `elif ev.type is EventType.CRIT:` (existing)
- `elif ev.type is EventType.ULTIMATE_START:` (existing)
- `elif ev.type is EventType.KO:` (existing)

- [ ] **Step 2: Run tests for no regression**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_compose.py pixel_battle/tests/test_audio_video_ms_map.py -v
```
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add pixel_battle/video/compose.py
git commit -m "feat(pixel-battle): compose plays cast SFX on ATTACK_WINDUP"
```

---

## Task 7: `ImpactFXSystem.spawn_release_flash` method

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/impact_fx.py`
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_impact_fx.py`

- [ ] **Step 1: Append failing test**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_impact_fx.py`:

```python
def test_spawn_release_flash_creates_short_lived_big_ring():
    """spawn_release_flash adds a ring with bigger max_radius and shorter lifetime than default."""
    sys = ImpactFXSystem()
    sys.spawn_release_flash(x=240, y=400, color=(80, 180, 255))
    assert len(sys.rings) == 1
    r = sys.rings[0]
    assert r.max_radius == 80   # bigger than default 60
    assert r.lifetime == 3      # shorter than default 8
    assert r.color == (80, 180, 255)
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_impact_fx.py::test_spawn_release_flash_creates_short_lived_big_ring -v
```
Expected: AttributeError — no `spawn_release_flash`.

- [ ] **Step 3: Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/impact_fx.py`**

Find the `spawn_ring` method:
```python
    def spawn_ring(self, x: float, y: float,
                   color: Tuple[int, int, int]) -> None:
        self.rings.append(ImpactRing(x=x, y=y, color=color))
```

Add a new method right after it:
```python
    def spawn_release_flash(self, x: float, y: float,
                            color: Tuple[int, int, int]) -> None:
        """Bigger, shorter ring used at skill release (vs hit landing)."""
        self.rings.append(ImpactRing(
            x=x, y=y, color=color,
            lifetime=3, max_radius=80,
        ))
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_impact_fx.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/impact_fx.py pixel_battle/tests/test_impact_fx.py
git commit -m "feat(pixel-battle): ImpactFX.spawn_release_flash — bigger short ring for skill release"
```

---

## Task 8: ChargeFX motion lines

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/charge_fx.py`
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_charge_fx.py`

- [ ] **Step 1: Append failing test**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_charge_fx.py`:

```python
def test_motion_lines_render_does_not_crash():
    """Motion lines drawn during charge — smoke test."""
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ChargeFXSystem()
    sys.spawn(x=200, y=400, color=(80, 180, 255))
    # Render multiple frames so the motion lines have time to draw
    for _ in range(6):
        sys.update_and_render(surface)
    # No crash + effect still exists
    assert len(sys.effects) == 1


def test_motion_lines_alpha_decreases_with_index():
    """Lower indexed motion lines (closer to attacker) have higher alpha than far ones."""
    from pixel_battle.engine.charge_fx import _motion_line_alpha
    # At frame 0, index 0 (innermost) > index 3 (outermost)
    assert _motion_line_alpha(line_index=0, eff_age=0) > _motion_line_alpha(line_index=3, eff_age=0)
    # All alphas non-negative
    for i in range(4):
        for f in range(15):
            assert _motion_line_alpha(line_index=i, eff_age=f) >= 0
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_charge_fx.py -v
```
Expected: ImportError for `_motion_line_alpha`.

- [ ] **Step 3: Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/charge_fx.py`**

At the module-level (after imports, before `ChargeEffect` dataclass), add:

```python
def _motion_line_alpha(line_index: int, eff_age: int) -> int:
    """Alpha for the motion line at given index and effect age. Closer lines (lower index) are brighter."""
    return max(0, 200 - line_index * 50 - eff_age * 8)
```

In `ChargeFXSystem.update_and_render`, find the section that draws sparkles. It currently looks like:
```python
            radius = self._current_orbit_radius(eff)
            alpha = int(255 * (eff.age / eff.lifetime))  # brighter as it converges
            for i in range(self.SPARKLE_COUNT):
                ...
            survivors.append(eff)
```

Add a motion-lines render block IMMEDIATELY BEFORE the sparkle loop:

```python
            # Motion lines (drawn before sparkles, "behind" the attacker)
            for i in range(4):
                line_alpha = _motion_line_alpha(i, eff.age)
                if line_alpha <= 0:
                    continue
                offset_x = -40 - (i * 8) + eff.age * 2   # pull in toward attacker
                offset_y = -50 - i * 20
                line_surface = pygame.Surface((16, 2), pygame.SRCALPHA)
                line_surface.fill((*eff.color, line_alpha))
                surface.blit(line_surface, (int(eff.x + offset_x), int(eff.y + offset_y)))

            radius = self._current_orbit_radius(eff)
            alpha = int(255 * (eff.age / eff.lifetime))  # brighter as it converges
            for i in range(self.SPARKLE_COUNT):
                ...  # (existing sparkle code unchanged)
            survivors.append(eff)
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_charge_fx.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/charge_fx.py pixel_battle/tests/test_charge_fx.py
git commit -m "feat(pixel-battle): ChargeFX motion lines — speed lines during windup"
```

---

## Task 9: Renderer camera zoom

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/engine/renderer.py`
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_renderer.py`

- [ ] **Step 1: Append failing tests**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_renderer.py`:

```python
def test_renderer_default_zoom_is_one():
    pygame.init()
    r = Renderer()
    assert r._zoom_factor == 1.0


def test_set_zoom_updates_factor_and_center():
    pygame.init()
    r = Renderer()
    r.set_zoom(1.04, (200, 400))
    assert r._zoom_factor == 1.04
    assert r._zoom_center == (200, 400)


def test_render_frame_with_zoom_does_not_crash():
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    r.set_zoom(1.04, (200, 400))
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=0, elapsed_ms=1000)
    # Reset zoom and re-render
    r.set_zoom(1.0, (240, 427))
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=0, elapsed_ms=1000)
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_renderer.py -v
```
Expected: 3 new tests FAIL (no `_zoom_factor` / `set_zoom`).

- [ ] **Step 3: Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/renderer.py`**

In `Renderer.__init__`, find the existing impact_fx block (added in P3.8):
```python
        # Impact FX (expanding rings + screen flash on big hits)
        from pixel_battle.engine.impact_fx import ImpactFXSystem
        self.impact_fx = ImpactFXSystem()
```

Add IMMEDIATELY AFTER:
```python
        # Camera zoom state (P4) — 1.0 = no zoom, > 1 = zoomed in on _zoom_center
        self._zoom_factor: float = 1.0
        self._zoom_center: tuple = (WIDTH // 2, HEIGHT // 2)
```

Add new methods on `Renderer` class. Place them right after `set_hud`:

```python
    def set_zoom(self, factor: float, center: tuple) -> None:
        """Set camera zoom factor and center for the next render_frame call(s).
        Pass factor=1.0 to reset."""
        self._zoom_factor = factor
        self._zoom_center = center

    def _apply_zoom(self) -> None:
        """Scale the surface around _zoom_center by _zoom_factor.
        Done in-place: scales up, crops to original dimensions centered on zoom point.
        """
        if self._zoom_factor == 1.0:
            return
        w, h = self.surface.get_size()
        zoom = self._zoom_factor
        cx, cy = self._zoom_center
        scaled = pygame.transform.smoothscale(self.surface,
                                               (max(1, int(w * zoom)),
                                                max(1, int(h * zoom))))
        # Crop region centered on (cx*zoom, cy*zoom)
        crop_x = max(0, min(int(cx * zoom - w / 2),
                            scaled.get_width() - w))
        crop_y = max(0, min(int(cy * zoom - h / 2),
                            scaled.get_height() - h))
        self.surface.fill((0, 0, 0))
        self.surface.blit(scaled, (-crop_x, -crop_y))
```

In `render_frame`, find the line:
```python
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

Replace with:
```python
        # Camera zoom (applied before screen shake)
        self._apply_zoom()
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_renderer.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/renderer.py pixel_battle/tests/test_renderer.py
git commit -m "feat(pixel-battle): Renderer camera zoom (set_zoom + _apply_zoom)"
```

---

## Task 10: Episode runner — `event_video_ms` map + charge release callback + zoom set/reset + ATTACK_WINDUP timing

**Files:**
- Modify: `/Users/arlong/Projects/AIvideo/pixel_battle/episodes/ep01_brick_vs_glass.py`

- [ ] **Step 1: Read current main() event-loop structure**

```bash
grep -n "EventType\.ATTACK_WINDUP\|EventType\.HIT\|build_audio_track\|frame_no" /Users/arlong/Projects/AIvideo/pixel_battle/episodes/ep01_brick_vs_glass.py | head -20
```

Confirm:
- `EventType.ATTACK_WINDUP` is handled in the event loop (added in P3.9)
- `build_audio_track(...)` is called near the end of main()
- `frame_no` is incremented per video frame

- [ ] **Step 2: Add event_video_ms map declaration in main()**

In `/Users/arlong/Projects/AIvideo/pixel_battle/episodes/ep01_brick_vs_glass.py`, find this line near the top of main() (after `cinematic_frame_idx = 0.0`):
```python
    active_captions = []  # list of (text, style, started_frame, pos|None)
```

Add IMMEDIATELY AFTER:
```python
    event_video_ms = {}  # id(event) -> video_ms (P4 audio sync correction)
```

- [ ] **Step 3: Populate event_video_ms inside the event loop**

Find the line:
```python
        for ev in new_events:
```

Add IMMEDIATELY AFTER (preserving the same indentation as the body of the loop):
```python
            # P4 audio sync: record video-frame time of this event
            event_video_ms[id(ev)] = frame_no * TICK_MS
```

- [ ] **Step 4: Update ATTACK_WINDUP handler to wire on_complete callback + zoom set**

Find the existing ATTACK_WINDUP block (added in P3.9):
```python
            if ev.type is EventType.ATTACK_WINDUP:
                actor = left if ev.actor == left.id else right
                st = ev.extra.get("skill_type", "basic") if ev.extra else "basic"
                color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))
                renderer.charge_fx.spawn(x=int(actor.pos_x),
                                          y=int(actor.pos_y),
                                          color=color)
                continue  # nothing else for this event type
```

Replace with:
```python
            if ev.type is EventType.ATTACK_WINDUP:
                actor = left if ev.actor == left.id else right
                st = ev.extra.get("skill_type", "basic") if ev.extra else "basic"
                color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))
                actor_x_int = int(actor.pos_x)
                actor_y_int = int(actor.pos_y)

                def _release_callback(rx=actor_x_int, ry=actor_y_int - 80,
                                       c=color):
                    renderer.impact_fx.spawn_release_flash(rx, ry, c)
                    renderer.particles.emit_hit_burst(rx, ry, color=c,
                                                       count=8, speed=8.0)
                    # Reset zoom when charge finishes
                    renderer.set_zoom(1.0, (WIDTH // 2, HEIGHT // 2))

                renderer.charge_fx.spawn(x=actor_x_int, y=actor_y_int,
                                          color=color,
                                          on_complete=_release_callback)
                # Zoom in slightly on attacker during windup
                renderer.set_zoom(1.04, (actor_x_int, actor_y_int - 80))
                continue
```

- [ ] **Step 5: Update build_audio_track call to pass the map**

Find the existing call near the end of main():
```python
    build_audio_track(battle.events,
                      total_duration_ms=total_ms,
                      output_path=str(audio_out),
                      event_offset_ms=intro_offset_ms)
```

Replace with:
```python
    # P4: audio sync uses recorded video-time per event when available
    # (events processed during cinematics / hit-stop have video time > battle time)
    # Adjust map values by intro_offset_ms so they line up with audio timeline
    audio_event_video_ms = {
        ev_id: ms + intro_offset_ms for ev_id, ms in event_video_ms.items()
    }
    build_audio_track(battle.events,
                      total_duration_ms=total_ms,
                      output_path=str(audio_out),
                      event_offset_ms=intro_offset_ms,
                      event_video_ms=audio_event_video_ms)
```

- [ ] **Step 6: Run all tests for no regression**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/ -v 2>&1 | tail -15
```
Expected: all PASS (allow pre-existing `test_ai_retreats_when_mp_high_and_close`).

- [ ] **Step 7: Commit**

```bash
git add pixel_battle/episodes/ep01_brick_vs_glass.py
git commit -m "feat(pixel-battle): episode runner — event_video_ms map + release callback + zoom"
```

---

## Task 11: Visual regression — regenerate `final.mp4` and verify

- [ ] **Step 1: Run the episode**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pixel_battle.episodes.ep01_brick_vs_glass
```
Expected: completes without error, prints winner + duration.

- [ ] **Step 2: Verify video metadata**

```bash
ffprobe -v error -show_entries format=duration,size:stream=width,height,codec_name -of default=noprint_wrappers=1 /Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/final.mp4
```
Expected: 480×854, h264, duration 8-60s.

- [ ] **Step 3: Verify ATTACK_WINDUP events still present + no overlap regression**

```bash
python3 << 'EOF'
import json
from collections import Counter
with open('/Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/battle_events.json') as f:
    events = json.load(f)
counts = Counter(e['type'] for e in events)
print('Event counts:', dict(counts))
assert counts.get('attack_windup', 0) > 0
assert counts.get('hit', 0) > 0

# Long-gap regression check
action = [e for e in events if e['type'] in ('hit', 'miss')]
if action:
    starts = [e['t_ms'] for e in events if e['type'] == 'ultimate_start']
    ends = [e['t_ms'] for e in events if e['type'] == 'ultimate_end']
    cinematic = list(zip(starts, ends))
    def in_c(t): return any(s <= t <= e for s, e in cinematic)
    gaps = []
    prev = 0
    for e in action:
        if not in_c(e['t_ms']):
            gap = e['t_ms'] - prev
            for s, ee in cinematic:
                if s >= prev and ee <= e['t_ms']:
                    gap -= (ee - s)
            gaps.append(gap)
            prev = e['t_ms']
    print(f'Max action gap: {max(gaps)/1000:.1f}s')

cd_hits = [e for e in events if e['type'] == 'hit' and e.get('extra', {}).get('skill_type') == 'cooldown']
sp_hits = [e for e in events if e['type'] == 'hit' and e.get('extra', {}).get('skill_type') == 'special']
ko_events = [e for e in events if e['type'] == 'ko']
print(f'CD-skill hits: {len(cd_hits)}, Special hits: {len(sp_hits)}, KO events: {len(ko_events)}')
EOF
```

- [ ] **Step 4: Verify cast SFX files present**

```bash
ls -la /Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_cooldown.wav /Users/arlong/Projects/AIvideo/pixel_battle/assets/sfx/cast_special.wav
```
Expected: both files exist, > 15KB.

- [ ] **Step 5: Verify audio multiplex**

```bash
ffprobe -v error -select_streams a -show_entries stream=codec_name,duration -of default=noprint_wrappers=1 /Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/final.mp4
```
Expected: aac, duration matches video.

- [ ] **Step 6: Git status check**

```bash
git status
```
Expected: clean (output/ .gitignored).

- [ ] **Step 7: Report**

Summarize:
- Episode duration + winner (KO vs Draw)
- ATTACK_WINDUP / CD-skill / Special / KO event counts
- Max action gap (< 5s expected)
- Cast SFX files present
- Any errors

Do NOT open the video — user does that.

---

## Self-Review

**Spec coverage:**
- A1 character collision → Task 1 ✓
- A2 AI band → Task 2 ✓
- A3 cast pushback → Task 3 ✓
- B1+B2 audio sync map → Tasks 4, 10 ✓
- C1 cast SFX gen → Task 5 ✓
- C2 compose plays cast SFX → Task 6 ✓
- D1 release flash → Task 7 (impact method) + Task 10 (callback wiring) ✓
- D2 camera zoom → Task 9 (renderer) + Task 10 (episode wiring) ✓
- D3 motion lines → Task 8 ✓
- Visual regression → Task 11 ✓

**Placeholder scan:** No TBDs. Every code-bearing step has full code.

**Type consistency:**
- `MIN_CHAR_DISTANCE` constant — used in Task 1 ✓
- `Battle._resolve_character_collision()` method — defined Task 1, called from `tick_ms` Task 1 ✓
- `build_audio_track(..., event_video_ms=None)` signature — Tasks 4, 6, 10 consistent ✓
- `ImpactFXSystem.spawn_release_flash(x, y, color)` — Task 7 defined, Task 10 consumed ✓
- `Renderer.set_zoom(factor, center)` + `_zoom_factor`, `_zoom_center` — Task 9 defined, Task 10 consumed ✓
- Cast SFX filenames `cast_cooldown.wav` / `cast_special.wav` matching `cast_{skill_type}` lookup in Task 6 ✓
- `_motion_line_alpha(line_index, eff_age)` helper — Task 8 defined and tested ✓

No issues found.
