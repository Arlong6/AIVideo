# Pixel Battle P2 Polish Iteration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the P1 video's three watch-killers: AI lock-up after 36s, invisible CD-skill effects, and stiff sprite motion.

**Architecture:** Heuristic patches to `_ai_choose_action` (retreat timer + lower HP threshold + wall-stuck guard); two new procedural-render modules (`engine/projectile.py`, `engine/banner.py`) mirroring the `engine/particles.py` pattern; surgical edits to `renderer.py` / `animator.py` / `battle.py` for walk bob, attack timing, and punch recoil.

**Tech Stack:** Python 3, pygame (headless via `SDL_VIDEODRIVER=dummy`), pytest. All rendering stays on the 480×854 vertical canvas.

**Spec:** `docs/superpowers/specs/2026-05-18-pixel-battle-p2-design.md`

---

## File Structure

**Create:**
- `pixel_battle/engine/projectile.py` — `Projectile` dataclass + `ProjectileSystem` (spawn/update/render/on_land callback)
- `pixel_battle/engine/banner.py` — `Banner` dataclass + `BannerSystem` (spawn/update_and_render with 3-phase x lerp + alpha fade)
- `pixel_battle/tests/test_projectile.py`
- `pixel_battle/tests/test_banner.py`
- `pixel_battle/tests/test_ai_retreat_lock.py`
- `pixel_battle/tests/test_battle_no_lock.py`

**Modify:**
- `pixel_battle/engine/character.py` — add `retreat_until_ms: int = 0`
- `pixel_battle/engine/battle.py` — retreat timer + HP threshold 30→15 + wall-stuck guard + attack recoil
- `pixel_battle/engine/animator.py` — `CLIP_DEFINITIONS[ATTACK]` rebalance 6/6/6 → 8/4/10
- `pixel_battle/engine/renderer.py` — instantiate `projectiles` + `banners`, render them in chain, walk bob in `_draw_sprite_char`
- `pixel_battle/episodes/ep01_brick_vs_glass.py` — spawn projectiles for CD-skill HITs (with deferred-particle callback), spawn banners for CD/special/ultimate HITs, scale CD particles

---

## Task 1: Retreat lock-up fix (HP threshold, retreat timer, wall-stuck guard)

**Files:**
- Modify: `pixel_battle/engine/character.py`
- Modify: `pixel_battle/engine/battle.py`
- Create: `pixel_battle/tests/test_ai_retreat_lock.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_ai_retreat_lock.py`:

```python
"""P2 fix: AI retreat must not lock both characters against walls."""
from pixel_battle.engine.battle import Battle, BattleState
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import ARENA_LEFT, ARENA_RIGHT, MELEE_RANGE


def _battle_post_intro(seed=1):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    bat.tick_ms(2500)  # past intro
    return bat, a, b


def test_retreat_timer_expires_after_800ms():
    """Once retreat_until_ms is set, after 800ms it must be cleared so AI can re-evaluate."""
    bat, a, b = _battle_post_intro(seed=1)
    # Force defensive retreat by low HP + high opp MP
    a.hp = 10
    b.mp = b.mp_max  # 100
    # Close range so retreat triggers
    a.pos_x = 240
    b.pos_x = 280
    bat._ai_choose_action(a, b, 16)
    assert a.retreat_until_ms > 0
    set_at = a.retreat_until_ms
    # Advance battle clock past the timer
    bat.elapsed_ms = set_at + 1
    a.action_state = "idle"  # let AI re-decide
    bat._ai_choose_action(a, b, 16)
    # After timer expiry, retreat_until_ms must be cleared
    assert a.retreat_until_ms == 0


def test_wall_stuck_char_skips_retreat():
    """Char already at wall must skip retreat and attack instead."""
    bat, a, b = _battle_post_intro(seed=1)
    a.hp = 10
    b.mp = b.mp_max
    # Pin a to the left wall, b near it
    a.pos_x = ARENA_LEFT + 5  # within 30px of wall
    b.pos_x = ARENA_LEFT + 60  # in melee range
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    # Because a is wall-stuck, must NOT be in retreat-walking; should attack or idle
    assert a.action_state != "walking" or a.vel_x >= 0  # vel_x >= 0 means not retreating left


def test_lower_hp_threshold_to_15():
    """Defensive retreat triggers only when HP < 15 (not 30 as before)."""
    bat, a, b = _battle_post_intro(seed=1)
    a.hp = 20  # between old (30) and new (15) thresholds
    b.mp = b.mp_max
    a.pos_x = 240
    b.pos_x = 280  # in range
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    # At HP=20, should NOT defensive-retreat
    assert a.retreat_until_ms == 0
    # And at HP=10 it should
    a.hp = 10
    a.action_state = "idle"
    bat._ai_choose_action(a, b, 16)
    assert a.retreat_until_ms > 0


def test_reset_physics_clears_retreat_timer():
    a = Character.load("brick_phone")
    a.reset_physics(initial_x=100, facing=1)
    a.retreat_until_ms = 5000
    a.reset_physics(initial_x=100, facing=1)
    assert a.retreat_until_ms == 0
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_ai_retreat_lock.py -v
```
Expected: all 4 FAIL (no `retreat_until_ms` attribute; threshold still 30; no wall guard).

- [ ] **Step 3: Add `retreat_until_ms` to Character**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/character.py`.

Find the line:
```python
    skill_cd_ready_at: Dict[str, int] = field(default_factory=dict)
```
Add immediately after:
```python
    retreat_until_ms: int = 0
```

Find inside `reset_physics`, after `self.skill_cd_ready_at = {}`, add:
```python
        self.retreat_until_ms = 0
```

- [ ] **Step 4: Update `_ai_choose_action` in battle.py**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`.

Find the constants block near the top (`AI_RETREAT_IN_RANGE_PROB` line region) and add a new constant:
```python
RETREAT_DURATION_MS = 800           # max consecutive ms in retreat before forced re-evaluate
WALL_STUCK_PX = 30                  # distance from arena edge that counts as stuck
DEFENSIVE_RETREAT_HP = 15           # HP below which defensive retreat may trigger
```

Find `_ai_choose_action`. Replace its full body with:

```python
    def _ai_choose_action(self, char: Character, opp: Character, dt_ms: int) -> None:
        """Simple AI: pursue → attack → react → retreat. Only acts when free."""
        if char.action_state in ("attacking", "hit_stagger", "ko"):
            return

        # Retreat-timer expiry: if a previous retreat has run its course, clear and re-evaluate.
        if char.retreat_until_ms > 0 and self.elapsed_ms >= char.retreat_until_ms:
            char.retreat_until_ms = 0

        # Update facing toward opponent
        if opp.pos_x > char.pos_x:
            char.facing = 1
        else:
            char.facing = -1

        distance = abs(char.pos_x - opp.pos_x)
        at_wall = (char.pos_x - ARENA_LEFT < WALL_STUCK_PX or
                   ARENA_RIGHT - char.pos_x < WALL_STUCK_PX)

        # Strategic retreat: MP near full and opponent very close → brief space-out safely
        if (char.mp >= char.mp_max * 0.92 and distance < MELEE_RANGE * 0.9
                and not at_wall and char.retreat_until_ms == 0):
            self._start_retreat(char, opp)
            char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
            return

        # Defensive retreat: low HP and opponent building ult
        if (char.hp < DEFENSIVE_RETREAT_HP and opp.mp >= opp.mp_max * 0.7
                and not at_wall and char.retreat_until_ms == 0):
            self._start_retreat(char, opp)
            char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
            return

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
                # Try to attack
                can_attack = (self.elapsed_ms - char.last_attack_ms) >= char.attack_interval_ms
                if can_attack:
                    self._start_attack(char, opp)
                else:
                    # Cooldown still running — keep walking to stay close
                    self._start_walk(char, char.facing)
            elif roll < AI_ATTACK_IN_RANGE_PROB + AI_JUMP_IN_RANGE_PROB:
                # Jump/dodge
                if char.on_ground:
                    self._start_jump(char)
            elif (roll < AI_ATTACK_IN_RANGE_PROB + AI_JUMP_IN_RANGE_PROB + AI_RETREAT_IN_RANGE_PROB
                  and not at_wall and char.retreat_until_ms == 0):
                # Retreat — create distance
                self._start_retreat(char, opp)
                char.retreat_until_ms = self.elapsed_ms + RETREAT_DURATION_MS
            else:
                # Brief idle — stop walking
                char.vel_x = 0.0
                if char.action_state == "walking":
                    char.action_state = "idle"
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_ai_retreat_lock.py pixel_battle/tests/test_battle.py pixel_battle/tests/test_skill_cooldown.py pixel_battle/tests/test_battle_ai_priority.py -v
```
Expected: all PASS except (verify) the long-standing `test_ai_retreats_when_mp_high_and_close` which was already failing in main before P2. With the new HP threshold = 15, that test's hp=full + mp=75% scenario no longer triggers strategic retreat (which needs mp >= 92%). The expected behavior in that test is also stale.

If `test_ai_retreats_when_mp_high_and_close` is still failing the same way, leave it — it's pre-existing and explicitly out of scope for P2.

- [ ] **Step 6: Commit**

```bash
git add pixel_battle/engine/character.py pixel_battle/engine/battle.py pixel_battle/tests/test_ai_retreat_lock.py
git commit -m "fix(pixel-battle): break retreat lock-up — timer + lower HP threshold + wall guard"
```

---

## Task 2: Integration test — no 5s event-free gaps in a 60s simulated battle

**Files:**
- Create: `pixel_battle/tests/test_battle_no_lock.py`

- [ ] **Step 1: Write failing test**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_battle_no_lock.py`:

```python
"""Regression test: a 60s simulated battle should not have 5+ second event-free gaps
(excluding cinematic playback windows).
"""
from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def _longest_event_gap_excluding_cinematics(events, total_ms):
    """Return the longest gap (ms) between consecutive HIT/MISS events,
    skipping the ULTIMATE_START → ULTIMATE_END windows.
    """
    # Build "active" timeline by clipping out cinematic windows
    cinematic_intervals = []
    starts = [e for e in events if e.type is EventType.ULTIMATE_START]
    ends = [e for e in events if e.type is EventType.ULTIMATE_END]
    for s, e in zip(starts, ends):
        cinematic_intervals.append((s.t_ms, e.t_ms))

    def in_cinematic(t):
        return any(start <= t <= end for start, end in cinematic_intervals)

    action_events = [e for e in events
                     if e.type in (EventType.HIT, EventType.MISS)
                     and not in_cinematic(e.t_ms)]

    if not action_events:
        return total_ms  # no events at all = max gap
    timestamps = [0] + [e.t_ms for e in action_events] + [total_ms]
    # Drop any pair where a cinematic spans between them — subtract cinematic duration
    max_gap = 0
    for i in range(len(timestamps) - 1):
        a, b = timestamps[i], timestamps[i + 1]
        gap = b - a
        # Subtract any cinematic time inside this gap
        for cs, ce in cinematic_intervals:
            if cs >= a and ce <= b:
                gap -= (ce - cs)
        max_gap = max(max_gap, gap)
    return max_gap


def test_60s_battle_no_long_gaps():
    """Run a 60-second battle and assert max event-free gap < 5s (excluding cinematics)."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    while bat.elapsed_ms < 60_000 and bat.state is not BattleState.KO:
        bat.tick_ms(16)
    gap = _longest_event_gap_excluding_cinematics(bat.events, bat.elapsed_ms)
    assert gap < 5000, f"AI lock detected: longest event-free gap = {gap}ms"
```

- [ ] **Step 2: Run test, verify behavior**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_battle_no_lock.py -v
```

Expected: PASS (Task 1 should already have fixed the lock). If it fails, the seed produces a different lock pattern — investigate.

- [ ] **Step 3: Commit**

```bash
git add pixel_battle/tests/test_battle_no_lock.py
git commit -m "test(pixel-battle): integration test catches AI lock regressions"
```

---

## Task 3: Walk bob in renderer

**Files:**
- Modify: `pixel_battle/engine/renderer.py`
- Modify: `pixel_battle/tests/test_renderer.py`

- [ ] **Step 1: Write failing test**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_renderer.py`:

```python
def test_walk_bob_offset_oscillates():
    """Walking animation should produce a non-zero y-offset that oscillates."""
    from pixel_battle.engine.renderer import _walk_bob_offset
    # Across enough frames, offset must take at least one positive AND one negative value
    offsets = [_walk_bob_offset(f) for f in range(60)]
    assert max(offsets) > 0
    assert min(offsets) < 0
    # Amplitude bounded
    assert max(offsets) <= 3
    assert min(offsets) >= -3
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_renderer.py::test_walk_bob_offset_oscillates -v
```
Expected: FAIL — no `_walk_bob_offset`.

- [ ] **Step 3: Add `_walk_bob_offset` + integrate into `_draw_sprite_char`**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/renderer.py`.

Add this helper after the existing `_build_arena_bg` function (top-level, module scope):

```python
def _walk_bob_offset(anim_frame: int) -> int:
    """±3 px sinusoidal y offset for walking sprites — reads as a footstep cycle."""
    import math
    return int(math.sin(anim_frame * 0.6) * 3)
```

Find `_draw_sprite_char`. Find the line:
```python
        # Use midbottom: world_y is the feet position, sprite extends upward
        rect = sprite.get_rect(midbottom=(world_x, world_y))
```
Replace with:
```python
        # Use midbottom: world_y is the feet position, sprite extends upward.
        # Apply walk-bob for the walking state.
        bob = _walk_bob_offset(anim_frame) if anim_state is AnimationState.WALKING else 0
        rect = sprite.get_rect(midbottom=(world_x, world_y + bob))
```

- [ ] **Step 4: Run test, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_renderer.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/renderer.py pixel_battle/tests/test_renderer.py
git commit -m "feat(pixel-battle): walk-bob sprite oscillation"
```

---

## Task 4: Attack timing rebalance + recoil

**Files:**
- Modify: `pixel_battle/engine/animator.py`
- Modify: `pixel_battle/engine/battle.py`
- Modify: `pixel_battle/tests/test_animator.py`
- Modify: `pixel_battle/tests/test_battle.py`

- [ ] **Step 1: Write failing tests**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_animator.py`:

```python
def test_attack_clip_timing_rebalanced():
    """ATTACK clip should be 8/4/10 split (windup/strike/recover), total 22 frames."""
    from pixel_battle.engine.animator import AnimClip, CLIP_DEFINITIONS
    spec = CLIP_DEFINITIONS[AnimClip.ATTACK]
    assert spec == [("attack_windup", 8), ("attack_strike", 4), ("attack_recover", 10)]
```

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_battle.py`:

```python
def test_attacker_recoils_after_landing_hit():
    """After a hit lands, attacker gets a small backward velocity (punch recoil)."""
    from pixel_battle.engine.physics import SPECIAL_RANGE
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed=42))
    bat.tick_ms(2500)
    # Position attacker to the LEFT of defender, in range
    a.pos_x = 200
    b.pos_x = 250  # melee-range
    # Force attack
    basic = a.skills_of_type(__import__('pixel_battle.engine.skill', fromlist=['SkillType']).SkillType.BASIC)[0]
    a.attack_used_kind = basic
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0
    a.vel_x = 0.0
    for _ in range(20):
        bat.tick_ms(16)
        if b.hp < 100:
            break
    # After hitting, a should have a negative vel_x (recoil leftward, away from b which is to the right)
    assert a.vel_x < 0, f"Expected negative recoil vel_x, got {a.vel_x}"
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_animator.py::test_attack_clip_timing_rebalanced pixel_battle/tests/test_battle.py::test_attacker_recoils_after_landing_hit -v
```
Expected: both FAIL (timing still 6/6/6; no recoil logic).

- [ ] **Step 3: Update ATTACK clip timing**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/animator.py`. Find:
```python
    AnimClip.ATTACK: [("attack_windup", 6), ("attack_strike", 6), ("attack_recover", 6)],
```
Replace with:
```python
    AnimClip.ATTACK: [("attack_windup", 8), ("attack_strike", 4), ("attack_recover", 10)],
```

- [ ] **Step 4: Add attacker recoil in `_resolve_attack_hit`**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/battle.py`. In `_resolve_attack_hit`, find the block:
```python
        attacker.last_attack_ms = self.elapsed_ms

        self._emit(
            EventType.HIT,
```

Replace with:
```python
        attacker.last_attack_ms = self.elapsed_ms

        # Punch recoil — attacker gets a small backward velocity reading as reaction force
        recoil_dir = -1 if attacker.pos_x < defender.pos_x else 1
        attacker.vel_x = recoil_dir * 1.5

        self._emit(
            EventType.HIT,
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_animator.py pixel_battle/tests/test_battle.py pixel_battle/tests/test_skill_cooldown.py pixel_battle/tests/test_battle_ai_priority.py -v
```
Expected: PASS (except the pre-existing `test_ai_retreats_when_mp_high_and_close` if still failing).

- [ ] **Step 6: Commit**

```bash
git add pixel_battle/engine/animator.py pixel_battle/engine/battle.py pixel_battle/tests/test_animator.py pixel_battle/tests/test_battle.py
git commit -m "feat(pixel-battle): rebalance attack timing 8/4/10 + add punch recoil"
```

---

## Task 5: `ProjectileSystem` module

**Files:**
- Create: `pixel_battle/engine/projectile.py`
- Create: `pixel_battle/tests/test_projectile.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_projectile.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.projectile import Projectile, ProjectileSystem


def test_projectile_system_starts_empty():
    sys = ProjectileSystem()
    assert len(sys.projectiles) == 0


def test_spawn_creates_projectile():
    sys = ProjectileSystem()
    sys.spawn(x_start=100, y_start=400, x_end=300, y_end=400,
              shape="screw", color=(80, 180, 255), lifetime=8)
    assert len(sys.projectiles) == 1
    p = sys.projectiles[0]
    assert p.x == 100
    assert p.y == 400
    assert p.shape == "screw"
    assert p.lifetime == 8
    assert p.age == 0


def test_projectile_lerps_position():
    sys = ProjectileSystem()
    sys.spawn(x_start=100, y_start=400, x_end=300, y_end=440,
              shape="screw", color=(80, 180, 255), lifetime=4)
    # After 1 update, position should be roughly 1/4 of the way from start to end
    sys.update()
    p = sys.projectiles[0]
    assert 140 <= p.x <= 160
    assert 405 <= p.y <= 415


def test_on_land_callback_fires_once_at_lifetime():
    sys = ProjectileSystem()
    landed = []

    def cb():
        landed.append(True)

    sys.spawn(x_start=0, y_start=0, x_end=100, y_end=0,
              shape="screw", color=(80, 180, 255), lifetime=3, on_land=cb)
    for _ in range(5):
        sys.update()
    # Callback fired exactly once
    assert landed == [True]
    # Aged-out projectile is removed
    assert len(sys.projectiles) == 0


def test_render_does_not_crash_for_both_shapes():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = ProjectileSystem()
    sys.spawn(x_start=50, y_start=50, x_end=200, y_end=200,
              shape="screw", color=(80, 180, 255), lifetime=8)
    sys.spawn(x_start=400, y_start=50, x_end=200, y_end=200,
              shape="shard", color=(80, 180, 255), lifetime=8)
    sys.render(surface)
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_projectile.py -v
```
Expected: ImportError (no `projectile.py`).

- [ ] **Step 3: Create `pixel_battle/engine/projectile.py`**

```python
"""Projectile system: short-lived flying objects (screw darts, glass shards) that
travel from a start to an end point over `lifetime` frames, optionally firing an
`on_land` callback when they reach the end.

Pure rendering — no game logic. Spawned by the episode runner.
"""
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import math
import pygame


@dataclass
class Projectile:
    x: float
    y: float
    x_start: float
    y_start: float
    x_end: float
    y_end: float
    shape: str          # "screw" or "shard"
    color: Tuple[int, int, int]
    lifetime: int
    age: int = 0
    on_land: Optional[Callable[[], None]] = None
    _landed_fired: bool = False


class ProjectileSystem:
    def __init__(self):
        self.projectiles: List[Projectile] = []

    def spawn(self,
              x_start: float, y_start: float,
              x_end: float, y_end: float,
              shape: str,
              color: Tuple[int, int, int],
              lifetime: int = 8,
              on_land: Optional[Callable[[], None]] = None) -> None:
        self.projectiles.append(Projectile(
            x=x_start, y=y_start,
            x_start=x_start, y_start=y_start,
            x_end=x_end, y_end=y_end,
            shape=shape, color=color,
            lifetime=lifetime, age=0,
            on_land=on_land,
        ))

    def update(self) -> None:
        survivors: List[Projectile] = []
        for p in self.projectiles:
            p.age += 1
            if p.age >= p.lifetime:
                if p.on_land is not None and not p._landed_fired:
                    p.on_land()
                    p._landed_fired = True
                # Drop projectile this frame (don't survive)
                continue
            # Linear lerp from start to end over lifetime frames
            t = p.age / p.lifetime
            p.x = p.x_start + (p.x_end - p.x_start) * t
            p.y = p.y_start + (p.y_end - p.y_start) * t
            survivors.append(p)
        self.projectiles = survivors

    def render(self, surface: pygame.Surface) -> None:
        for p in self.projectiles:
            if p.shape == "screw":
                self._draw_screw(surface, p)
            elif p.shape == "shard":
                self._draw_shard(surface, p)

    def _draw_screw(self, surface: pygame.Surface, p: Projectile) -> None:
        # 6x3 px rotating rect with diagonal threads
        cx, cy = int(p.x), int(p.y)
        angle = p.age * 0.4  # rotation speed
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        half_w = 6
        half_h = 2
        # Four corners of the rect rotated around center
        pts = [
            (cx + cos_a * dx - sin_a * dy, cy + sin_a * dx + cos_a * dy)
            for dx, dy in [(-half_w, -half_h), (half_w, -half_h),
                            (half_w, half_h), (-half_w, half_h)]
        ]
        pygame.draw.polygon(surface, p.color, pts)
        # Outline
        pygame.draw.polygon(surface, (20, 20, 30), pts, width=1)

    def _draw_shard(self, surface: pygame.Surface, p: Projectile) -> None:
        # 3 small triangles fanning out (different angles ±15°)
        cx, cy = int(p.x), int(p.y)
        base_angle = math.atan2(p.y_end - p.y_start, p.x_end - p.x_start)
        for ang_offset, alpha in [(-0.26, 200), (0.0, 255), (0.26, 200)]:
            angle = base_angle + ang_offset
            tip_dx = math.cos(angle) * 8
            tip_dy = math.sin(angle) * 8
            side1 = (cx + math.cos(angle + 2.4) * 4, cy + math.sin(angle + 2.4) * 4)
            side2 = (cx + math.cos(angle - 2.4) * 4, cy + math.sin(angle - 2.4) * 4)
            tip = (cx + tip_dx, cy + tip_dy)
            tri_surface = pygame.Surface((20, 20), pygame.SRCALPHA)
            tri_pts = [(tip[0] - cx + 10, tip[1] - cy + 10),
                        (side1[0] - cx + 10, side1[1] - cy + 10),
                        (side2[0] - cx + 10, side2[1] - cy + 10)]
            pygame.draw.polygon(tri_surface, (*p.color, alpha), tri_pts)
            surface.blit(tri_surface, (cx - 10, cy - 10))
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_projectile.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/projectile.py pixel_battle/tests/test_projectile.py
git commit -m "feat(pixel-battle): procedural projectile system (screw + shard shapes)"
```

---

## Task 6: `BannerSystem` module

**Files:**
- Create: `pixel_battle/engine/banner.py`
- Create: `pixel_battle/tests/test_banner.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_banner.py`:

```python
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame

from pixel_battle.engine.banner import Banner, BannerSystem


def test_banner_system_starts_empty():
    sys = BannerSystem()
    assert sys.active is None


def test_spawn_replaces_previous_banner():
    sys = BannerSystem()
    sys.spawn("FIRST", (255, 255, 255))
    sys.spawn("SECOND", (0, 0, 255))
    assert sys.active is not None
    assert sys.active.text == "SECOND"


def test_banner_ages_and_clears_after_lifetime():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = BannerSystem()
    sys.spawn("HELLO", (255, 255, 255))
    for _ in range(BannerSystem.LIFETIME_FRAMES + 2):
        sys.update_and_render(surface)
    assert sys.active is None


def test_banner_x_position_lerps_phase_1():
    pygame.init()
    surface = pygame.Surface((480, 854))
    sys = BannerSystem()
    sys.spawn("HI", (255, 255, 255))
    # At frame 5 (mid phase-1 slide-in), x should be between x_start and x_end
    for _ in range(5):
        sys.update_and_render(surface)
    assert sys.active is not None
    assert BannerSystem.X_START < sys.active.x < BannerSystem.X_END
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_banner.py -v
```
Expected: ImportError.

- [ ] **Step 3: Create `pixel_battle/engine/banner.py`**

```python
"""Skill-name banner system: flashes a big "SKILL NAME!" text across the screen
when a notable skill connects. Slides in from left, holds at center, fades out.

Pure rendering — no game logic. One banner at a time; newer spawn replaces older.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

import pygame


@dataclass
class Banner:
    text: str
    color: Tuple[int, int, int]
    x: float = -200.0
    age: int = 0


class BannerSystem:
    LIFETIME_FRAMES = 36       # ~0.6s at 60fps
    SLIDE_IN_FRAMES = 10
    FADE_OUT_START = 26
    X_START = -200
    X_END = 240                # screen center (480 / 2)
    Y_CENTER = 270
    FONT_SIZE = 48

    def __init__(self):
        self.active: Optional[Banner] = None
        self._font: Optional[pygame.font.Font] = None

    def _get_font(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, self.FONT_SIZE)
        return self._font

    def spawn(self, text: str, color: Tuple[int, int, int]) -> None:
        self.active = Banner(text=text, color=color, x=float(self.X_START), age=0)

    def update_and_render(self, surface: pygame.Surface) -> None:
        if self.active is None:
            return
        b = self.active
        b.age += 1
        if b.age >= self.LIFETIME_FRAMES:
            self.active = None
            return

        # Phase 1: slide in 0 → SLIDE_IN_FRAMES (x lerps START → END)
        if b.age <= self.SLIDE_IN_FRAMES:
            t = b.age / self.SLIDE_IN_FRAMES
            # Ease-out for snappy entry
            t = 1.0 - (1.0 - t) ** 2
            b.x = self.X_START + (self.X_END - self.X_START) * t
        else:
            b.x = float(self.X_END)

        # Phase 3: fade alpha FADE_OUT_START → LIFETIME_FRAMES
        if b.age >= self.FADE_OUT_START:
            fade_t = (b.age - self.FADE_OUT_START) / max(
                1, self.LIFETIME_FRAMES - self.FADE_OUT_START)
            alpha = max(0, int(255 * (1.0 - fade_t)))
        else:
            alpha = 255

        font = self._get_font()
        img = font.render(b.text, True, b.color)
        shadow = font.render(b.text, True, (0, 0, 0))
        img.set_alpha(alpha)
        shadow.set_alpha(alpha)
        rect = img.get_rect(center=(int(b.x), self.Y_CENTER))
        surface.blit(shadow, (rect.x + 3, rect.y + 3))
        surface.blit(img, rect)
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_banner.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/banner.py pixel_battle/tests/test_banner.py
git commit -m "feat(pixel-battle): skill-name banner system"
```

---

## Task 7: Wire ProjectileSystem + BannerSystem into Renderer

**Files:**
- Modify: `pixel_battle/engine/renderer.py`
- Modify: `pixel_battle/tests/test_renderer.py`

- [ ] **Step 1: Write failing tests**

Append to `/Users/arlong/Projects/AIvideo/pixel_battle/tests/test_renderer.py`:

```python
def test_renderer_has_projectiles_and_banners_after_init():
    pygame.init()
    r = Renderer()
    assert r.projectiles is not None
    assert r.banners is not None


def test_render_frame_processes_projectiles_and_banners():
    """A projectile spawned before render_frame should be aged + rendered."""
    pygame.init()
    left = Character.load("brick_phone")
    right = Character.load("glass_slab")
    left.reset_physics(initial_x=120, facing=1)
    right.reset_physics(initial_x=360, facing=-1)
    r = Renderer()
    r.set_hud(left, right)
    r.projectiles.spawn(x_start=120, y_start=400, x_end=360, y_end=400,
                         shape="screw", color=(80, 180, 255), lifetime=4)
    r.banners.spawn("TEST", (255, 255, 255))
    starting_age_p = r.projectiles.projectiles[0].age
    starting_age_b = r.banners.active.age
    r.render_frame(left, right, AnimationState.IDLE, AnimationState.IDLE,
                    anim_frame=0, elapsed_ms=1000)
    assert r.projectiles.projectiles[0].age > starting_age_p
    assert r.banners.active.age > starting_age_b
```

- [ ] **Step 2: Run tests, verify FAIL**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/test_renderer.py -v
```
Expected: 2 new tests FAIL.

- [ ] **Step 3: Wire systems into Renderer**

Edit `/Users/arlong/Projects/AIvideo/pixel_battle/engine/renderer.py`.

Inside `Renderer.__init__`, find the line:
```python
        # Particle system
        from pixel_battle.engine.particles import ParticleSystem
        self.particles = ParticleSystem()
```

Add immediately after:
```python
        # Projectile system (flying screws/shards for CD skills)
        from pixel_battle.engine.projectile import ProjectileSystem
        self.projectiles = ProjectileSystem()
        # Banner system (skill-name flash for CD/special/ultimate hits)
        from pixel_battle.engine.banner import BannerSystem
        self.banners = BannerSystem()
```

In `render_frame`, find the block:
```python
        self.particles.update()
        self.particles.render(self.surface)
        # HUD overlay (skill icons, DPS, damage popups, MP charge ring)
        if self.hud is not None:
            self.hud.render(self.surface, left, right, elapsed_ms)
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

Replace with:
```python
        self.particles.update()
        self.particles.render(self.surface)
        # Projectiles (rendered above particles, below HUD)
        self.projectiles.update()
        self.projectiles.render(self.surface)
        # HUD overlay (skill icons, DPS, damage popups, MP charge ring)
        if self.hud is not None:
            self.hud.render(self.surface, left, right, elapsed_ms)
        # Skill-name banners on top of HUD
        self.banners.update_and_render(self.surface)
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
python -m pytest pixel_battle/tests/test_renderer.py pixel_battle/tests/test_projectile.py pixel_battle/tests/test_banner.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pixel_battle/engine/renderer.py pixel_battle/tests/test_renderer.py
git commit -m "feat(pixel-battle): Renderer hosts ProjectileSystem + BannerSystem"
```

---

## Task 8: Episode runner — spawn projectiles + banners + scale CD particles

**Files:**
- Modify: `pixel_battle/episodes/ep01_brick_vs_glass.py`

- [ ] **Step 1: Identify the relevant block**

Currently, in `ep01_brick_vs_glass.py`, the HIT-event handler block looks like:

```python
            # Screen shake + particles + hit-stop + HUD record
            if ev.type is EventType.HIT:
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

- [ ] **Step 2: Add skill-name banner map after the color map**

Near the top of `/Users/arlong/Projects/AIvideo/pixel_battle/episodes/ep01_brick_vs_glass.py`, find:

```python
_HIT_COLOR_BY_SKILL_TYPE = {
    "basic":    (220, 220, 180),   # white-yellow
    "cooldown": ( 80, 180, 255),   # cyan
    "special":  (255, 140,  40),   # orange
}
```

Add immediately after:

```python
_BANNER_COLOR_BY_SKILL_TYPE = {
    "cooldown": ( 80, 180, 255),
    "special":  (255, 140,  40),
    "ultimate": (255, 220,  80),
}

# Friendly skill names for banners
_SKILL_BANNER_NAME = {
    "screw_dart":           "SCREW DART!",
    "shard_scatter":        "SHARD SCATTER!",
    "snake_strike":         "SNAKE STRIKE!",
    "ringtone_blast":       "RINGTONE BLAST!",
    "ringtone_shock":       "RINGTONE SHOCK!",
    "ad_popup_spam":        "AD POPUP SPAM!",
    "indestructible_throw": "INDESTRUCTIBLE THROW!",
    "force_update":         "FORCE UPDATE!",
}
```

- [ ] **Step 3: Replace the HIT-event block**

Replace the ENTIRE `if ev.type is EventType.HIT:` block (shown above) with:

```python
            # Screen shake + particles + hit-stop + HUD record + (CD-skill: projectile)
            if ev.type is EventType.HIT:
                target_x = int(target_char.pos_x)
                target_y = int(target_char.pos_y) - 80
                actor_char = left if ev.actor == left.id else right
                attacker_x = int(actor_char.pos_x)
                attacker_y = int(actor_char.pos_y) - 80

                st = ev.extra.get("skill_type", "basic")
                skill_id = ev.extra.get("skill_id", "")
                is_crit = bool(ev.extra.get("crit"))
                color = _HIT_COLOR_BY_SKILL_TYPE.get(st, (220, 220, 180))

                if st == "cooldown":
                    # Deferred particle burst until projectile lands.
                    count = int((10 + int(ev.amount)) * 1.8)
                    speed = (6.0 + ev.amount * 0.2) * 1.3
                    shape = "screw" if skill_id == "screw_dart" else "shard"

                    def _land_callback(tx=target_x, ty=target_y, c=color,
                                        ct=count, sp=speed, tgt=ev.target):
                        renderer.particles.emit_hit_burst(tx, ty,
                                                           color=c,
                                                           count=ct, speed=sp)
                        renderer.add_shake(4.0)
                        renderer.request_hit_stop(2)
                        renderer.add_char_flash(tgt, 1.0)

                    renderer.projectiles.spawn(
                        x_start=attacker_x, y_start=attacker_y,
                        x_end=target_x,    y_end=target_y,
                        shape=shape, color=color, lifetime=8,
                        on_land=_land_callback,
                    )
                else:
                    # Basic / special: immediate particle burst
                    count = 10 + int(ev.amount)
                    speed = 6.0 + ev.amount * 0.2
                    renderer.particles.emit_hit_burst(target_x, target_y,
                                                       color=color,
                                                       count=count, speed=speed)
                    if is_crit:
                        renderer.add_shake(8.0)
                        renderer.request_hit_stop(4)
                    elif st == "special":
                        renderer.add_shake(5.0)
                        renderer.request_hit_stop(3)
                    else:
                        renderer.add_shake(3.0)
                    renderer.add_char_flash(ev.target, 1.0)

                # Skill-name banner for non-basic hits
                banner_color = _BANNER_COLOR_BY_SKILL_TYPE.get(st)
                banner_text = _SKILL_BANNER_NAME.get(skill_id)
                if banner_color and banner_text:
                    renderer.banners.spawn(banner_text, banner_color)

                # Record into HUD (popup + DPS) — fires immediately on HIT regardless
                renderer.hud.record_hit(
                    actor_id=ev.actor,
                    dmg=ev.amount,
                    is_crit=is_crit,
                    target_x=target_x,
                    target_y=target_y,
                    t_ms=battle.elapsed_ms,
                )
```

- [ ] **Step 4: Add ultimate banner spawn**

Find the existing `elif ev.type is EventType.ULTIMATE_START:` block. Inside it, after `renderer.request_hit_stop(5)`, add:

```python
                # Skill-name banner for the ultimate
                ult_skill_id = ev.extra.get("skill_id") or ev.extra.get("anim", "")
                banner_text = _SKILL_BANNER_NAME.get(ult_skill_id)
                if banner_text:
                    renderer.banners.spawn(banner_text, (255, 220, 80))
```

- [ ] **Step 5: Run all tests to verify no regression**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pytest pixel_battle/tests/ -v 2>&1 | tail -20
```
Expected: all PASS except the pre-existing `test_ai_retreats_when_mp_high_and_close` if it's still failing.

- [ ] **Step 6: Commit**

```bash
git add pixel_battle/episodes/ep01_brick_vs_glass.py
git commit -m "feat(pixel-battle): episode runner spawns projectiles + banners on hit"
```

---

## Task 9: Visual regression — regenerate `final.mp4` and inspect

**Files:**
- Output: `pixel_battle/output/ep01_brick_vs_glass/final.mp4` (not tracked — .gitignored)

- [ ] **Step 1: Run the episode**

```bash
cd /Users/arlong/Projects/AIvideo && python -m pixel_battle.episodes.ep01_brick_vs_glass
```
Expected: completes without error, prints "Episode 1 produced: …final.mp4" line + winner + duration.

- [ ] **Step 2: Confirm video metadata**

```bash
ffprobe -v error -show_entries format=duration,size:stream=width,height,codec_name -of default=noprint_wrappers=1 /Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/final.mp4
```
Expected: 480×854, h264, duration 8-60s.

- [ ] **Step 3: Check for unusually long event-free gaps**

```bash
python3 -c "
import json
with open('/Users/arlong/Projects/AIvideo/pixel_battle/output/ep01_brick_vs_glass/battle_events.json') as f:
    events = json.load(f)
action = [e for e in events if e['type'] in ('hit','miss')]
gaps = [(action[i+1]['t_ms'] - action[i]['t_ms'], action[i]['t_ms']) for i in range(len(action)-1)]
gaps.sort(reverse=True)
print('Top 3 longest action gaps:')
for g, at in gaps[:3]:
    print(f'  {g/1000:.1f}s @ {at/1000:.1f}s')
print(f'Total events: {len(events)}, action events: {len(action)}')
"
```
Expected: top gaps < 5000 ms (5s).

- [ ] **Step 4: If video looks bad, report — do not auto-tune**

User explicitly said "我們再來修正" — capture issues in a follow-up TODO, don't tune in this plan.

- [ ] **Step 5: Final commit (only if output dir is tracked, which P1 confirmed it isn't)**

```bash
git status
```
If `pixel_battle/output/` is `.gitignored` (it is, per P1 task 12), there's nothing to commit. Skip.

---

## Self-Review

**Spec coverage:**
- A1 HP threshold → Task 1 ✓
- A2 retreat timer → Task 1 ✓
- A3 wall-stuck guard → Task 1 ✓
- Integration test for lock regression → Task 2 ✓
- B1 projectile module → Task 5 ✓
- B2 CD-skill projectile spawn + deferred particles → Task 8 ✓
- B3 banner module → Task 6 ✓
- B4 CD particle scaling → Task 8 ✓
- C1 walk bob → Task 3 ✓
- C2 attack timing rebalance → Task 4 ✓
- C3 punch recoil → Task 4 ✓
- Renderer integration of new systems → Task 7 ✓
- Visual regression → Task 9 ✓

**Placeholder scan:** No TBDs. Every code-bearing step has full code. No "similar to" references.

**Type consistency:**
- `Character.retreat_until_ms: int` — used as int in Tasks 1, 2 ✓
- `ProjectileSystem.spawn(x_start, y_start, x_end, y_end, shape, color, lifetime, on_land)` — same kwargs in Tasks 5, 7, 8 ✓
- `BannerSystem.spawn(text, color)` — same in Tasks 6, 7, 8 ✓
- `Renderer.projectiles` and `Renderer.banners` — referenced consistently in Tasks 7, 8 ✓
- Skill-name banner string format ("SCREW DART!") — consistent in Task 8 ✓
- HIT-event handler refactor preserves all existing HUD.record_hit kwargs from P1 ✓

No issues found.
