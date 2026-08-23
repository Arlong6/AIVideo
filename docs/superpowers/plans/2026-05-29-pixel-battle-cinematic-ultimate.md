# Cinematic Ultimate Sequence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the one-shot ultimate VFX with a full 2.7-second cinematic sequence — 1500ms anticipation (engine frozen, vignette, magic circle, converging particles, caster aura), 200ms release (white flash → beam fires), 1000ms aftermath (smoke clouds, defender silhouette outline).

**Architecture:** New `UltimateSequence` state machine in `pixel_battle/rl/ultimate_sequence.py` (mirrors `KOSequence`). `_render_fight` in `play.py` instantiates it and calls `ult_seq.tick()` each render frame. The sequence returns a `UltSeqResult` dataclass controlling `dt_scale`, overlay parameters, and one-shot spawn signals. New VFX helpers added to `pixel_battle/rl/impact_fx.py`. Engine is NOT touched — it applies damage instantly; only the renderer plays the cinematic.

**Tech Stack:** Python 3, pygame (SRCALPHA surfaces), existing `ImpactFX` particle system, existing `_Spark`/`CameraShake` infrastructure.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pixel_battle/rl/ultimate_sequence.py` | **CREATE** | 3-phase state machine (ANTICIPATION → RELEASE → AFTERMATH) + `UltSeqResult` |
| `pixel_battle/rl/impact_fx.py` | **MODIFY** | Add 5 new VFX helpers: `spawn_vignette`, `spawn_caster_aura`, `spawn_magic_circle`, `spawn_converging_particles`, `spawn_release_flash`, `spawn_smoke_cloud`, `spawn_defender_silhouette` — plus internal dataclasses |
| `pixel_battle/rl/play.py` | **MODIFY** | Import + instantiate `UltimateSequence`; replace current `ultimate_start` handling in `_render_fight` with phase-driven dispatch; plumb dt_scale into engine tick |
| `pixel_battle/tests/test_rl_ultimate_sequence.py` | **CREATE** | 5 unit tests for the state machine and VFX |

---

## Task 1 — Create `UltimateSequence` state machine

**Files:**
- Create: `pixel_battle/rl/ultimate_sequence.py`
- Test: `pixel_battle/tests/test_rl_ultimate_sequence.py`

- [ ] **Step 1.1: Write the failing tests first**

Create `pixel_battle/tests/test_rl_ultimate_sequence.py` with this content:

```python
"""Tests for UltimateSequence — 3-phase cinematic state machine."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame
pygame.init()
pygame.display.set_mode((1, 1))

from pixel_battle.rl.ultimate_sequence import UltimateSequence, Phase


def test_ultimate_sequence_phases():
    """ULTIMATE_START event → ANTICIPATION → RELEASE → AFTERMATH at correct ms."""
    seq = UltimateSequence()
    # Before trigger: inactive
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase is None

    # Trigger
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.ANTICIPATION

    # Advance to just before RELEASE boundary (1500ms - 16ms elapsed)
    for _ in range(93):          # 93 × 16ms = 1488ms total elapsed (still in ANTICIPATION)
        r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.ANTICIPATION

    # One more tick crosses 1500ms → RELEASE
    r = seq.tick(triggered=False, dt_ms=16)   # now at 1504ms
    assert r.phase == Phase.RELEASE

    # Advance through RELEASE (200ms) → should enter AFTERMATH
    for _ in range(13):          # 13 × 16ms = 208ms
        r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase == Phase.AFTERMATH

    # Advance through AFTERMATH (1000ms)
    for _ in range(63):          # 63 × 16ms = 1008ms
        r = seq.tick(triggered=False, dt_ms=16)
    # After AFTERMATH: phase returns to None
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.phase is None


def test_ultimate_sequence_freezes_engine():
    """dt_scale == 0.0 during ANTICIPATION phase."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))
    r = seq.tick(triggered=False, dt_ms=16)
    assert r.dt_scale == 0.0, f"Expected dt_scale=0.0 during ANTICIPATION, got {r.dt_scale}"


def test_caster_aura_grows():
    """Aura radius at t=200ms < t=1400ms (grows through anticipation)."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))

    # Tick to t≈200ms (12 ticks × 16ms = 192ms)
    r_early = None
    for _ in range(12):
        r_early = seq.tick(triggered=False, dt_ms=16)

    # Tick to t≈1400ms (another 75 ticks × 16ms = 1200ms → total ≈1392ms)
    r_late = None
    for _ in range(75):
        r_late = seq.tick(triggered=False, dt_ms=16)

    assert r_early is not None and r_late is not None
    assert r_early.caster_aura_radius < r_late.caster_aura_radius, (
        f"Aura radius should grow: early={r_early.caster_aura_radius} "
        f"late={r_late.caster_aura_radius}"
    )


def test_release_flash_alpha_decays():
    """Release flash alpha at t=0 (just entered RELEASE) > alpha at t=200ms (end of RELEASE)."""
    seq = UltimateSequence()
    seq.trigger(caster_x=100.0, caster_y=700.0, defender_x=300.0, defender_y=700.0,
                color=(255, 240, 120))

    # Fast-forward to RELEASE phase (advance 1500ms in large steps)
    for _ in range(94):          # 94 × 16ms = 1504ms → enters RELEASE
        seq.tick(triggered=False, dt_ms=16)

    r_start = seq.tick(triggered=False, dt_ms=16)
    assert r_start.phase == Phase.RELEASE
    alpha_start = r_start.release_flash_alpha

    # Advance to end of RELEASE (200ms = 12 more ticks × 16ms = 192ms)
    r_end = None
    for _ in range(12):
        r_end = seq.tick(triggered=False, dt_ms=16)

    assert r_end is not None
    assert alpha_start > r_end.release_flash_alpha, (
        f"Flash alpha should decay: start={alpha_start} end={r_end.release_flash_alpha}"
    )


def test_smoke_cloud_drifts_upward():
    """Smoke particles at t=500ms have lower y (higher on screen) than at t=0."""
    from pixel_battle.rl.impact_fx import ImpactFX
    import pygame
    fx = ImpactFX()
    surf = pygame.Surface((480, 854))
    fx.spawn_smoke_cloud(x=240.0, y=600.0, color=(180, 180, 180))

    # Record initial y positions of smoke particles
    initial_ys = [p.y for p in fx._smoke_clouds]

    # Advance 500ms (31 × 16ms = 496ms)
    for _ in range(31):
        fx.update_and_draw(surf, dt_ms=16)

    # Record final y positions
    final_ys = [p.y for p in fx._smoke_clouds]

    assert len(initial_ys) > 0, "spawn_smoke_cloud should create particles"
    if final_ys:
        avg_initial = sum(initial_ys) / len(initial_ys)
        avg_final = sum(final_ys) / len(final_ys)
        assert avg_final < avg_initial, (
            f"Smoke should drift upward (lower y): initial_avg={avg_initial:.1f} "
            f"final_avg={avg_final:.1f}"
        )
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
python -m pytest pixel_battle/tests/test_rl_ultimate_sequence.py -v --tb=short 2>&1 | tail -20
```

Expected: all 5 tests FAIL (ImportError for `UltimateSequence`)

- [ ] **Step 1.3: Create `ultimate_sequence.py`**

Create `pixel_battle/rl/ultimate_sequence.py`:

```python
"""Cinematic 3-phase ultimate sequence controller.

Mirrors KOSequence: call `trigger()` when ULTIMATE_START fires, then
`tick()` every render frame. Returns `UltSeqResult` with per-frame
rendering parameters that `_render_fight` maps to VFX calls.

Phase durations:
  ANTICIPATION  1500 ms — engine frozen (dt_scale=0), vignette builds, magic circle, particles converge
  RELEASE        200 ms — dt_scale=0.3, full-screen white flash, beam fires
  AFTERMATH     1000 ms — dt_scale=1.0, smoke + silhouette
"""
from __future__ import annotations
import enum
import math
from dataclasses import dataclass
from typing import Optional, Tuple


class Phase(enum.Enum):
    ANTICIPATION = "anticipation"
    RELEASE = "release"
    AFTERMATH = "aftermath"


ANTICIPATION_MS = 1500
RELEASE_MS = 200
AFTERMATH_MS = 1000

_TOTAL_MS = ANTICIPATION_MS + RELEASE_MS + AFTERMATH_MS

# Aura radius: 20 → 120 px over anticipation
AURA_RADIUS_START = 20
AURA_RADIUS_END = 120

# Vignette alpha: 0 → 140 over anticipation, 140 → 0 over aftermath
VIGNETTE_ALPHA_MAX = 140


@dataclass
class UltSeqResult:
    phase: Optional[Phase]
    dt_scale: float
    vignette_alpha: int          # 0-255 full-screen darkening overlay alpha
    caster_aura_radius: float    # radius of the pulsing ring around the caster
    magic_circle_t: float        # 0→1 progress (drives rotation + visibility)
    converging_particles_alpha: int  # alpha for converging particle spawns
    release_flash_alpha: int     # 0-255 for the full-screen white flash during RELEASE
    spawn_release_flash: bool    # one-shot True on first RELEASE frame
    spawn_beam: bool             # one-shot True on first RELEASE frame
    spawn_smoke: bool            # one-shot True on first AFTERMATH frame
    spawn_defender_silhouette: bool  # one-shot True on first AFTERMATH frame
    caster_x: float = 0.0       # stored for VFX positioning
    caster_y: float = 0.0
    defender_x: float = 0.0
    defender_y: float = 0.0
    color: Tuple[int, int, int] = (255, 240, 120)


_INACTIVE_RESULT = UltSeqResult(
    phase=None,
    dt_scale=1.0,
    vignette_alpha=0,
    caster_aura_radius=0.0,
    magic_circle_t=0.0,
    converging_particles_alpha=0,
    release_flash_alpha=0,
    spawn_release_flash=False,
    spawn_beam=False,
    spawn_smoke=False,
    spawn_defender_silhouette=False,
)


class UltimateSequence:
    """State machine: INACTIVE → ANTICIPATION → RELEASE → AFTERMATH → INACTIVE."""

    def __init__(self) -> None:
        self._active: bool = False
        self._elapsed_ms: float = 0.0
        self._caster_x: float = 0.0
        self._caster_y: float = 0.0
        self._defender_x: float = 0.0
        self._defender_y: float = 0.0
        self._color: Tuple[int, int, int] = (255, 240, 120)
        # one-shot guards
        self._spawned_release: bool = False
        self._spawned_aftermath: bool = False

    def trigger(
        self,
        caster_x: float,
        caster_y: float,
        defender_x: float,
        defender_y: float,
        color: Tuple[int, int, int],
    ) -> None:
        """Start the cinematic sequence. Call when ULTIMATE_START event fires."""
        self._active = True
        self._elapsed_ms = 0.0
        self._caster_x = caster_x
        self._caster_y = caster_y
        self._defender_x = defender_x
        self._defender_y = defender_y
        self._color = color
        self._spawned_release = False
        self._spawned_aftermath = False

    def tick(self, triggered: bool, dt_ms: float) -> UltSeqResult:
        """Advance by dt_ms and return per-frame rendering instructions.

        `triggered` is ignored after the first call to `trigger()`; it is kept
        for API symmetry with KOSequence.
        """
        if not self._active:
            return _INACTIVE_RESULT

        t = self._elapsed_ms
        result = UltSeqResult(
            phase=None,
            dt_scale=1.0,
            vignette_alpha=0,
            caster_aura_radius=0.0,
            magic_circle_t=0.0,
            converging_particles_alpha=0,
            release_flash_alpha=0,
            spawn_release_flash=False,
            spawn_beam=False,
            spawn_smoke=False,
            spawn_defender_silhouette=False,
            caster_x=self._caster_x,
            caster_y=self._caster_y,
            defender_x=self._defender_x,
            defender_y=self._defender_y,
            color=self._color,
        )

        if t < ANTICIPATION_MS:
            # ── ANTICIPATION ──────────────────────────────────────────────────
            frac = t / ANTICIPATION_MS   # 0.0 → 1.0
            result.phase = Phase.ANTICIPATION
            result.dt_scale = 0.0
            result.vignette_alpha = int(VIGNETTE_ALPHA_MAX * frac)
            result.caster_aura_radius = AURA_RADIUS_START + (AURA_RADIUS_END - AURA_RADIUS_START) * frac
            result.magic_circle_t = frac
            result.converging_particles_alpha = int(200 * frac)

        elif t < ANTICIPATION_MS + RELEASE_MS:
            # ── RELEASE ───────────────────────────────────────────────────────
            rel_t = t - ANTICIPATION_MS   # 0 → RELEASE_MS
            rel_frac = rel_t / RELEASE_MS  # 0.0 → 1.0
            result.phase = Phase.RELEASE
            result.dt_scale = 0.3
            # Flash is full white at start of RELEASE and decays to 0
            result.release_flash_alpha = int(255 * (1.0 - rel_frac))
            result.vignette_alpha = int(VIGNETTE_ALPHA_MAX * (1.0 - rel_frac))
            # One-shot spawns on the very first RELEASE frame
            if not self._spawned_release:
                self._spawned_release = True
                result.spawn_release_flash = True
                result.spawn_beam = True

        elif t < ANTICIPATION_MS + RELEASE_MS + AFTERMATH_MS:
            # ── AFTERMATH ─────────────────────────────────────────────────────
            aft_t = t - ANTICIPATION_MS - RELEASE_MS
            result.phase = Phase.AFTERMATH
            result.dt_scale = 1.0
            # One-shot spawns on the very first AFTERMATH frame
            if not self._spawned_aftermath:
                self._spawned_aftermath = True
                result.spawn_smoke = True
                result.spawn_defender_silhouette = True

        else:
            # Sequence complete
            self._active = False
            return _INACTIVE_RESULT

        self._elapsed_ms += dt_ms
        return result
```

- [ ] **Step 1.4: Run the 4 state-machine tests (skip smoke test — ImpactFX not yet modified)**

```bash
python -m pytest pixel_battle/tests/test_rl_ultimate_sequence.py::test_ultimate_sequence_phases pixel_battle/tests/test_rl_ultimate_sequence.py::test_ultimate_sequence_freezes_engine pixel_battle/tests/test_rl_ultimate_sequence.py::test_caster_aura_grows pixel_battle/tests/test_rl_ultimate_sequence.py::test_release_flash_alpha_decays -v --tb=short 2>&1 | tail -10
```

Expected: 4 PASSED

- [ ] **Step 1.5: Commit**

```bash
git add pixel_battle/rl/ultimate_sequence.py pixel_battle/tests/test_rl_ultimate_sequence.py
git commit -m "feat(pixel-battle/rl): UltimateSequence state machine — 3-phase controller"
```

---

## Task 2 — Add cinematic VFX helpers to `ImpactFX`

**Files:**
- Modify: `pixel_battle/rl/impact_fx.py`
- Test: `pixel_battle/tests/test_rl_ultimate_sequence.py` (smoke test)

We add 7 new methods to `ImpactFX`. They use existing `_Spark` for particles and new dataclasses for the complex per-frame effects.

- [ ] **Step 2.1: Add dataclasses and constants near the top of `impact_fx.py`**

After the `_UltimateSlam` dataclass (around line 222), add these new dataclasses and constants:

```python
# ── Cinematic ultimate VFX constants ─────────────────────────────────────────
VIGNETTE_SURFACE_CACHE: dict = {}     # cache keyed by (w, h) — reuse alpha surface
SMOKE_CLOUD_MS = 1000
DEFENDER_SILHOUETTE_MS = 600
CONVERGING_PARTICLE_MS = 600         # each homing particle lives up to 600 ms
CONVERGING_PARTICLE_SPEED = 12.0     # px/tick toward target (accelerating)


@dataclass
class _SmokeParticle:
    """A single smoke puff drifting upward and fading."""
    x: float
    y: float
    vx: float           # slow horizontal drift
    vy: float           # upward velocity (negative = up)
    radius: float       # current radius (grows slightly)
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = SMOKE_CLOUD_MS


@dataclass
class _DefenderSilhouette:
    """Defender ghost outline rendered in stark white, fading over 600 ms."""
    x: float
    y: float
    age_ms: int = 0
    life_ms: int = DEFENDER_SILHOUETTE_MS


@dataclass
class _MagicCircle:
    """Flat ellipse 'magic circle' at the caster's feet, rotating over its lifetime."""
    cx: float         # world x center
    ground_y: float   # world y feet
    radius: float     # semi-major axis (px)
    color: Tuple[int, int, int]
    rotation: float   # radians, advances each tick
    age_ms: int = 0
    life_ms: int = 1500   # matches ANTICIPATION_MS


@dataclass
class _CasterAura:
    """Pulsing ring(s) around the caster during anticipation."""
    cx: float
    cy: float
    radius: float     # current peak radius (grows each tick via UltSeqResult)
    color: Tuple[int, int, int]
    t: float          # 0.0→1.0 phase progress (drives sin pulse)
    age_ms: int = 0
    life_ms: int = 1500


@dataclass
class _ReleaseFlash:
    """Full-screen white flash that decays over RELEASE_MS (200 ms)."""
    age_ms: int = 0
    life_ms: int = 200
    peak_alpha: int = 255


@dataclass
class _HomingParticle:
    """A particle that accelerates toward a target point."""
    x: float
    y: float
    target_x: float
    target_y: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = CONVERGING_PARTICLE_MS
    speed: float = CONVERGING_PARTICLE_SPEED
```

- [ ] **Step 2.2: Add new list fields to `ImpactFX.__init__`**

Inside `ImpactFX.__init__`, after the `self._endpoint_stars` line (around line 313), add:

```python
        # Cinematic ultimate VFX queues
        self._smoke_clouds: List[_SmokeParticle] = []
        self._defender_silhouettes: List[_DefenderSilhouette] = []
        self._magic_circles: List[_MagicCircle] = []
        self._caster_auras: List[_CasterAura] = []
        self._release_flashes: List[_ReleaseFlash] = []
        self._homing_particles: List[_HomingParticle] = []
```

- [ ] **Step 2.3: Add the 7 spawn methods to `ImpactFX`**

After the `spawn_ultimate_slam` method (around line 586), insert these methods:

```python
    # ── Cinematic ultimate VFX ─────────────────────────────────────────────────

    def spawn_vignette(self, alpha: int, surf_size: Tuple[int, int]) -> None:
        """Draw a darkening vignette overlay immediately onto any surface.

        Call each frame during anticipation with alpha from UltSeqResult.vignette_alpha.
        We store the alpha on self and draw it in update_and_draw — callers should NOT
        pass a surf here. Instead just store the desired alpha; update_and_draw reads it.
        """
        self._vignette_alpha = min(255, max(0, alpha))
        self._vignette_surf_size = surf_size

    def spawn_caster_aura(
        self,
        cx: float,
        cy: float,
        radius: float,
        color: Tuple[int, int, int],
        t: float,
    ) -> None:
        """Per-frame pulsing rings at (cx, cy). Call every anticipation frame.

        Replaces the existing entry in _caster_auras so only one is active at a time.
        """
        self._caster_auras = [_CasterAura(cx=cx, cy=cy, radius=radius, color=color, t=t)]

    def spawn_magic_circle(
        self,
        cx: float,
        ground_y: float,
        radius: float,
        color: Tuple[int, int, int],
        rotation: float,
    ) -> None:
        """Per-frame flat rotating ellipse at the caster's feet during anticipation.

        Replaces the existing entry so only one is active at a time.
        """
        self._magic_circles = [
            _MagicCircle(cx=cx, ground_y=ground_y, radius=radius,
                         color=color, rotation=rotation)
        ]

    def spawn_converging_particles(
        self,
        target_x: float,
        target_y: float,
        color: Tuple[int, int, int],
        surf_w: int,
        surf_h: int,
        n: int = 3,
    ) -> None:
        """Spawn n particles at random screen edges that home toward (target_x, target_y)."""
        for _ in range(n):
            edge = random.randint(0, 3)   # 0=top, 1=right, 2=bottom, 3=left
            if edge == 0:
                x, y = random.uniform(0, surf_w), 0.0
            elif edge == 1:
                x, y = float(surf_w), random.uniform(0, surf_h)
            elif edge == 2:
                x, y = random.uniform(0, surf_w), float(surf_h)
            else:
                x, y = 0.0, random.uniform(0, surf_h)
            self._homing_particles.append(_HomingParticle(
                x=x, y=y, target_x=target_x, target_y=target_y, color=color))

    def spawn_release_flash(self) -> None:
        """Trigger the 200 ms full-screen white flash for the RELEASE phase."""
        self._release_flashes.append(_ReleaseFlash())

    def spawn_smoke_cloud(
        self,
        x: float,
        y: float,
        color: Tuple[int, int, int],
        n: int = 12,
    ) -> None:
        """Spawn n smoke puffs at (x, y) drifting upward and outward over 1 s."""
        for i in range(n):
            angle = random.uniform(-math.pi, 0.0)  # upward hemisphere
            speed = random.uniform(0.8, 2.5)
            vx = math.cos(angle) * speed * random.uniform(0.5, 1.5)
            vy = math.sin(angle) * speed - random.uniform(0.5, 1.0)  # upward bias
            radius = random.uniform(8.0, 22.0)
            # Mix brand color + grey for smoke feel
            smoke_col = (
                int(color[0] * 0.35 + 140),
                int(color[1] * 0.35 + 140),
                int(color[2] * 0.35 + 140),
            )
            self._smoke_clouds.append(_SmokeParticle(
                x=x + random.uniform(-20, 20),
                y=y - 80 + random.uniform(-20, 20),
                vx=vx, vy=vy, radius=radius, color=smoke_col))

    def spawn_defender_silhouette(
        self,
        defender_x: float,
        defender_y: float,
    ) -> None:
        """Render a stark white ghost outline of the defender that fades over 600 ms."""
        self._defender_silhouettes.append(
            _DefenderSilhouette(x=defender_x, y=defender_y))
```

- [ ] **Step 2.4: Add `_vignette_alpha` and `_vignette_surf_size` to `ImpactFX.__init__`**

Right after the existing `self.camera_shake` line (around line 307 in `__init__`), add:

```python
        # Cinematic vignette state (driven by UltimateSequence each frame)
        self._vignette_alpha: int = 0
        self._vignette_surf_size: Tuple[int, int] = (480, 854)
```

- [ ] **Step 2.5: Add rendering code to `update_and_draw` for the new effects**

At the very end of `update_and_draw`, right before the last `# Draw screen flash overlay` block (around line 1150), insert:

```python
        # ── Vignette overlay (cinematic ultimate anticipation) ─────────────────
        if self._vignette_alpha > 0:
            try:
                vw, vh = self._vignette_surf_size
                vig = pygame.Surface((vw, vh), pygame.SRCALPHA)
                # Radial gradient: dark at edges, transparent in center
                # Build as a solid fill first, then punch a transparent circle in center
                vig.fill((0, 0, 0, self._vignette_alpha))
                # Punch out a transparent ellipse in center (40% of screen)
                center_x, center_y = vw // 2, vh // 2
                punch_rx = int(vw * 0.40)
                punch_ry = int(vh * 0.30)
                pygame.draw.ellipse(vig, (0, 0, 0, 0),
                                    (center_x - punch_rx, center_y - punch_ry,
                                     punch_rx * 2, punch_ry * 2))
                surf.blit(vig, (0, 0))
            except Exception:
                pass
            self._vignette_alpha = 0   # reset each frame; caller sets it again next tick

        # ── Magic circles (caster feet ring) ─────────────────────────────────
        alive_mc: List[_MagicCircle] = []
        for mc in self._magic_circles:
            mc.age_ms += dt_ms
            if mc.age_ms >= mc.life_ms:
                continue
            alive_mc.append(mc)
            frac = mc.age_ms / mc.life_ms
            alpha = max(0, int(200 * (1.0 - frac * 0.3)))
            if alpha < 4:
                continue
            try:
                # Flat ellipse at feet (perspective foreshortening)
                rx = int(mc.radius)
                ry = max(2, int(mc.radius * 0.25))
                d = rx * 2 + 8
                mc_surf = pygame.Surface((d, int(ry * 2 + 8)), pygame.SRCALPHA)
                cx_mc, cy_mc = rx + 4, ry + 4
                # Outer ring
                pygame.draw.ellipse(mc_surf, (*mc.color, alpha),
                                    (0, 0, d, ry * 2 + 8), 3)
                # Rotating notch lines (3 evenly spaced, rotating with mc.rotation)
                for k in range(3):
                    ang = mc.rotation + (math.tau * k) / 3
                    nx = cx_mc + int(math.cos(ang) * rx)
                    ny = cy_mc + int(math.sin(ang) * ry * 0.8)
                    pygame.draw.line(mc_surf, (*mc.color, min(255, alpha + 40)),
                                     (cx_mc, cy_mc), (nx, ny), 2)
                surf.blit(mc_surf, (int(mc.cx) - rx - 4,
                                    int(mc.ground_y) - ry - 4))
            except Exception:
                pass
        self._magic_circles = alive_mc

        # ── Caster aura rings ─────────────────────────────────────────────────
        alive_ca: List[_CasterAura] = []
        for ca in self._caster_auras:
            ca.age_ms += dt_ms
            if ca.age_ms >= ca.life_ms:
                continue
            alive_ca.append(ca)
            frac = ca.age_ms / ca.life_ms
            # 3 concentric pulsing rings using sin wave for alpha variation
            for k in range(3):
                phase_offset = k * (math.tau / 3)
                pulse = 0.5 + 0.5 * math.sin(ca.t * math.tau * 2 + phase_offset)
                ring_r = int(ca.radius * (0.7 + 0.3 * k * 0.4))
                alpha = max(0, int(180 * pulse * (1.0 - frac * 0.2)))
                if ring_r < 2 or alpha < 4:
                    continue
                d = ring_r * 2 + 8
                ring_surf = pygame.Surface((d, d), pygame.SRCALPHA)
                pygame.draw.circle(ring_surf, (*ca.color, alpha),
                                   (ring_r + 4, ring_r + 4), ring_r, 3)
                surf.blit(ring_surf, (int(ca.cx) - ring_r - 4,
                                      int(ca.cy) - ring_r - 4))
        self._caster_auras = alive_ca

        # ── Homing (converging) particles ─────────────────────────────────────
        alive_hp: List[_HomingParticle] = []
        for hp in self._homing_particles:
            hp.age_ms += dt_ms
            if hp.age_ms >= hp.life_ms:
                continue
            alive_hp.append(hp)
            # Accelerate toward target
            dx = hp.target_x - hp.x
            dy = hp.target_y - hp.y
            dist = math.hypot(dx, dy)
            if dist > 1.0:
                # speed accelerates over time
                speed_now = hp.speed * (1.0 + hp.age_ms / max(1, hp.life_ms) * 3.0)
                step = min(dist, speed_now)
                hp.x += (dx / dist) * step
                hp.y += (dy / dist) * step
            frac = hp.age_ms / hp.life_ms
            alpha = max(0, int(180 * (1.0 - frac)))
            if alpha < 4:
                continue
            p_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            pygame.draw.circle(p_surf, (*hp.color, alpha),
                               (int(hp.x), int(hp.y)), 3)
            surf.blit(p_surf, (0, 0))
        self._homing_particles = alive_hp

        # ── Release flash ─────────────────────────────────────────────────────
        alive_rf: List[_ReleaseFlash] = []
        for rf in self._release_flashes:
            rf.age_ms += dt_ms
            if rf.age_ms >= rf.life_ms:
                continue
            alive_rf.append(rf)
            frac = rf.age_ms / rf.life_ms
            alpha = max(0, int(rf.peak_alpha * (1.0 - frac)))
            if alpha < 4:
                continue
            try:
                fl_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                fl_surf.fill((255, 255, 255, alpha))
                surf.blit(fl_surf, (0, 0))
            except Exception:
                pass
        self._release_flashes = alive_rf

        # ── Smoke clouds ──────────────────────────────────────────────────────
        alive_sc: List[_SmokeParticle] = []
        for sc in self._smoke_clouds:
            sc.age_ms += dt_ms
            if sc.age_ms >= sc.life_ms:
                continue
            alive_sc.append(sc)
            sc.x += sc.vx
            sc.y += sc.vy
            sc.vy *= 0.98          # slight deceleration
            sc.radius = min(sc.radius + 0.15, 32.0)  # slowly expand
            frac = sc.age_ms / sc.life_ms
            alpha = max(0, int(140 * (1.0 - frac)))
            if alpha < 4 or sc.radius < 2:
                continue
            r = int(sc.radius)
            d = r * 2 + 4
            sc_surf = pygame.Surface((d, d), pygame.SRCALPHA)
            pygame.draw.circle(sc_surf, (*sc.color, alpha), (r + 2, r + 2), r)
            surf.blit(sc_surf, (int(sc.x) - r - 2, int(sc.y) - r - 2))
        self._smoke_clouds = alive_sc

        # ── Defender silhouette ───────────────────────────────────────────────
        alive_ds: List[_DefenderSilhouette] = []
        for ds in self._defender_silhouettes:
            ds.age_ms += dt_ms
            if ds.age_ms >= ds.life_ms:
                continue
            alive_ds.append(ds)
            frac = ds.age_ms / ds.life_ms
            alpha = max(0, int(220 * (1.0 - frac)))
            if alpha < 4:
                continue
            # Draw a simple stick-figure silhouette in white
            cx_ds = int(ds.x)
            fy_ds = int(ds.y)
            sil = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            col = (255, 255, 255, alpha)
            # Head
            pygame.draw.circle(sil, col, (cx_ds, fy_ds - 120), 10, 2)
            # Torso
            pygame.draw.line(sil, col, (cx_ds, fy_ds - 110), (cx_ds, fy_ds - 50), 3)
            # Arms
            pygame.draw.line(sil, col, (cx_ds - 20, fy_ds - 90),
                             (cx_ds + 20, fy_ds - 90), 3)
            # Legs
            pygame.draw.line(sil, col, (cx_ds, fy_ds - 50), (cx_ds - 18, fy_ds), 3)
            pygame.draw.line(sil, col, (cx_ds, fy_ds - 50), (cx_ds + 18, fy_ds), 3)
            surf.blit(sil, (0, 0))
        self._defender_silhouettes = alive_ds
```

- [ ] **Step 2.6: Add `import List` guard — check that `List` from `typing` is already imported**

The file already has `from typing import List, Optional, Tuple` at line 12. No change needed.

- [ ] **Step 2.7: Run the smoke-cloud test**

```bash
python -m pytest pixel_battle/tests/test_rl_ultimate_sequence.py::test_smoke_cloud_drifts_upward -v --tb=short 2>&1 | tail -10
```

Expected: PASSED

- [ ] **Step 2.8: Run all 5 new tests**

```bash
python -m pytest pixel_battle/tests/test_rl_ultimate_sequence.py -v --tb=short 2>&1 | tail -10
```

Expected: 5 PASSED

- [ ] **Step 2.9: Run existing impact_fx tests to verify no regression**

```bash
python -m pytest pixel_battle/tests/test_rl_impact_fx.py -v --tb=short 2>&1 | tail -10
```

Expected: all PASSED

- [ ] **Step 2.10: Commit**

```bash
git add pixel_battle/rl/impact_fx.py
git commit -m "feat(pixel-battle/rl): cinematic ultimate VFX helpers — vignette, magic circle, aura, converging particles, release flash, smoke, silhouette"
```

---

## Task 3 — Wire `UltimateSequence` into `_render_fight` in `play.py`

**Files:**
- Modify: `pixel_battle/rl/play.py`

This is the integration task. We replace the current `ultimate_start` event handler with the new phase-driven approach.

**Key changes:**
1. Import `UltimateSequence` at the top of `_render_fight`'s local imports block.
2. Instantiate `ult_seq = UltimateSequence()` after `ko_seq`.
3. Add `_ult_zoom_focus_x` and `_ult_cam_zoom_target` local vars (already exist; we extend them).
4. In the `et == "ultimate_start"` event handler: call `ult_seq.trigger(...)` instead of the existing inline VFX. Keep the old `spawn_ultimate_beam` / `spawn_ultimate_slam` / etc. — they will now be fired in the RELEASE frame instead.
5. After the event loop each frame: call `ult_result = ult_seq.tick(...)` and dispatch VFX based on phase.
6. During ANTICIPATION: override the `effective_dt` passed to `env.battle.tick_ms` to `0` (engine frozen).

- [ ] **Step 3.1: Add `UltimateSequence` import inside `_render_fight`**

Find the local imports block at the top of `_render_fight` (around line 429):

```python
    from pixel_battle.rl.hud import HUD as _HUD
    from pixel_battle.rl.impact_fx import ImpactFX as _ImpactFX
    from pixel_battle.rl.ko_sequence import KOSequence as _KOSequence
    from pixel_battle.engine.battle import BattleState as _BattleState
    from pixel_battle.engine.skill import SkillType as _SkillType
```

Replace with:

```python
    from pixel_battle.rl.hud import HUD as _HUD
    from pixel_battle.rl.impact_fx import ImpactFX as _ImpactFX
    from pixel_battle.rl.ko_sequence import KOSequence as _KOSequence
    from pixel_battle.rl.ultimate_sequence import UltimateSequence as _UltSequence
    from pixel_battle.engine.battle import BattleState as _BattleState
    from pixel_battle.engine.skill import SkillType as _SkillType
```

- [ ] **Step 3.2: Instantiate `ult_seq` after `ko_seq`**

Find the line `ko_seq = _KOSequence()` (around line 441) and after it add:

```python
    ult_seq = _UltSequence()
    _ult_phase_particle_timer: int = 0  # ms since last converging-particle spawn batch
```

- [ ] **Step 3.3: Replace the `ultimate_start` event handler**

Find the large `elif et == "ultimate_start":` block that runs from around line 679 to line 771. This entire block runs `ult_seq.trigger()` instead of firing VFX directly, and DEFERS the beam/slam VFX to the RELEASE phase.

Replace the entire `elif et == "ultimate_start":` block with:

```python
                elif et == "ultimate_start":
                    # ── CINEMATIC ULTIMATE: trigger sequence, defer VFX to phases ──
                    actor_obj = env.left if ev.actor == env.left.id else env.right
                    defender = env.right if ev.target == env.right.id else env.left
                    burst_color = lcol if actor_obj is env.left else rcol
                    brand_col_ult = getattr(actor_obj, "brand_color",
                                            getattr(actor_obj, "color", burst_color))
                    ult_seq.trigger(
                        caster_x=float(actor_obj.pos_x),
                        caster_y=float(actor_obj.pos_y),
                        defender_x=float(defender.pos_x),
                        defender_y=float(defender.pos_y),
                        color=brand_col_ult,
                    )
                    # Banner + audio flash still fire immediately (non-visual)
                    banner_text = "ULTIMATE!"
                    banner_until_frame = frame + 156
                    _SKILL_BANNER_MAP = {
                        "final_spark": "FINAL SPARK!",
                        "demacian_justice": "DEMACIAN JUSTICE!",
                        "last_breath": "LAST BREATH!",
                        "enchanted_crystal_arrow": "ENCHANTED ARROW!",
                        "force_update": "FORCE UPDATE!",
                        "indestructible_throw": "INDESTRUCTIBLE!",
                    }
                    ult_skill_id = (ev.extra or {}).get("skill_id", "")
                    banner_display = _SKILL_BANNER_MAP.get(
                        ult_skill_id,
                        str(ult_skill_id).upper().replace("_", " ") + "!")
                    impact_fx.spawn_skill_banner(
                        name=banner_display,
                        color=brand_col_ult,
                        surf_size=(WIDTH, HEIGHT))
                    # Store ult vfx type and actor/target positions for RELEASE phase
                    _ult_pending_vfx = (ev.extra or {}).get("vfx", "slam")
                    _ult_actor_x = float(actor_obj.pos_x)
                    _ult_actor_y = float(actor_obj.pos_y)
                    _ult_target_x = float(defender.pos_x)
                    _ult_target_y = float(defender.pos_y)
                    _ult_brand_col = brand_col_ult
                    _ult_burst_color = burst_color
                    _ult_zoom_age_ms = 0.0
                    _ult_zoom_focus_x = float(actor_obj.pos_x)
```

- [ ] **Step 3.4: Initialize the deferred vfx state variables**

Right after the `ult_seq = _UltSequence()` line (Step 3.2), add:

```python
    _ult_pending_vfx: str = ""
    _ult_actor_x: float = 0.0
    _ult_actor_y: float = 0.0
    _ult_target_x: float = 0.0
    _ult_target_y: float = 0.0
    _ult_brand_col: tuple = (255, 240, 120)
    _ult_burst_color: tuple = (255, 255, 255)
```

- [ ] **Step 3.5: Add the per-frame `ult_seq.tick()` dispatch block**

Find the line `# KO sequence — drives slow-mo + zoom once battle.state == KO` (around line 821) and right BEFORE it, insert the ultimate sequence dispatch:

```python
        # ── Ultimate sequence — per-frame cinematic phase dispatch ────────────
        ult_result = ult_seq.tick(triggered=False, dt_ms=RENDER_MS)
        if ult_result.phase is not None:
            # Vignette: request each frame during anticipation
            if ult_result.vignette_alpha > 0:
                impact_fx.spawn_vignette(
                    alpha=ult_result.vignette_alpha,
                    surf_size=(WIDTH, HEIGHT))
            # Caster aura: replace each frame with growing radius
            if ult_result.caster_aura_radius > 0:
                impact_fx.spawn_caster_aura(
                    cx=ult_result.caster_x,
                    cy=ult_result.caster_y - 90,
                    radius=ult_result.caster_aura_radius,
                    color=ult_result.color,
                    t=ult_result.magic_circle_t)
            # Magic circle at caster feet
            if ult_result.magic_circle_t > 0:
                from pixel_battle.engine.physics import GROUND_Y as _GROUND_Y
                impact_fx.spawn_magic_circle(
                    cx=ult_result.caster_x,
                    ground_y=_GROUND_Y,
                    radius=40 + ult_result.magic_circle_t * 40,
                    color=ult_result.color,
                    rotation=ult_result.magic_circle_t * math.pi * 4)
            # Converging particles: spawn every 3-4 render frames
            if ult_result.converging_particles_alpha > 0:
                _ult_phase_particle_timer += int(RENDER_MS)
                if _ult_phase_particle_timer >= 50:   # ~3 frames at 60fps
                    _ult_phase_particle_timer = 0
                    impact_fx.spawn_converging_particles(
                        target_x=ult_result.caster_x,
                        target_y=ult_result.caster_y - 90,
                        color=ult_result.color,
                        surf_w=WIDTH,
                        surf_h=HEIGHT,
                        n=3)
            # Release phase one-shots
            if ult_result.spawn_release_flash:
                impact_fx.spawn_release_flash()
            if ult_result.spawn_beam:
                # Fire the beam VFX that was deferred from the event handler
                if _ult_pending_vfx == "beam":
                    bx = _ult_target_x + (_ult_target_x - _ult_actor_x) // 2
                    active_beams.append([
                        int(_ult_actor_x), int(_ult_actor_y) - 95,
                        int(bx), int(_ult_target_y) - 95,
                        (255, 255, 255), 0])
                    active_beams.append([
                        int(_ult_actor_x), int(_ult_actor_y) - 95,
                        int(bx), int(_ult_target_y) - 95,
                        _ult_burst_color, 0])
                    impact_fx.spawn_beam_fx(
                        x1=_ult_actor_x, x2=bx, y=_ult_actor_y - 95,
                        color=_ult_brand_col)
                    impact_fx.spawn_ultimate_beam(
                        x1=float(_ult_actor_x), x2=float(bx),
                        y=float(_ult_actor_y - 95),
                        color=_ult_brand_col, surf_size=(WIDTH, HEIGHT))
                elif _ult_pending_vfx in ("slam", "dash"):
                    impact_fx.spawn_ultimate_slam(
                        impact_x=float(_ult_target_x),
                        impact_y=float(_ult_target_y),
                        color=_ult_brand_col, surf_size=(WIDTH, HEIGHT))
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 90,
                        (255, 240, 150), 0, 20, 460])
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 90,
                        _ult_burst_color, 0, 24, 520])
                # Camera shake + flash on release
                impact_fx.flash_screen(color=(255, 60, 60), alpha=200)
                impact_fx.camera_shake.trigger(magnitude_px=5.0, duration_ms=200.0)
            # Aftermath one-shots
            if ult_result.spawn_smoke:
                impact_fx.spawn_smoke_cloud(
                    x=_ult_target_x,
                    y=_ult_target_y,
                    color=_ult_brand_col)
            if ult_result.spawn_defender_silhouette:
                impact_fx.spawn_defender_silhouette(
                    defender_x=_ult_target_x,
                    defender_y=_ult_target_y)
        # ── Override slow-mo dt during ultimate anticipation / release ─────────
        if ult_result.phase is not None and ult_result.dt_scale < 1.0:
            _slowmo_remaining_ms = max(_slowmo_remaining_ms, ENGINE_MS * 2)
            _slowmo_dt_scale = ult_result.dt_scale
```

- [ ] **Step 3.6: Add missing `math` import guard**

Check that `import math` is at the top of `play.py`. It is already there (line 9). No change needed.

- [ ] **Step 3.7: Run the existing rl tests to confirm no regression**

```bash
python -m pytest pixel_battle/tests/test_rl_ko_sequence.py pixel_battle/tests/test_rl_impact_fx.py pixel_battle/tests/test_rl_ultimate_sequence.py pixel_battle/tests/test_smoothness_pass.py -v --tb=short 2>&1 | tail -20
```

Expected: all PASSED

- [ ] **Step 3.8: Commit**

```bash
git add pixel_battle/rl/play.py
git commit -m "feat(pixel-battle/rl): wire UltimateSequence into _render_fight — deferred beam, phase-driven VFX"
```

---

## Task 4 — Camera zoom extension for anticipation phase

**Files:**
- Modify: `pixel_battle/rl/play.py`

Currently the ultimate zoom controller (lines 495–503) runs for 600ms (200ms in + 200ms hold + 200ms out). We extend it to cover the full 1700ms anticipation+release window, zooming toward caster during anticipation and pulling back at release.

- [ ] **Step 4.1: Extend the ultimate zoom constants**

Find this block in `_render_fight` (around line 495):

```python
    _ULT_ZOOM_IN_MS = 200
    _ULT_ZOOM_HOLD_MS = 200
    _ULT_ZOOM_OUT_MS = 200
    _ULT_ZOOM_TOTAL_MS = _ULT_ZOOM_IN_MS + _ULT_ZOOM_HOLD_MS + _ULT_ZOOM_OUT_MS
    _ULT_ZOOM_MAX = 1.35
```

Replace with:

```python
    _ULT_ZOOM_IN_MS = 800       # zoom in over first 800ms of anticipation
    _ULT_ZOOM_HOLD_MS = 700     # hold at max through rest of anticipation + release
    _ULT_ZOOM_OUT_MS = 400      # pull back during aftermath
    _ULT_ZOOM_TOTAL_MS = _ULT_ZOOM_IN_MS + _ULT_ZOOM_HOLD_MS + _ULT_ZOOM_OUT_MS
    _ULT_ZOOM_MAX = 1.5         # slightly tighter crop for drama
```

- [ ] **Step 4.2: Run smoothness tests to verify zoom constants don't break anything**

```bash
python -m pytest pixel_battle/tests/test_smoothness_pass.py -v --tb=short 2>&1 | tail -10
```

Expected: all PASSED

- [ ] **Step 4.3: Commit**

```bash
git add pixel_battle/rl/play.py
git commit -m "tune(pixel-battle/rl): extend ultimate camera zoom to cover full 1.9s anticipation+release window"
```

---

## Task 5 — Validation render

**Files:** No code changes — run the scripted renderer and inspect output.

- [ ] **Step 5.1: Run the scripted render for Script 01**

```bash
python -m pixel_battle.rl.play_scripted pixel_battle/data/scripts/01_lux_kite_garen.yaml 2>&1 | tail -5
```

Expected: prints the output path, exits 0.

- [ ] **Step 5.2: Check output exists and duration is ~19-22s**

```bash
python -c "
from pathlib import Path
import subprocess, json
p = Path('pixel_battle/output/scripted/01_lux_kite_garen_raw.mp4')
if not p.exists():
    print('ERROR: output not found'); exit(1)
result = subprocess.run(['ffprobe','-v','quiet','-print_format','json','-show_format', str(p)],
    capture_output=True, text=True)
data = json.loads(result.stdout)
dur = float(data['format']['duration'])
size_mb = p.stat().st_size / 1e6
print(f'Duration: {dur:.1f}s  Size: {size_mb:.1f} MB')
assert 15 < dur < 30, f'Unexpected duration {dur}'
print('PASS')
"
```

- [ ] **Step 5.3: Run full test suite to confirm all tests green**

```bash
python -m pytest pixel_battle/tests/test_rl_ko_sequence.py pixel_battle/tests/test_rl_impact_fx.py pixel_battle/tests/test_rl_ultimate_sequence.py pixel_battle/tests/test_smoothness_pass.py pixel_battle/tests/test_battle.py pixel_battle/tests/test_script01_arena.py pixel_battle/tests/test_play_scripted.py -v --tb=short 2>&1 | tail -20
```

Note: `test_battle.py::test_ultimate_triggers_when_mp_full` and `test_ultimate_locks_combat_during_playback` were already failing before this change (pre-existing). Do not fix them here; they are NOT in scope.

- [ ] **Step 5.4: Final commit with all new files**

```bash
git add pixel_battle/rl/ultimate_sequence.py pixel_battle/rl/impact_fx.py pixel_battle/rl/play.py pixel_battle/tests/test_rl_ultimate_sequence.py
git commit -m "feat(pixel-battle/rl): cinematic ultimate sequence — anticipation/release/aftermath"
```

---

## Self-Review Checklist

### Spec coverage

| Spec requirement | Task |
|---|---|
| 1.5s ANTICIPATION: engine frozen | Task 1 (`dt_scale=0.0`), Task 3 (plumbed into slow-mo) |
| Screen dims (vignette) | Task 2 `spawn_vignette`, Task 3 dispatch |
| Magic circle at caster feet | Task 2 `spawn_magic_circle`, Task 3 dispatch |
| Particles converge from edges | Task 2 `spawn_converging_particles`, Task 3 dispatch |
| Caster pose "raised staff" | Not implemented — pose changes are engine-side; spec says don't touch engine. The aura + magic circle visually cues "charging" |
| Camera zooms toward caster | Task 4 (extended zoom 800ms in, 700ms hold) |
| 0.2s RELEASE: full-screen white flash | Task 2 `spawn_release_flash`, Task 3 `spawn_release_flash` one-shot |
| Beam fires at release | Task 3 `spawn_beam` one-shot fires all beam VFX |
| 1.0s AFTERMATH: beam lingers | Existing `active_beams` already handles this |
| Smoke clouds at impact | Task 2 `spawn_smoke_cloud`, Task 3 `spawn_smoke` one-shot |
| Defender silhouette outline | Task 2 `spawn_defender_silhouette`, Task 3 `spawn_defender_silhouette` one-shot |
| Camera pull-back at release | Task 4 (`_ULT_ZOOM_HOLD_MS` transitions to `_ULT_ZOOM_OUT_MS` during aftermath) |
| HUD HP-bar delay | **Skipped for v1** per spec: "If the HUD HP-delay is hard to integrate, skip it" |
| 5 specified unit tests | Task 1 (4 state machine tests) + Task 2 (smoke test) = 5 total |
| Script 01 only | play_scripted is unchanged; `_render_fight` is shared but guarded by `ult_seq.trigger()` only firing on `ultimate_start` events |
| Engine not modified | Confirmed — only `play.py`, `impact_fx.py`, `ultimate_sequence.py` touched |
| YAML script not modified | Confirmed |

### Placeholder scan

No TBDs or TODOs found. All code blocks are complete.

### Type consistency

- `UltSeqResult.phase: Optional[Phase]` — used as `None` check in `_render_fight` ✓
- `_ult_pending_vfx: str` — set in event handler, read in `spawn_beam` block ✓
- `impact_fx.spawn_vignette(alpha, surf_size)` — alpha set to `0` after draw (reset pattern) ✓
- `impact_fx.spawn_caster_aura(cx, cy, radius, color, t)` — all floats ✓
- `_SmokeParticle.y` — used in smoke-drift test ✓
- `_HomingParticle` fields match `spawn_converging_particles` constructor ✓
