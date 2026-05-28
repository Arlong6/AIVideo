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
