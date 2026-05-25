"""KO sequence controller — impact flash → slow-motion → hold + zoom.

Per render. `tick(ko_active, ko_loser_x, dt_ms)` returns a `TickResult`
describing how `_render_fight` should drive this frame: how much to scale
the engine's `dt_ms`, the camera zoom, the splash alpha, and one-shot
spawn signals."""
from __future__ import annotations
from dataclasses import dataclass, field

IMPACT_MS = 200
SLOWMO_MS = 1000
HOLD_MS = 1500
SLOWMO_DT_SCALE = 1.0 / 3.0
MAX_ZOOM = 1.6


@dataclass
class TickResult:
    dt_scale: float
    zoom: float
    zoom_focus_x: int
    splash_alpha: int
    spawn_flash: bool = False
    spawn_splash: bool = False


class KOSequence:
    """State machine: INACTIVE → IMPACT → SLOW_MO → HOLD.

    Call `tick` every rendered frame. Returns a `TickResult` that tells the
    renderer how to scale the engine dt, how much to zoom, and whether to
    fire one-shot spawn signals this frame.
    """

    def __init__(self):
        self._t_ms: int = 0
        self._active: bool = False
        self._spawned_flash: bool = False
        self._spawned_splash: bool = False
        self._loser_x: int = 240

    def tick(self, ko_active: bool, ko_loser_x: int, dt_ms: int) -> TickResult:
        if not ko_active:
            return TickResult(dt_scale=1.0, zoom=1.0, zoom_focus_x=240,
                              splash_alpha=0)

        if not self._active:
            # First tick — activate and record loser position
            self._active = True
            self._loser_x = ko_loser_x
            self._t_ms = 0
            self._spawned_flash = False
            self._spawned_splash = False

        result = TickResult(dt_scale=1.0, zoom=1.0, zoom_focus_x=self._loser_x,
                            splash_alpha=0)

        if self._t_ms < IMPACT_MS:
            # IMPACT phase (0–200 ms)
            if not self._spawned_flash:
                result.spawn_flash = True
                self._spawned_flash = True
            if not self._spawned_splash:
                result.spawn_splash = True
                self._spawned_splash = True
            frac = self._t_ms / IMPACT_MS
            result.dt_scale = SLOWMO_DT_SCALE
            result.zoom = 1.0 + (MAX_ZOOM - 1.0) * frac * 0.5
            result.splash_alpha = int(255 * frac)

        elif self._t_ms < IMPACT_MS + SLOWMO_MS:
            # SLOW_MO phase (200–1200 ms)
            frac = (self._t_ms - IMPACT_MS) / SLOWMO_MS
            result.dt_scale = SLOWMO_DT_SCALE
            result.zoom = 1.0 + (MAX_ZOOM - 1.0) * (0.5 + 0.5 * frac)
            result.splash_alpha = 255

        else:
            # HOLD phase (1200 ms+)
            result.dt_scale = 0.0
            result.zoom = MAX_ZOOM
            result.splash_alpha = 255

        self._t_ms += dt_ms
        return result
