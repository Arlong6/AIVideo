"""Renderer-side impact effects: big sparks, screen flash, floating text,
per-vfx-archetype cast effects, hit-confirm ring, camera shake.

Stateless per spawn; `update_and_draw` ticks all active effects and renders
them onto the supplied world surface. Spawning is decoupled from drawing
so `_render_fight` can route engine events to the spawn helpers and the
per-frame draw step composites everything."""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pygame

TEXT_FONT_SIZE = 22
TEXT_LIFETIME_MS = 400
TEXT_RISE_PX = 30
FLASH_DECAY_PER_FRAME = 18

# ── New VFX effect lifetimes (ms) ─────────────────────────────────────────────
BUFF_PILLAR_MS = 600
AURA_STARBURST_MS = 400
PROJECTILE_TRAIL_MS = 200   # linger after contact
MULTISHOT_FAN_MS = 300
BEAM_MS = 300
DASH_AFTERIMAGE_MS = 350
ULTIMATE_BURST_MS = 500
HIT_RING_MS = 220           # hit-confirm ring duration

ULTIMATE_FONT_SIZE = 32


@dataclass
class _Spark:
    x: float
    y: float
    vx: float
    vy: float
    life_ms: int
    color: Tuple[int, int, int]


@dataclass
class _FloatingText:
    x: int
    y: int
    text: str
    color: Tuple[int, int, int]
    age_ms: int = 0
    font_size: int = TEXT_FONT_SIZE * 2


@dataclass
class _BuffPillar:
    """Bright vertical pillar of brand-color particles rising from the caster."""
    x: float
    y: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = BUFF_PILLAR_MS


@dataclass
class _AuraStarburst:
    """8-point radial starburst + expanding ring at the hip."""
    x: float
    y: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = AURA_STARBURST_MS


@dataclass
class _BeamFX:
    """Thick horizontal beam from caster to target."""
    x1: float
    y: float
    x2: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = BEAM_MS


@dataclass
class _DashAfterimage:
    """Three ghost figures fading along the dash path."""
    # fractions of distance from start to end: 0.25, 0.50, 0.75
    sx: float
    sy: float
    ex: float
    ey: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = DASH_AFTERIMAGE_MS


@dataclass
class _HitRing:
    """Expanding hit-confirm ring at the defender's hip joint."""
    x: float
    y: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = HIT_RING_MS
    min_r: int = 6
    max_r: int = 36


# ── Camera shake helper ────────────────────────────────────────────────────────

class CameraShake:
    """Tracks a decaying camera-shake impulse.

    Call `trigger(magnitude_px, duration_ms)` to start a shake.
    Call `update(dt_ms)` each frame; it returns the (dx, dy) offset for that
    frame.  Offset decays linearly from `magnitude_px` → 0 over `duration_ms`.
    Multiple overlapping calls keep the strongest active shake.
    """

    def __init__(self) -> None:
        self._mag: float = 0.0
        self._elapsed: float = 0.0
        self._duration: float = 0.0

    def trigger(self, magnitude_px: float, duration_ms: float) -> None:
        """Start (or strengthen) a shake impulse."""
        # Keep the stronger shake.
        if magnitude_px >= self._mag or self._elapsed >= self._duration:
            self._mag = magnitude_px
            self._elapsed = 0.0
            self._duration = max(1.0, duration_ms)

    def update(self, dt_ms: float) -> Tuple[int, int]:
        """Advance by dt_ms and return the (dx, dy) offset for this frame."""
        if self._elapsed >= self._duration or self._mag <= 0:
            return (0, 0)
        frac = 1.0 - self._elapsed / self._duration
        current_mag = self._mag * frac
        self._elapsed += dt_ms
        dx = random.randint(-int(current_mag), int(current_mag))
        dy = random.randint(-int(current_mag), int(current_mag))
        return (dx, dy)

    @property
    def active(self) -> bool:
        return self._elapsed < self._duration and self._mag > 0


class ImpactFX:
    """Registry of active impact effects. Construct once per render; call
    `update_and_draw` each frame after drawing the world surface."""

    def __init__(self):
        self._active: List[_Spark] = []
        self._texts: List[_FloatingText] = []
        self._flash_color: Tuple[int, int, int] = (255, 255, 255)
        self._flash_alpha: int = 0
        self._text_font = pygame.font.SysFont(None, TEXT_FONT_SIZE * 2)
        # New per-VFX effect queues
        self._pillars: List[_BuffPillar] = []
        self._starbursts: List[_AuraStarburst] = []
        self._beams: List[_BeamFX] = []
        self._dash_afterimages: List[_DashAfterimage] = []
        self._hit_rings: List[_HitRing] = []
        self.camera_shake: CameraShake = CameraShake()

    def spawn_hit_spark(self, x: int, y: int, damage: int,
                        color: Tuple[int, int, int]) -> None:
        """Radial burst of sparks; count scales with damage."""
        n = max(6, min(28, 6 + damage * 2))
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(2.5, 5.5)
            life = random.randint(140, 280)
            self._active.append(_Spark(
                x=float(x), y=float(y),
                vx=math.cos(ang) * speed, vy=math.sin(ang) * speed,
                life_ms=life, color=color))

    def flash_screen(self, color: Tuple[int, int, int], alpha: int = 200) -> None:
        """Request a full-screen color flash at the given alpha."""
        self._flash_color = color
        self._flash_alpha = max(self._flash_alpha, alpha)

    def spawn_floating_text(self, x: int, y: int, text: str,
                            color: Tuple[int, int, int],
                            font_size: Optional[int] = None) -> None:
        """Spawn text that rises and fades over TEXT_LIFETIME_MS ms."""
        fs = font_size if font_size is not None else TEXT_FONT_SIZE * 2
        self._texts.append(_FloatingText(x=x, y=y, text=text, color=color,
                                         font_size=fs))

    # ── Per-VFX-archetype cast effects ────────────────────────────────────────

    def spawn_buff_pillar(self, x: int, y: int,
                          color: Tuple[int, int, int]) -> None:
        """Shield/buff cast: bright particle pillar + sparkles drifting upward."""
        self._pillars.append(_BuffPillar(x=float(x), y=float(y), color=color))
        # Seed radial sparks immediately for the "radiating body" feel
        n = 14
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(1.2, 3.5)
            life = random.randint(300, BUFF_PILLAR_MS)
            # Upward bias: override y velocity to rise
            vy = -abs(random.uniform(2.0, 5.0))
            self._active.append(_Spark(
                x=float(x) + random.uniform(-12, 12),
                y=float(y),
                vx=math.cos(ang) * speed,
                vy=vy,
                life_ms=life,
                color=color))

    def spawn_aura_starburst(self, x: int, y: int,
                              color: Tuple[int, int, int]) -> None:
        """Aura/channel: 8-point starburst + expanding ring at hip joint."""
        self._starbursts.append(_AuraStarburst(x=float(x), y=float(y),
                                                color=color))
        # Immediate outward burst sparks
        for i in range(8):
            ang = (math.tau * i) / 8
            speed = random.uniform(3.5, 6.0)
            self._active.append(_Spark(
                x=float(x), y=float(y),
                vx=math.cos(ang) * speed,
                vy=math.sin(ang) * speed,
                life_ms=random.randint(200, AURA_STARBURST_MS),
                color=color))

    def spawn_beam_fx(self, x1: float, x2: float, y: float,
                      color: Tuple[int, int, int]) -> None:
        """Beam cast: thick glowing horizontal beam from x1 to x2 at height y."""
        self._beams.append(_BeamFX(x1=x1, y=y, x2=x2, color=color))

    def spawn_dash_afterimage(self, sx: float, sy: float,
                               ex: float, ey: float,
                               color: Tuple[int, int, int]) -> None:
        """Dash cast: three ghost torsos fading along the dash path."""
        self._dash_afterimages.append(
            _DashAfterimage(sx=sx, sy=sy, ex=ex, ey=ey, color=color))

    def spawn_hit_ring(self, x: int, y: int,
                       color: Tuple[int, int, int]) -> None:
        """Hit-confirm: expanding alpha-fading ring at the defender's hip."""
        self._hit_rings.append(_HitRing(x=float(x), y=float(y), color=color))

    def spawn_ultimate_burst(self, x: int, y: int,
                              color: Tuple[int, int, int],
                              surf_size: Tuple[int, int] = (480, 854)) -> None:
        """Ultimate: full-screen brand-color flash + 30 radial sparks + giant text.

        `surf_size` is passed so the flash overlay can be properly sized;
        the caller can pass (WIDTH, HEIGHT) from the renderer.
        """
        # Full-screen brand-color flash at 250 alpha
        self.flash_screen(color=color, alpha=250)
        # Camera shake: 3 px, 200 ms
        self.camera_shake.trigger(magnitude_px=3.0, duration_ms=200.0)
        # 30 large radial sparks
        n = 30
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            speed = random.uniform(4.0, 9.0)
            life = random.randint(300, ULTIMATE_BURST_MS)
            self._active.append(_Spark(
                x=float(x), y=float(y),
                vx=math.cos(ang) * speed,
                vy=math.sin(ang) * speed,
                life_ms=life,
                color=color))
        # Giant "ULTIMATE!" floating text in caster's brand color
        cx = surf_size[0] // 2
        cy = surf_size[1] // 3
        self._texts.append(_FloatingText(
            x=cx, y=cy,
            text="ULTIMATE!",
            color=color,
            font_size=ULTIMATE_FONT_SIZE * 2))

    def update_and_draw(self, surf: pygame.Surface, dt_ms: int) -> None:
        """Advance all effects by dt_ms and draw onto surf."""
        # Update and draw sparks
        alive: List[_Spark] = []
        for s in self._active:
            s.x += s.vx
            s.y += s.vy
            s.vy += 0.25   # gravity-like droop
            s.life_ms -= dt_ms
            if s.life_ms > 0:
                alive.append(s)
                pygame.draw.line(surf, s.color,
                                 (int(s.x), int(s.y)),
                                 (int(s.x - s.vx), int(s.y - s.vy)),
                                 width=2)
        self._active = alive

        # ── Buff pillars (shield/buff cast) ──────────────────────────────────
        alive_pillars: List[_BuffPillar] = []
        for p in self._pillars:
            p.age_ms += dt_ms
            if p.age_ms < p.life_ms:
                alive_pillars.append(p)
                frac = p.age_ms / p.life_ms
                fade = max(0, int(200 * (1.0 - frac)))
                # Central vertical pillar of brand color
                pillar_h = int(120 * (1.0 - frac * 0.4))
                pillar_surf = pygame.Surface((16, pillar_h), pygame.SRCALPHA)
                for row in range(pillar_h):
                    row_frac = row / max(1, pillar_h)
                    a = int(fade * (1.0 - row_frac))
                    pillar_surf.fill((*p.color, a), (0, row, 16, 1))
                surf.blit(pillar_surf, (int(p.x) - 8, int(p.y) - pillar_h))
                # Expanding base ring at feet
                ring_r = int(12 + 28 * frac)
                if ring_r > 2:
                    ring_d = ring_r * 2 + 8
                    ring_surf = pygame.Surface((ring_d, ring_d), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf, (*p.color, max(0, fade // 2)),
                                       (ring_r + 4, ring_r + 4), ring_r, 2)
                    surf.blit(ring_surf, (int(p.x) - ring_r - 4,
                                         int(p.y) - ring_r - 4))
        self._pillars = alive_pillars

        # ── Aura starbursts ───────────────────────────────────────────────────
        alive_sb: List[_AuraStarburst] = []
        for sb in self._starbursts:
            sb.age_ms += dt_ms
            if sb.age_ms < sb.life_ms:
                alive_sb.append(sb)
                frac = sb.age_ms / sb.life_ms
                fade = max(0, int(220 * (1.0 - frac)))
                # 8-point starburst lines expanding outward
                ray_len = int(8 + 50 * frac)
                for i in range(8):
                    ang = (math.tau * i) / 8
                    ex = int(sb.x + math.cos(ang) * ray_len)
                    ey = int(sb.y + math.sin(ang) * ray_len)
                    ray_surf = pygame.Surface(
                        (abs(ex - int(sb.x)) + 4, abs(ey - int(sb.y)) + 4),
                        pygame.SRCALPHA)
                    # Draw on main surf with color+alpha line via SRCALPHA surface
                    line_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                    pygame.draw.line(line_surf, (*sb.color, fade),
                                     (int(sb.x), int(sb.y)), (ex, ey), 3)
                    surf.blit(line_surf, (0, 0))
                # Expanding alpha ring
                ring_r = int(6 + 60 * frac)
                ring_surf = pygame.Surface((ring_r * 2 + 8, ring_r * 2 + 8),
                                           pygame.SRCALPHA)
                pygame.draw.circle(ring_surf, (*sb.color, max(0, fade // 2)),
                                   (ring_r + 4, ring_r + 4), ring_r, 3)
                surf.blit(ring_surf, (int(sb.x) - ring_r - 4,
                                      int(sb.y) - ring_r - 4))
        self._starbursts = alive_sb

        # ── Beam FX ───────────────────────────────────────────────────────────
        alive_beams: List[_BeamFX] = []
        for bm in self._beams:
            bm.age_ms += dt_ms
            if bm.age_ms < bm.life_ms:
                alive_beams.append(bm)
                frac = bm.age_ms / bm.life_ms
                width = max(2, int(22 * (1.0 - frac) + 4))
                fade = max(0, int(230 * (1.0 - frac)))
                bm_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                pygame.draw.line(bm_surf, (*bm.color, fade),
                                 (int(bm.x1), int(bm.y)),
                                 (int(bm.x2), int(bm.y)), width)
                # White-hot core
                pygame.draw.line(bm_surf, (255, 255, 255, max(0, fade - 40)),
                                 (int(bm.x1), int(bm.y)),
                                 (int(bm.x2), int(bm.y)),
                                 max(2, width // 3))
                surf.blit(bm_surf, (0, 0))
        self._beams = alive_beams

        # ── Dash afterimages ──────────────────────────────────────────────────
        alive_da: List[_DashAfterimage] = []
        for da in self._dash_afterimages:
            da.age_ms += dt_ms
            if da.age_ms < da.life_ms:
                alive_da.append(da)
                frac = da.age_ms / da.life_ms
                # Three ghost torso lines at 25%, 50%, 75% along the path
                for i, (pos_frac, base_alpha) in enumerate(
                        ((0.25, 120), (0.50, 70), (0.75, 30))):
                    gx = da.sx + (da.ex - da.sx) * pos_frac
                    gy = da.sy + (da.ey - da.sy) * pos_frac
                    alpha = max(0, int(base_alpha * (1.0 - frac)))
                    ghost = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                    # Torso line (simplified ghost)
                    torso_top = (int(gx), int(gy) - 110)
                    torso_bot = (int(gx), int(gy) - 20)
                    pygame.draw.line(ghost, (*da.color, alpha),
                                     torso_top, torso_bot, 5)
                    # Arms cross stroke
                    pygame.draw.line(ghost, (*da.color, alpha),
                                     (int(gx) - 15, int(gy) - 75),
                                     (int(gx) + 15, int(gy) - 75), 4)
                    surf.blit(ghost, (0, 0))
        self._dash_afterimages = alive_da

        # ── Hit-confirm rings ─────────────────────────────────────────────────
        alive_rings: List[_HitRing] = []
        for hr in self._hit_rings:
            hr.age_ms += dt_ms
            if hr.age_ms < hr.life_ms:
                alive_rings.append(hr)
                frac = hr.age_ms / hr.life_ms
                radius = int(hr.min_r + (hr.max_r - hr.min_r) * frac)
                alpha = max(0, int(220 * (1.0 - frac)))
                if radius > 0 and alpha > 0:
                    ring_d = radius * 2 + 8
                    ring_surf = pygame.Surface((ring_d, ring_d), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf, (*hr.color, alpha),
                                       (radius + 4, radius + 4), radius, 3)
                    surf.blit(ring_surf,
                               (int(hr.x) - radius - 4, int(hr.y) - radius - 4))
        self._hit_rings = alive_rings

        # Update and draw floating text
        alive_texts: List[_FloatingText] = []
        for t in self._texts:
            t.age_ms += dt_ms
            if t.age_ms < TEXT_LIFETIME_MS:
                alive_texts.append(t)
                frac = t.age_ms / TEXT_LIFETIME_MS
                y_offset = int(TEXT_RISE_PX * frac)
                fade = max(0, 255 - int(255 * frac))
                try:
                    font = pygame.font.SysFont(None, t.font_size)
                    rendered = font.render(t.text, True, t.color)
                    rendered.set_alpha(fade)
                    surf.blit(rendered, (t.x - rendered.get_width() // 2,
                                         t.y - y_offset - rendered.get_height()))
                except Exception:
                    pass  # graceful no-op if font unavailable
        self._texts = alive_texts

        # Draw screen flash overlay (on top of everything)
        if self._flash_alpha > 0:
            try:
                overlay = pygame.Surface(surf.get_size(), flags=pygame.SRCALPHA)
                overlay.fill((*self._flash_color, self._flash_alpha))
                surf.blit(overlay, (0, 0))
            except Exception:
                pass
            self._flash_alpha = max(0, self._flash_alpha - FLASH_DECAY_PER_FRAME)
