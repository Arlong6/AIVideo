# Pixel Battle RL Stickfight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace sprite-driven combat with procedurally-drawn stick figures controlled by a PPO self-play agent trained on the existing `Battle` engine.

**Architecture:** Add a new `pixel_battle/rl/` package with stick renderer + Gymnasium env + PPO training + playback. Inject two tiny shims into `engine/battle.py` (`skip_ai` flag on `tick_ms`, new `_start_attack_with_kind`) so the existing physics/MP/cooldown logic is preserved while letting the policy take over decision-making. Existing sprite/audio pipelines stay untouched.

**Tech Stack:** Python 3.10, pygame (rendering), Gymnasium (RL env API), stable-baselines3 + PyTorch (PPO), numpy.

**Spec:** `docs/superpowers/specs/2026-05-20-pixel-battle-rl-stickfight-design.md`

---

## File Structure

**New (this plan creates):**
- `pixel_battle/rl/__init__.py` — empty package marker
- `pixel_battle/rl/stick_renderer.py` — procedural stick draw (single function: `draw_stick_figure`)
- `pixel_battle/rl/env.py` — Gymnasium env: `PixelBattleEnv` (paired observation, paired step return)
- `pixel_battle/rl/train.py` — PPO training driver with self-play wrapper
- `pixel_battle/rl/play.py` — loads checkpoint, renders fight via existing audio + video pipeline
- `pixel_battle/episodes/sticks_demo.py` — Phase 1 deliverable: heuristic AI + stick visuals (no RL yet)

**Modified:**
- `pixel_battle/engine/battle.py:94` — `tick_ms` gains optional `skip_ai: bool = False`
- `pixel_battle/engine/battle.py` (append) — new `_start_attack_with_kind(char, opp, kind)` method

**New tests:**
- `pixel_battle/tests/test_stick_renderer.py`
- `pixel_battle/tests/test_battle_skip_ai.py`
- `pixel_battle/tests/test_battle_start_attack_with_kind.py`
- `pixel_battle/tests/test_rl_env.py`

**Untouched:** `engine/character.py`, `engine/physics.py`, all `video/`, all existing `episodes/*`, all `assets/`.

**Gitignored** (add to `.gitignore`): `data/rl_checkpoints/`

---

## Implementation Order

Each phase produces a watchable video deliverable.

**Phase 1 — Stick visuals**
1. `stick_renderer.draw_stick_figure` (TDD)
2. `episodes/sticks_demo.py` runs existing engine with stick visuals → Phase 1 video

**Phase 2 — Gym env**
3. Install `gymnasium` + `stable_baselines3` + `torch`
4. `Battle.tick_ms(skip_ai=True)` shim (TDD)
5. `Battle._start_attack_with_kind` shim (TDD)
6. `PixelBattleEnv.reset / step / observation / action mapping` (TDD)
7. Random-agent smoke test → Phase 2 video

**Phase 3 — PPO training**
8. `SinglePerspectiveEnv` self-play wrapper (TDD)
9. `train.py` with PPO + checkpoint callback
10. Run 500K-step training → checkpoint artifact

**Phase 4 — Final render**
11. `play.py` loads checkpoint, renders fight with sticks + audio → Phase 4 video

---

### Task 1: `draw_stick_figure` helper (Phase 1)

**Files:**
- Create: `pixel_battle/rl/__init__.py` (empty)
- Create: `pixel_battle/rl/stick_renderer.py`
- Create: `pixel_battle/tests/test_stick_renderer.py`

- [ ] **Step 1.1: Create the empty package marker**

Create `pixel_battle/rl/__init__.py` containing only a docstring:

```python
"""RL stick-fight: gymnasium env + PPO training + stick-figure renderer."""
```

- [ ] **Step 1.2: Write the failing tests**

Create `pixel_battle/tests/test_stick_renderer.py`:

```python
"""Stick renderer draws a stick figure from a Character's physics state."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.rl.stick_renderer import draw_stick_figure

WIDTH, HEIGHT = 480, 854
RED = (220, 60, 60)
BLUE = (60, 130, 220)


@pytest.fixture
def surf():
    pygame.init()
    pygame.display.set_mode((1, 1))
    return pygame.Surface((WIDTH, HEIGHT))


def _has_nonzero_pixel_in_box(surf, cx, cy, half):
    """Check at least one non-background pixel exists in a square around (cx, cy)."""
    arr = pygame.surfarray.array3d(surf)
    x0 = max(0, cx - half)
    x1 = min(WIDTH, cx + half)
    y0 = max(0, cy - half)
    y1 = min(HEIGHT, cy + half)
    region = arr[x0:x1, y0:y1]
    return bool((region.sum(axis=-1) > 0).any())


def test_draw_writes_pixels_near_character_position(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0  # near ground
    draw_stick_figure(surf, c, RED)
    # Stick figure spans roughly cy - 90 (head top) to cy (feet)
    assert _has_nonzero_pixel_in_box(surf, 200, 580, 50)


def test_draw_uses_provided_color(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0
    draw_stick_figure(surf, c, RED)
    arr = pygame.surfarray.array3d(surf)
    # Find a non-background pixel
    nonbg = (arr.sum(axis=-1) > 0)
    assert nonbg.any()
    # Sample one and check it's red-ish (R channel dominant)
    ys, xs = nonbg.nonzero()[1], nonbg.nonzero()[0]
    sample_x, sample_y = xs[0], ys[0]
    r, g, b = arr[sample_x, sample_y]
    assert r > g and r > b, f"expected red-dominant pixel, got rgb=({r},{g},{b})"


def test_draw_does_not_crash_in_attack_pose(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 600.0
    c.action_state = "attacking"
    c.attack_phase = "windup"
    c.attack_phase_t = 50
    draw_stick_figure(surf, c, RED)


def test_draw_does_not_crash_when_jumping(surf):
    c = Character.load("brick_phone")
    c.reset_physics(initial_x=200.0, facing=1)
    c.pos_y = 500.0
    c.on_ground = False
    c.vel_y = -5.0
    draw_stick_figure(surf, c, BLUE)


def test_left_and_right_chars_are_distinct_colors(surf):
    left = Character.load("brick_phone")
    left.reset_physics(initial_x=150.0, facing=1)
    left.pos_y = 600.0
    right = Character.load("glass_slab")
    right.reset_physics(initial_x=330.0, facing=-1)
    right.pos_y = 600.0
    draw_stick_figure(surf, left, RED)
    draw_stick_figure(surf, right, BLUE)
    arr = pygame.surfarray.array3d(surf)
    red_pixels = ((arr[:, :, 0] > 150) & (arr[:, :, 2] < 100)).sum()
    blue_pixels = ((arr[:, :, 2] > 150) & (arr[:, :, 0] < 100)).sum()
    assert red_pixels > 50, "left character should have visible red pixels"
    assert blue_pixels > 50, "right character should have visible blue pixels"
```

- [ ] **Step 1.3: Run tests to verify failure**

Run: `python -m pytest pixel_battle/tests/test_stick_renderer.py -v`
Expected: ImportError — `pixel_battle.rl.stick_renderer` does not exist.

- [ ] **Step 1.4: Implement `stick_renderer`**

Create `pixel_battle/rl/stick_renderer.py`:

```python
"""Procedural stick figure draw — replaces sprite blits in RL pipeline.

Pose driven by Character.action_state, attack_phase, vel_x, on_ground.
"""
from __future__ import annotations
from typing import Tuple

import pygame

from pixel_battle.engine.character import Character


HEAD_RADIUS = 12
TORSO_LENGTH = 40
ARM_LENGTH = 22
LEG_LENGTH = 28
LINE_WIDTH = 3


def _arm_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_arm_dx, dy), (right_arm_dx, dy)) for the two arms.

    Pose interpretation:
      - attack_phase=='windup' → both arms pulled back
      - attack_phase=='strike' → front arm thrust forward (in facing direction)
      - default               → arms hang slightly out from body
    """
    facing = char.facing  # +1 right, -1 left
    if char.attack_phase == "windup":
        # Both arms pulled to back side
        back_dx = -facing * ARM_LENGTH
        return (back_dx, 6), (back_dx, 6)
    if char.attack_phase == "strike":
        # Front arm thrust forward, back arm pulled back for balance
        front_dx = facing * ARM_LENGTH
        back_dx = -facing * (ARM_LENGTH // 2)
        return (front_dx, -4), (back_dx, 8)
    if char.action_state == "hit_stagger":
        # Arms flailing up
        return (-ARM_LENGTH // 2, -ARM_LENGTH // 2), (ARM_LENGTH // 2, -ARM_LENGTH // 2)
    # Default: hanging out slightly to each side
    return (-ARM_LENGTH // 2, 10), (ARM_LENGTH // 2, 10)


def _leg_offsets(char: Character) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Return ((left_leg_dx, dy), (right_leg_dx, dy))."""
    if not char.on_ground:
        # Tucked in mid-air
        return (-8, LEG_LENGTH // 2), (8, LEG_LENGTH // 2)
    if abs(char.vel_x) > 0.5:
        # Splayed for walking
        return (-LEG_LENGTH // 2, LEG_LENGTH), (LEG_LENGTH // 2, LEG_LENGTH)
    # Standing
    return (-6, LEG_LENGTH), (6, LEG_LENGTH)


def draw_stick_figure(surf: pygame.Surface, char: Character,
                       color: Tuple[int, int, int]) -> None:
    """Draw a stick figure for `char` onto `surf` in `color`.

    Body anchor is char.pos_x, char.pos_y (feet position).
    Stick extends upward: hips → torso → shoulders → head.
    """
    cx = int(char.pos_x)
    cy = int(char.pos_y)

    hip_y = cy - LEG_LENGTH                      # waist
    shoulder_y = hip_y - TORSO_LENGTH            # neck
    head_center_y = shoulder_y - HEAD_RADIUS - 2 # head sits just above shoulders

    # Head
    pygame.draw.circle(surf, color, (cx, head_center_y), HEAD_RADIUS, LINE_WIDTH)
    # Eyes — two filled dots that look in facing direction
    eye_offset = 4 if char.facing >= 0 else -4
    pygame.draw.circle(surf, color, (cx + eye_offset - 3, head_center_y - 2), 1)
    pygame.draw.circle(surf, color, (cx + eye_offset + 3, head_center_y - 2), 1)

    # Torso
    pygame.draw.line(surf, color, (cx, shoulder_y), (cx, hip_y), LINE_WIDTH)

    # Arms (from shoulder)
    (lax, lay), (rax, ray) = _arm_offsets(char)
    pygame.draw.line(surf, color, (cx, shoulder_y),
                      (cx + lax, shoulder_y + lay), LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, shoulder_y),
                      (cx + rax, shoulder_y + ray), LINE_WIDTH)

    # Legs (from hip)
    (llx, lly), (rlx, rly) = _leg_offsets(char)
    pygame.draw.line(surf, color, (cx, hip_y),
                      (cx + llx, hip_y + lly), LINE_WIDTH)
    pygame.draw.line(surf, color, (cx, hip_y),
                      (cx + rlx, hip_y + rly), LINE_WIDTH)
```

- [ ] **Step 1.5: Run tests to verify pass**

Run: `python -m pytest pixel_battle/tests/test_stick_renderer.py -v`
Expected: PASS (5 passed)

- [ ] **Step 1.6: Commit**

```bash
git add pixel_battle/rl/__init__.py pixel_battle/rl/stick_renderer.py pixel_battle/tests/test_stick_renderer.py
git commit -m "feat(pixel-battle): stick figure renderer (procedural pygame draw)"
```

---

### Task 2: `sticks_demo.py` episode (Phase 1 deliverable)

**Files:**
- Create: `pixel_battle/episodes/sticks_demo.py`

This episode reuses the existing `Battle` (with heuristic AI) but renders stick figures instead of sprites. Confirms the stick visuals are readable in motion.

- [ ] **Step 2.1: Create `sticks_demo.py`**

Create `pixel_battle/episodes/sticks_demo.py`:

```python
"""Phase 1 demo: existing engine + heuristic AI + stick figure visuals.

Output: pixel_battle/output/sticks_demo/final.mp4
"""
from __future__ import annotations
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.rl.stick_renderer import draw_stick_figure
from pixel_battle.video.recorder import FrameRecorder
from pixel_battle.video.audio_mixer import AudioMixer
from pixel_battle.video.compose import (
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
TICK_MS = 16
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "output" / "sticks_demo"


def draw_arena(surf, ground_y):
    surf.fill(BG)
    pygame.draw.line(surf, (60, 70, 110), (0, ground_y),
                      (WIDTH, ground_y), 2)


def main(max_seconds: int = 30):
    pygame.init()
    pygame.display.set_mode((1, 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    rng = BattleRNG(42)
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    battle = Battle(left=left, right=right, rng=rng)

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()

    mixer = AudioMixer(sample_rate=48000)

    surf = pygame.Surface((WIDTH, HEIGHT))
    total_frames = max_seconds * FPS
    event_video_ms: dict = {}

    for frame_no in range(total_frames):
        if battle.state == BattleState.KO:
            # Hold last frame for 2s of result, then stop
            if frame_no > total_frames - 120:
                break
        prev_n = len(battle.events)
        battle.tick_ms(TICK_MS)
        for ev in battle.events[prev_n:]:
            event_video_ms[id(ev)] = int(frame_no * FRAME_MS)

        draw_arena(surf, GROUND_Y)
        draw_stick_figure(surf, left, RED)
        draw_stick_figure(surf, right, BLUE)
        recorder.write_frame(surf)

    recorder.stop()

    # Build audio track using existing helpers — reuses synthwave BGM + SFX
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, int(total_frames * FRAME_MS), mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    for ev in battle.events:
        pos = event_video_ms.get(id(ev), int(ev.t_ms))
        name_map = {"hit": "hit", "crit": "crit", "ko": "ko",
                     "attack_windup": None, "ultimate_start": "ultimate"}
        # See ev.type.value for the string form
        type_val = ev.type.value
        sfx_name = name_map.get(type_val)
        if sfx_name is None and type_val == "attack_windup":
            kind = (ev.extra or {}).get("skill_type", "")
            sfx_name = f"cast_{kind}"
        if not sfx_name:
            continue
        samp = _load_sfx_samples_or_none(sfx_name, mixer.sr)
        if samp is None:
            continue
        if sfx_name in ("hit", "crit", "ko"):
            mixer.hit_bus.add(samp, pos)
        elif sfx_name.startswith("cast_"):
            mixer.cast_bus.add(samp, pos)
        else:
            mixer.ult_bus.add(samp, pos)

    mixer.export(int(total_frames * FRAME_MS), str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ Sticks demo: {final_mp4} ({max_seconds}s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2.2: Run the demo**

Run: `SDL_VIDEODRIVER=dummy python -m pixel_battle.episodes.sticks_demo`
Expected: prints `✅ Sticks demo: ... final.mp4 (30s)` without error.

- [ ] **Step 2.3: Inspect artifacts**

Run: `ls -la pixel_battle/output/sticks_demo/final.mp4`
Expected: file exists, ~1-3 MB.

- [ ] **Step 2.4: Commit**

```bash
git add pixel_battle/episodes/sticks_demo.py
git commit -m "feat(pixel-battle): sticks_demo episode — Phase 1 deliverable"
```

(Output mp4s should already be gitignored; if not the commit is still fine since we're only adding source.)

---

### Task 3: Install RL dependencies (Phase 2)

**Files:** none modified; dependency install only.

- [ ] **Step 3.1: Install**

Run: `pip install gymnasium stable-baselines3 torch`
Expected: install succeeds. `torch` is ~700MB; expect 2-3 minutes.

- [ ] **Step 3.2: Verify**

Run:
```bash
python -c "
import gymnasium, stable_baselines3, torch
print('gym', gymnasium.__version__)
print('sb3', stable_baselines3.__version__)
print('torch', torch.__version__)
print('cuda available:', torch.cuda.is_available())
"
```
Expected: prints versions. `gymnasium >= 0.29`, `stable_baselines3 >= 2.0`, `torch >= 2.0`. CUDA can be False — CPU is fine for our env.

- [ ] **Step 3.3: No commit needed for install alone**

(Skip commit — dependency install isn't in version control yet. If the project has a `requirements.txt`, append these three packages.)

Run: `[ -f requirements.txt ] && grep -E "^(gymnasium|stable-baselines3|torch)" requirements.txt || echo "no requirements.txt"`
If the file exists, add the three packages to it (preserve order), commit:

```bash
git add requirements.txt
git commit -m "chore(pixel-battle): add RL deps (gymnasium, sb3, torch)"
```

---

### Task 4: `Battle.tick_ms(skip_ai=True)` shim (Phase 2)

**Files:**
- Modify: `pixel_battle/engine/battle.py:94` — add `skip_ai` parameter
- Create: `pixel_battle/tests/test_battle_skip_ai.py`

- [ ] **Step 4.1: Write the failing tests**

Create `pixel_battle/tests/test_battle_skip_ai.py`:

```python
"""Battle.tick_ms(skip_ai=True) bypasses the heuristic AI + auto-ultimate."""
from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def _new_battle(seed: int = 42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    return Battle(left=a, right=b, rng=BattleRNG(seed))


def test_tick_ms_default_runs_ai():
    """Without skip_ai, characters move toward each other under heuristic AI."""
    bat = _new_battle()
    bat.tick_ms(2500)  # advance past intro
    init_left_x = bat.left.pos_x
    init_right_x = bat.right.pos_x
    for _ in range(60):
        bat.tick_ms(16)
    # AI should have moved at least one of them
    moved = (bat.left.pos_x != init_left_x) or (bat.right.pos_x != init_right_x)
    assert moved, "expected heuristic AI to move characters"


def test_tick_ms_skip_ai_no_movement():
    """With skip_ai=True, characters do not move under AI control."""
    bat = _new_battle()
    bat.tick_ms(2500)
    bat.left.vel_x = 0.0
    bat.right.vel_x = 0.0
    init_left_x = bat.left.pos_x
    init_right_x = bat.right.pos_x
    for _ in range(60):
        bat.tick_ms(16, skip_ai=True)
    # Velocities should still be zero (friction would clear any residual);
    # positions unchanged (no AI input, no manual vel)
    assert bat.left.pos_x == init_left_x
    assert bat.right.pos_x == init_right_x


def test_tick_ms_skip_ai_still_resolves_attacks():
    """Physics + attack-phase + collision still run with skip_ai."""
    bat = _new_battle()
    bat.tick_ms(2500)
    # Manually set attack state and step
    bat.left.pos_x = 220
    bat.right.pos_x = 260  # in melee range
    bat.left.action_state = "attacking"
    bat.left.attack_phase = "windup"
    bat.left.attack_phase_t = 0
    bat.left.attack_used_kind = bat.left.skills[0]  # basic skill
    bat.left.facing = 1
    initial_right_hp = bat.right.hp
    for _ in range(15):  # enough frames for windup → strike → hit
        bat.tick_ms(16, skip_ai=True)
    # Either the attack landed (hp dropped) or missed (logged); just confirm
    # the phase machine progressed (not stuck at windup forever).
    assert bat.left.attack_phase != "windup", "phase machine should have advanced"


def test_tick_ms_skip_ai_skips_auto_ultimate():
    """When MP is full, default tick triggers ultimate; skip_ai prevents that."""
    bat = _new_battle()
    bat.tick_ms(2500)
    bat.left.mp = bat.left.mp_max  # ultimate ready
    bat.left.action_state = "idle"
    bat.left.attack_phase = "none"
    bat.tick_ms(16, skip_ai=True)
    # Should NOT have entered ULTIMATE_PLAYING state via auto-trigger
    assert bat.state != BattleState.ULTIMATE_PLAYING
```

- [ ] **Step 4.2: Run tests to verify failure**

Run: `python -m pytest pixel_battle/tests/test_battle_skip_ai.py -v`
Expected: 3 of the 4 tests FAIL with `TypeError: tick_ms() got an unexpected keyword argument 'skip_ai'`. (`test_tick_ms_default_runs_ai` may pass since it doesn't use skip_ai.)

- [ ] **Step 4.3: Add `skip_ai` parameter to `Battle.tick_ms`**

In `pixel_battle/engine/battle.py`, find the current signature at line 94:

```python
    def tick_ms(self, dt_ms: int) -> None:
        self.elapsed_ms += dt_ms
```

Replace the signature with:

```python
    def tick_ms(self, dt_ms: int, skip_ai: bool = False) -> None:
        self.elapsed_ms += dt_ms
```

Then find the block at lines 144-154 (the auto-ultimate + AI calls):

```python
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
```

Replace with:

```python
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
```

- [ ] **Step 4.4: Run tests to verify pass**

Run: `python -m pytest pixel_battle/tests/test_battle_skip_ai.py -v`
Expected: 4 PASS.

- [ ] **Step 4.5: Confirm full suite still passes**

Run: `python -m pytest pixel_battle/tests/ --ignore=pixel_battle/tests/test_renderer.py --deselect pixel_battle/tests/test_battle_ai_priority.py::test_ai_retreats_when_mp_high_and_close -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 4.6: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_battle_skip_ai.py
git commit -m "feat(pixel-battle): Battle.tick_ms gains skip_ai flag for RL control"
```

---

### Task 5: `Battle._start_attack_with_kind` shim (Phase 2)

**Files:**
- Modify: `pixel_battle/engine/battle.py` — append new method
- Create: `pixel_battle/tests/test_battle_start_attack_with_kind.py`

- [ ] **Step 5.1: Write the failing tests**

Create `pixel_battle/tests/test_battle_start_attack_with_kind.py`:

```python
"""_start_attack_with_kind lets the RL policy pick the skill category."""
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.skill import SkillType


def _battle(seed: int = 42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)  # past intro
    return bat


def test_basic_kind_picks_basic_skill():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    bat._start_attack_with_kind(a, b, "basic")
    assert a.action_state == "attacking"
    assert a.attack_used_kind.skill_type is SkillType.BASIC


def test_cooldown_kind_picks_cd_skill_when_available():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    a.skill_cd_ready_at = {}  # all CD skills available
    bat._start_attack_with_kind(a, b, "cooldown")
    assert a.action_state == "attacking"
    assert a.attack_used_kind.skill_type is SkillType.COOLDOWN


def test_cooldown_kind_falls_through_when_all_on_cooldown():
    """If no CD skill is available, the action is a no-op (no attack started)."""
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    # Mark all CD skills on cooldown
    for skill in a.skills_of_type(SkillType.COOLDOWN):
        a.skill_cd_ready_at[skill.id] = 999_999
    bat._start_attack_with_kind(a, b, "cooldown")
    # No attack should have started
    assert a.action_state != "attacking" or a.attack_used_kind is None or \
           a.attack_used_kind.skill_type is not SkillType.COOLDOWN


def test_unknown_kind_is_noop():
    bat = _battle()
    a = bat.left; b = bat.right
    a.action_state = "idle"
    a.attack_phase = "none"
    a.last_attack_ms = -10000
    bat._start_attack_with_kind(a, b, "bogus")
    assert a.action_state != "attacking"
```

- [ ] **Step 5.2: Run tests to verify failure**

Run: `python -m pytest pixel_battle/tests/test_battle_start_attack_with_kind.py -v`
Expected: 4 FAIL with `AttributeError: ... has no attribute '_start_attack_with_kind'`.

- [ ] **Step 5.3: Implement the method**

In `pixel_battle/engine/battle.py`, after the existing `_start_attack` method (around line 458, end of the method body), append a new method on the same class:

```python
    def _start_attack_with_kind(self, char: Character, opp: Character,
                                  kind: str) -> None:
        """RL-friendly attack initiator: skip the random selection in
        _choose_attack_skill and pick by category instead.

        kind: "basic" | "cooldown"
          - basic: always picks the first BASIC skill (always available)
          - cooldown: picks first off-cooldown COOLDOWN skill; no-op if none
        Unknown kinds are a no-op.
        """
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return
        if self.elapsed_ms < char.last_attack_ms + char.attack_interval_ms:
            return  # respect attack interval gate

        from pixel_battle.engine.skill import SkillType
        if kind == "basic":
            skill = char.skills_of_type(SkillType.BASIC)[0]
        elif kind == "cooldown":
            cd_skills = char.skills_of_type(SkillType.COOLDOWN)
            available = [s for s in cd_skills
                          if char.skill_off_cooldown(s, self.elapsed_ms)]
            if not available:
                return  # no CD skill ready — no-op
            skill = available[0]
        else:
            return

        # Mirror _start_attack body but with explicit skill choice
        char.attack_used_kind = skill
        char.attack_phase = "windup"
        char.attack_phase_t = 0
        char.action_state = "attacking"
        char.vel_x = 0.0

        from pixel_battle.engine.battle import EventType  # local import; safe
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
```

- [ ] **Step 5.4: Run tests to verify pass**

Run: `python -m pytest pixel_battle/tests/test_battle_start_attack_with_kind.py -v`
Expected: 4 PASS.

- [ ] **Step 5.5: Confirm full suite still green**

Run: `python -m pytest pixel_battle/tests/ --ignore=pixel_battle/tests/test_renderer.py --deselect pixel_battle/tests/test_battle_ai_priority.py::test_ai_retreats_when_mp_high_and_close -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 5.6: Commit**

```bash
git add pixel_battle/engine/battle.py pixel_battle/tests/test_battle_start_attack_with_kind.py
git commit -m "feat(pixel-battle): _start_attack_with_kind — explicit skill category"
```

---

### Task 6: `PixelBattleEnv` Gymnasium env (Phase 2)

**Files:**
- Create: `pixel_battle/rl/env.py`
- Create: `pixel_battle/tests/test_rl_env.py`

- [ ] **Step 6.1: Write the failing tests**

Create `pixel_battle/tests/test_rl_env.py`:

```python
"""PixelBattleEnv exposes a paired Gymnasium env for self-play."""
import numpy as np
import pytest

from pixel_battle.rl.env import PixelBattleEnv


def test_env_reset_returns_paired_obs_with_correct_shape():
    env = PixelBattleEnv(seed=42)
    (obs_left, obs_right), info = env.reset()
    assert obs_left.shape == (17,)
    assert obs_right.shape == (17,)
    assert obs_left.dtype == np.float32
    assert obs_right.dtype == np.float32
    assert isinstance(info, dict)


def test_env_step_advances_battle_time():
    env = PixelBattleEnv(seed=42)
    env.reset()
    # Step past intro
    for _ in range(200):
        env.step((0, 0))
    assert env.battle.elapsed_ms > 2000


def test_env_step_returns_paired_reward_tuple():
    env = PixelBattleEnv(seed=42)
    env.reset()
    obs, rewards, terminated, truncated, info = env.step((0, 0))
    assert len(rewards) == 2
    assert isinstance(rewards[0], float)
    assert isinstance(rewards[1], float)


def test_env_movement_actions_apply_velocity():
    env = PixelBattleEnv(seed=42)
    env.reset()
    # Step past intro so we're in FIGHTING
    for _ in range(200):
        env.step((0, 0))
    # Action 2 = right, 1 = left
    env.step((2, 1))
    assert env.left.vel_x > 0, f"left should move right, vel_x={env.left.vel_x}"
    assert env.right.vel_x < 0, f"right should move left, vel_x={env.right.vel_x}"


def test_env_basic_attack_action_triggers_attacking():
    env = PixelBattleEnv(seed=42)
    env.reset()
    for _ in range(200):
        env.step((0, 0))
    # Place in melee range first
    env.left.pos_x = 200
    env.right.pos_x = 260
    env.left.last_attack_ms = -10000
    env.step((4, 0))  # basic attack
    assert env.left.action_state == "attacking"


def test_env_terminates_on_ko():
    env = PixelBattleEnv(seed=42)
    env.reset()
    for _ in range(200):
        env.step((0, 0))
    # KO the right player manually
    env.right.hp = 0
    obs, rewards, terminated, truncated, info = env.step((0, 0))
    assert terminated is True
    # Left dealt the KO → bonus reward
    assert rewards[0] > 10


def test_env_action_space_is_discrete_seven():
    env = PixelBattleEnv(seed=42)
    assert env.action_space.n == 7


def test_env_observation_space_is_17_dim_box():
    env = PixelBattleEnv(seed=42)
    assert env.observation_space.shape == (17,)
```

- [ ] **Step 6.2: Run tests to verify failure**

Run: `python -m pytest pixel_battle/tests/test_rl_env.py -v`
Expected: ImportError — `pixel_battle.rl.env` does not exist.

- [ ] **Step 6.3: Implement the env**

Create `pixel_battle/rl/env.py`:

```python
"""Gymnasium env wrapping pixel_battle.engine.battle.Battle for PPO self-play.

Paired API: reset/step return (obs_left, obs_right) and reward tuples. We adapt
this to single-agent PPO via a wrapper in train.py.
"""
from __future__ import annotations
from typing import Tuple

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


TICK_MS = 16
EPISODE_TIMEOUT_MS = 60_000
INTRO_END_MS = 2500


class PixelBattleEnv(gym.Env):
    """Self-play env. step((left_act, right_act)) -> (obs_pair, reward_pair, ...)

    Observation per agent (17 dims, normalized to ~[-1, 1]):
       [own_x, own_y, own_vx, own_vy, own_hp, own_mp,
        opp_x, opp_y, opp_vx, opp_vy, opp_hp, opp_mp,
        dx, dy, on_ground, attack_phase_t, time_remaining]

    Action (Discrete 7):
       0=idle, 1=left, 2=right, 3=jump, 4=basic, 5=cd, 6=ultimate
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42):
        super().__init__()
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(17,), dtype=np.float32,
        )
        self.action_space = spaces.Discrete(7)
        self._init_seed = seed
        self.reset(seed=seed)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if seed is None:
            seed = self._init_seed
        self._rng = BattleRNG(seed)
        self.left = Character.load("brick_phone")
        self.right = Character.load("glass_slab")
        self.battle = Battle(left=self.left, right=self.right, rng=self._rng)
        # Tick through intro so both characters are in FIGHTING state
        while self.battle.state == BattleState.STARTING:
            self.battle.tick_ms(TICK_MS, skip_ai=True)
            if self.battle.elapsed_ms > INTRO_END_MS:
                break
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp
        return self._obs_pair(), {}

    def step(self, actions: Tuple[int, int]):
        left_action, right_action = actions
        self._apply_action(self.left, self.right, int(left_action))
        self._apply_action(self.right, self.left, int(right_action))
        self.battle.tick_ms(TICK_MS, skip_ai=True)

        dmg_to_right = max(0, self._prev_right_hp - self.right.hp)
        dmg_to_left = max(0, self._prev_left_hp - self.left.hp)
        self._prev_left_hp = self.left.hp
        self._prev_right_hp = self.right.hp

        # Per-frame engagement reward (small)
        dist = abs(self.left.pos_x - self.right.pos_x)
        engage = 0.05 if dist < 200 else 0.0

        reward_left = dmg_to_right * 1.0 - dmg_to_left * 1.0 - 0.01 + engage
        reward_right = dmg_to_left * 1.0 - dmg_to_right * 1.0 - 0.01 + engage

        terminated = self.battle.state in (BattleState.KO,
                                              BattleState.ULTIMATE_PLAYING) \
                      and self.battle.state == BattleState.KO
        # ULTIMATE_PLAYING is transient; KO is end. Use clean check:
        terminated = self.battle.state == BattleState.KO
        truncated = (self.battle.elapsed_ms - INTRO_END_MS) >= EPISODE_TIMEOUT_MS

        if terminated:
            if self.right.is_ko() and not self.left.is_ko():
                reward_left += 50.0
                reward_right -= 50.0
            elif self.left.is_ko() and not self.right.is_ko():
                reward_left -= 50.0
                reward_right += 50.0

        return (self._obs_pair(),
                (float(reward_left), float(reward_right)),
                terminated, truncated, {})

    def _obs_for(self, me: Character, opp: Character) -> np.ndarray:
        return np.array([
            me.pos_x / 480 - 1.0, me.pos_y / 854 - 1.0,
            float(np.clip(me.vel_x / 10, -1, 1)),
            float(np.clip(me.vel_y / 20, -1, 1)),
            me.hp / 100.0, me.mp / 100.0,
            opp.pos_x / 480 - 1.0, opp.pos_y / 854 - 1.0,
            float(np.clip(opp.vel_x / 10, -1, 1)),
            float(np.clip(opp.vel_y / 20, -1, 1)),
            opp.hp / 100.0, opp.mp / 100.0,
            float(np.clip((opp.pos_x - me.pos_x) / 480, -1, 1)),
            float(np.clip((opp.pos_y - me.pos_y) / 854, -1, 1)),
            float(me.on_ground),
            float(np.clip(me.attack_phase_t / 200, 0, 1)),
            float(np.clip(
                (EPISODE_TIMEOUT_MS - (self.battle.elapsed_ms - INTRO_END_MS))
                / EPISODE_TIMEOUT_MS,
                0, 1,
            )),
        ], dtype=np.float32)

    def _obs_pair(self):
        return (self._obs_for(self.left, self.right),
                self._obs_for(self.right, self.left))

    def _apply_action(self, me: Character, opp: Character, action: int):
        if me.action_state in ("attacking", "hit_stagger", "ko"):
            return
        if action == 1:                          # left
            me.vel_x = -3.0
            me.facing = -1 if opp.pos_x > me.pos_x else me.facing
        elif action == 2:                        # right
            me.vel_x = 3.0
            me.facing = 1 if opp.pos_x > me.pos_x else me.facing
        elif action == 3 and me.on_ground:       # jump
            me.vel_y = -8.0
            me.on_ground = False
        elif action == 4:                        # basic attack
            self.battle._start_attack_with_kind(me, opp, "basic")
        elif action == 5:                        # cd skill
            self.battle._start_attack_with_kind(me, opp, "cooldown")
        elif action == 6 and me.ultimate_ready():
            self.battle._trigger_ultimate(me, opp)
```

- [ ] **Step 6.4: Run tests to verify pass**

Run: `python -m pytest pixel_battle/tests/test_rl_env.py -v`
Expected: PASS (8 passed).

- [ ] **Step 6.5: Confirm full suite still green**

Run: `python -m pytest pixel_battle/tests/ --ignore=pixel_battle/tests/test_renderer.py --deselect pixel_battle/tests/test_battle_ai_priority.py::test_ai_retreats_when_mp_high_and_close -q 2>&1 | tail -5`
Expected: all green.

- [ ] **Step 6.6: Commit**

```bash
git add pixel_battle/rl/env.py pixel_battle/tests/test_rl_env.py
git commit -m "feat(pixel-battle): PixelBattleEnv Gymnasium env for PPO self-play"
```

---

### Task 7: Phase 2 deliverable — random agent video

**Files:**
- Create: `pixel_battle/episodes/sticks_random.py`

Render a video of two random-action agents fighting via the new env + stick renderer. Verifies the gym pipeline + stick renderer integrate.

- [ ] **Step 7.1: Create the episode**

Create `pixel_battle/episodes/sticks_random.py`:

```python
"""Phase 2 deliverable: PixelBattleEnv + random agents + stick visuals."""
from __future__ import annotations
import os
import random
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.rl.stick_renderer import draw_stick_figure
from pixel_battle.video.recorder import FrameRecorder
from pixel_battle.video.audio_mixer import AudioMixer
from pixel_battle.video.compose import (
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

OUT_DIR = Path(__file__).resolve().parents[1] / "output" / "sticks_random"


def main(max_seconds: int = 30, seed: int = 7):
    pygame.init()
    pygame.display.set_mode((1, 1))
    random.seed(seed)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    env = PixelBattleEnv(seed=seed)
    env.reset()

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()

    surf = pygame.Surface((WIDTH, HEIGHT))
    mixer = AudioMixer(sample_rate=48000)
    total_frames = max_seconds * FPS
    total_duration_ms = int(total_frames * FRAME_MS)

    for frame in range(total_frames):
        action = (random.randint(0, 6), random.randint(0, 6))
        env.step(action)

        surf.fill(BG)
        pygame.draw.line(surf, (60, 70, 110), (0, GROUND_Y),
                          (WIDTH, GROUND_Y), 2)
        draw_stick_figure(surf, env.left, RED)
        draw_stick_figure(surf, env.right, BLUE)
        recorder.write_frame(surf)

        if env.battle.state.name == "KO":
            # Hold a few frames after KO then stop
            for _ in range(60):
                recorder.write_frame(surf)
            break

    recorder.stop()

    # Minimal audio: BGM only (no SFX wiring for random agent)
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ Sticks random: {final_mp4} ({max_seconds}s)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7.2: Run the random episode**

Run: `SDL_VIDEODRIVER=dummy python -m pixel_battle.episodes.sticks_random`
Expected: prints `✅ Sticks random: ... final.mp4 (30s)` without error.

- [ ] **Step 7.3: Commit**

```bash
git add pixel_battle/episodes/sticks_random.py
git commit -m "feat(pixel-battle): sticks_random episode — Phase 2 deliverable"
```

---

### Task 8: Single-perspective self-play wrapper (Phase 3)

**Files:**
- Append to: `pixel_battle/rl/env.py`

PPO needs a single-agent step API. Wrap `PixelBattleEnv` so left is the policy and right is controlled by a frozen-snapshot policy. For first cut, the opponent uses the SAME model (live shared policy), giving symmetric self-play.

- [ ] **Step 8.1: Add `SinglePerspectiveEnv` wrapper to `pixel_battle/rl/env.py`**

Append to the bottom of `pixel_battle/rl/env.py`:

```python
class SinglePerspectiveEnv(gym.Env):
    """Wrap PixelBattleEnv so step(left_action) controls only 'left'.

    Right is controlled by `opponent_policy` (a callable taking obs -> int).
    Use a fresh random policy for the first training rollouts, then swap to
    the current PPO model itself for symmetric self-play.
    """

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 42, opponent_policy=None):
        super().__init__()
        self._inner = PixelBattleEnv(seed=seed)
        self.observation_space = self._inner.observation_space
        self.action_space = self._inner.action_space
        self._opponent_policy = opponent_policy or (lambda obs: 0)

    def set_opponent_policy(self, policy):
        """policy(obs: np.ndarray) -> int (discrete action)."""
        self._opponent_policy = policy

    def reset(self, seed=None, options=None):
        (obs_left, obs_right), info = self._inner.reset(seed=seed)
        self._last_right_obs = obs_right
        return obs_left, info

    def step(self, left_action):
        right_action = int(self._opponent_policy(self._last_right_obs))
        (obs_left, obs_right), rewards, terminated, truncated, info = \
            self._inner.step((int(left_action), right_action))
        self._last_right_obs = obs_right
        return obs_left, float(rewards[0]), terminated, truncated, info
```

- [ ] **Step 8.2: Add quick smoke test**

Append to `pixel_battle/tests/test_rl_env.py`:

```python
from pixel_battle.rl.env import SinglePerspectiveEnv


def test_single_perspective_env_steps_with_random_opponent():
    import random
    env = SinglePerspectiveEnv(seed=42,
                                opponent_policy=lambda obs: random.randint(0, 6))
    obs, info = env.reset()
    assert obs.shape == (17,)
    obs, r, term, trunc, info = env.step(0)
    assert isinstance(r, float)
    assert obs.shape == (17,)
```

- [ ] **Step 8.3: Run smoke test**

Run: `python -m pytest pixel_battle/tests/test_rl_env.py::test_single_perspective_env_steps_with_random_opponent -v`
Expected: PASS.

- [ ] **Step 8.4: Commit**

```bash
git add pixel_battle/rl/env.py pixel_battle/tests/test_rl_env.py
git commit -m "feat(pixel-battle): SinglePerspectiveEnv self-play wrapper"
```

---

### Task 9: PPO training script (Phase 3)

**Files:**
- Create: `pixel_battle/rl/train.py`

- [ ] **Step 9.1: Add `.gitignore` rule for checkpoints**

Run: `grep -E "^data/rl_checkpoints" .gitignore 2>/dev/null || echo "data/rl_checkpoints/" >> .gitignore`
Then commit if changed:
```bash
git diff --cached --quiet .gitignore || true
git add .gitignore
git diff --staged --quiet || git commit -m "chore: gitignore data/rl_checkpoints/"
```

- [ ] **Step 9.2: Create `pixel_battle/rl/train.py`**

Create:

```python
"""PPO self-play training for PixelBattleEnv.

Defaults to 500K total timesteps with a checkpoint every 100K. Starts
opponent_policy as random; after the first 50K steps, swaps opponent to
the live model itself (in-place self-play).

Usage:
    python -m pixel_battle.rl.train --total_timesteps 500000
"""
from __future__ import annotations
import argparse
import random
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback

from pixel_battle.rl.env import SinglePerspectiveEnv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT_DIR = ROOT / "data" / "rl_checkpoints"


class SelfPlaySwapCallback(BaseCallback):
    """After `swap_after` steps, replace random opponent with live model."""

    def __init__(self, env: SinglePerspectiveEnv,
                  swap_after: int = 50_000, verbose: int = 0):
        super().__init__(verbose)
        self.env = env
        self.swap_after = swap_after
        self.swapped = False

    def _on_step(self) -> bool:
        if not self.swapped and self.num_timesteps >= self.swap_after:
            def policy(obs):
                act, _ = self.model.predict(obs, deterministic=False)
                return int(act)
            self.env.set_opponent_policy(policy)
            self.swapped = True
            if self.verbose:
                print(f"[SelfPlaySwap] swapped at step {self.num_timesteps}")
        return True


def main(total_timesteps: int = 500_000,
          ckpt_dir: Path = DEFAULT_CKPT_DIR,
          seed: int = 42):
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # Initial opponent: random
    raw_env = SinglePerspectiveEnv(
        seed=seed,
        opponent_policy=lambda obs: random.randint(0, 6),
    )

    model = PPO("MlpPolicy", raw_env, verbose=1,
                 n_steps=2048, batch_size=256,
                 gae_lambda=0.95, gamma=0.99,
                 learning_rate=3e-4, clip_range=0.2, ent_coef=0.01,
                 seed=seed)

    ckpt_cb = CheckpointCallback(save_freq=100_000,
                                  save_path=str(ckpt_dir),
                                  name_prefix="ppo")
    swap_cb = SelfPlaySwapCallback(raw_env, swap_after=50_000, verbose=1)

    model.learn(total_timesteps=total_timesteps,
                 callback=[ckpt_cb, swap_cb])
    model.save(ckpt_dir / "ppo_final.zip")
    print(f"✅ Training done. Final model: {ckpt_dir / 'ppo_final.zip'}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--total_timesteps", type=int, default=500_000)
    p.add_argument("--ckpt_dir", type=Path, default=DEFAULT_CKPT_DIR)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    main(total_timesteps=args.total_timesteps,
          ckpt_dir=args.ckpt_dir, seed=args.seed)
```

- [ ] **Step 9.3: Sanity-check the training loop with a tiny run (1000 steps)**

Run: `python -m pixel_battle.rl.train --total_timesteps 1000`
Expected: prints PPO log lines like `| time/fps | ... |` and finishes with `✅ Training done.`. Takes ~30s on CPU. NO `ppo_*.zip` may be saved if `save_freq` was never reached — that's expected for 1000-step run; `ppo_final.zip` should still appear.

- [ ] **Step 9.4: Commit the training script**

```bash
git add pixel_battle/rl/train.py
git commit -m "feat(pixel-battle): PPO self-play training driver"
```

---

### Task 10: Run 500K-step training (Phase 3)

**Files:** none modified; just runs training.

- [ ] **Step 10.1: Kick off the training run**

Run: `python -m pixel_battle.rl.train --total_timesteps 500000 2>&1 | tee data/rl_checkpoints/train.log`
Expected: runs for ~30-90 min on CPU. Watches PPO log lines. Final message: `✅ Training done. Final model: .../ppo_final.zip`.

- [ ] **Step 10.2: Inspect outputs**

Run: `ls -la data/rl_checkpoints/`
Expected: `ppo_final.zip` + 4-5 `ppo_*_steps.zip` checkpoints + `train.log`.

- [ ] **Step 10.3: Sanity-check final model loads + predicts**

Run:
```bash
python -c "
from stable_baselines3 import PPO
from pixel_battle.rl.env import SinglePerspectiveEnv
model = PPO.load('data/rl_checkpoints/ppo_final.zip')
env = SinglePerspectiveEnv(seed=99)
obs, _ = env.reset()
for _ in range(50):
    action, _ = model.predict(obs)
    obs, r, term, trunc, _ = env.step(int(action))
    if term or trunc: break
print('OK, prediction loop ran')
"
```
Expected: prints `OK, prediction loop ran` without crashes.

- [ ] **Step 10.4: No commit** (checkpoint files are gitignored; train.log can be committed if it helps document the run, but optional).

---

### Task 11: `play.py` — render trained fight (Phase 4)

**Files:**
- Create: `pixel_battle/rl/play.py`

- [ ] **Step 11.1: Create `pixel_battle/rl/play.py`**

```python
"""Load a trained PPO checkpoint, render a self-play fight as mp4."""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.stick_renderer import draw_stick_figure  # noqa: E402
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.video.audio_mixer import AudioMixer  # noqa: E402
from pixel_battle.video.compose import (  # noqa: E402
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
RED = (220, 60, 60)
BLUE = (60, 130, 220)
BG = (18, 22, 40)
GROUND_Y = 720

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = ROOT / "data" / "rl_checkpoints" / "ppo_final.zip"
OUT_DIR = ROOT / "pixel_battle" / "output" / "rl_play"


def _route_audio_for_events(events, event_video_ms, mixer):
    """Use the existing audio routing convention from compose.py."""
    for ev in events:
        pos = event_video_ms.get(id(ev))
        if pos is None:
            continue
        type_val = ev.type.value
        sfx_name = None
        if type_val == "hit":
            sfx_name = "crit" if (ev.extra or {}).get("crit") else "hit"
        elif type_val == "crit":
            sfx_name = "crit"
        elif type_val == "ko":
            sfx_name = "ko"
        elif type_val == "ultimate_start":
            sfx_name = "ultimate"
        elif type_val == "attack_windup":
            kind = (ev.extra or {}).get("skill_type", "")
            sfx_name = f"cast_{kind}"
        if not sfx_name:
            continue
        samp = _load_sfx_samples_or_none(sfx_name, mixer.sr)
        if samp is None:
            continue
        if sfx_name in ("hit", "crit", "ko"):
            mixer.hit_bus.add(samp, pos)
        elif sfx_name.startswith("cast_"):
            mixer.cast_bus.add(samp, pos)
        else:
            mixer.ult_bus.add(samp, pos)


def main(checkpoint: Path = DEFAULT_CKPT, max_seconds: float = 60.0,
          seed: int = 1234):
    pygame.init()
    pygame.display.set_mode((1, 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_video = OUT_DIR / "raw.mp4"
    audio_out = OUT_DIR / "audio.wav"
    final_mp4 = OUT_DIR / "final.mp4"

    model = PPO.load(str(checkpoint))
    env = PixelBattleEnv(seed=seed)
    (obs_left, obs_right), _ = env.reset()

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()
    mixer = AudioMixer(sample_rate=48000)

    surf = pygame.Surface((WIDTH, HEIGHT))
    total_frames = int(max_seconds * FPS)
    event_video_ms: dict = {}

    for frame in range(total_frames):
        left_act, _ = model.predict(obs_left, deterministic=False)
        right_act, _ = model.predict(obs_right, deterministic=False)

        prev_ev_n = len(env.battle.events)
        (obs_left, obs_right), _, terminated, truncated, _ = env.step(
            (int(left_act), int(right_act))
        )
        for ev in env.battle.events[prev_ev_n:]:
            event_video_ms[id(ev)] = int(frame * FRAME_MS)

        surf.fill(BG)
        pygame.draw.line(surf, (60, 70, 110), (0, GROUND_Y),
                          (WIDTH, GROUND_Y), 2)
        draw_stick_figure(surf, env.left, RED)
        draw_stick_figure(surf, env.right, BLUE)
        recorder.write_frame(surf)

        if terminated:
            for _ in range(120):  # 2s hold
                recorder.write_frame(surf)
            break

    recorder.stop()
    actual_frames = (frame + 1 + 120) if terminated else total_frames
    total_duration_ms = int(actual_frames * FRAME_MS)

    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    _route_audio_for_events(env.battle.events, event_video_ms, mixer)

    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))
    print(f"✅ RL play: {final_mp4} ({total_duration_ms / 1000:.1f}s)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--max_seconds", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=1234)
    args = p.parse_args()
    main(checkpoint=args.checkpoint,
          max_seconds=args.max_seconds, seed=args.seed)
```

- [ ] **Step 11.2: Run the playback**

Run: `SDL_VIDEODRIVER=dummy python -m pixel_battle.rl.play`
Expected: prints `✅ RL play: .../final.mp4 ...`. Takes ~30-60s.

- [ ] **Step 11.3: Verify output**

Run: `ls -la pixel_battle/output/rl_play/final.mp4`
Expected: file exists, ~1-5 MB.

- [ ] **Step 11.4: Commit**

```bash
git add pixel_battle/rl/play.py
git commit -m "feat(pixel-battle): rl.play — render trained PPO self-play match"
```

---

## Out of scope (do not implement)

- Asymmetric policies (separate networks per side)
- Curriculum learning
- GPU training
- Tensorboard logging beyond stable-baselines3 default
- Hyperparameter sweep
- Reverting / removing sprite pipeline
- Removing existing `ep01_brick_vs_glass.py` episode

## Tuning knobs (already in spec; restated for the implementer)

- Reward: damage 1:1, KO ±50, step -0.01, engagement +0.05 if dist < 200
- Action space: 7 discrete
- PPO: lr=3e-4, n_steps=2048, batch_size=256, gae=0.95, gamma=0.99, ent_coef=0.01, clip=0.2
- Episode: 60s max (after intro)
- Training: 500K steps default, checkpoint every 100K
- Stick dims: head r=12, torso 40px, arm 22px, leg 28px, line width 3
