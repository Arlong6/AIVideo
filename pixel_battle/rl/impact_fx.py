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
CHARGE_ORB_MS = 150         # matches ATTACK_WINDUP_MS — orb fills the full windup
FLASH_STREAK_MS = 250       # ghost trail left by a teleport

ULTIMATE_FONT_SIZE = 32

# ── Epic ultimate VFX constants ───────────────────────────────────────────────
SKILL_BANNER_MS = 600         # total lifetime for skill-name banner
SKILL_BANNER_FONT_SIZE = 48   # big font for the banner
SKILL_BANNER_FADE_IN_MS = 100
SKILL_BANNER_HOLD_MS = 350
SKILL_BANNER_FADE_OUT_MS = 150
SKILL_BANNER_RISE_PX = 10     # slight upward drift over lifetime

ULTIMATE_BEAM_MS = 600        # wide-beam + glow band lifetime
ULTIMATE_SLAM_MS = 450        # sword descent + shockwave lifetime
ULTIMATE_SLAM_DESCEND_MS = 150  # sword falls in first 150ms


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
class _ChargeOrb:
    """Expanding glow ball at the caster's hand during cd/special/ultimate windup.

    scale=1.0 → radius 2→12 px; scale=2.0 (ultimate) → 4→24 px.
    On expiry (age_ms >= life_ms) spawns 12 radial sparks automatically.
    """
    x: float
    y: float
    color: Tuple[int, int, int]
    scale: float = 1.0
    age_ms: int = 0
    life_ms: int = CHARGE_ORB_MS
    exploded: bool = False


@dataclass
class _FlashStreak:
    """Ghost figures + a streak line left by a Flash teleport.

    n_ghost positions are evenly spaced between from_x and to_x.  Each ghost
    is a minimal torso silhouette drawn at decreasing alpha (heaviest near
    from_x, lightest near to_x).  A single horizontal streak line connects
    from_x to to_x at hip height for extra emphasis.

    `ghost_pts` is a list of (gx, gy) world positions for the ghost centroids.
    `ghost_base_alphas` is the alpha for each ghost at age 0 (decays to 0).
    """
    from_x: float
    to_x: float
    hip_y: float
    color: Tuple[int, int, int]
    ghost_pts: list          # [(gx, gy), ...]
    ghost_base_alphas: list  # [alpha_0, alpha_1, ...]
    age_ms: int = 0
    life_ms: int = FLASH_STREAK_MS


@dataclass
class _SkillBanner:
    """Giant centered skill-name banner during ultimate cast.

    Fades in over SKILL_BANNER_FADE_IN_MS, holds, fades out.
    Drifts slightly upward over its lifetime.
    """
    text: str
    color: Tuple[int, int, int]
    screen_cx: int   # center x on screen (surf width // 2)
    screen_cy: int   # center y (~30% from top of surf height)
    age_ms: int = 0
    life_ms: int = SKILL_BANNER_MS


@dataclass
class _UltimateBeam:
    """Wide horizontal beam band + glow column + lens-flare rays for beam ultimates."""
    x1: float       # caster hand x
    x2: float       # target x
    y: float        # beam height
    color: Tuple[int, int, int]
    surf_w: int     # surface width (for full-span glow)
    surf_h: int     # surface height
    age_ms: int = 0
    life_ms: int = ULTIMATE_BEAM_MS


@dataclass
class _UltimateSlam:
    """Descending sword silhouette + impact shockwave for slam/dash ultimates."""
    impact_x: float
    impact_y: float
    color: Tuple[int, int, int]
    surf_h: int     # surface height so sword can start from top
    age_ms: int = 0
    life_ms: int = ULTIMATE_SLAM_MS
    impact_spawned: bool = False   # radial debris / shockwave fires once


@dataclass
class _SpeedLine:
    """Single radial speed line radiating from a hit point."""
    x: float
    y: float
    angle_deg: float
    color: Tuple[int, int, int]
    age_ms: int = 0
    life_ms: int = 120
    length: int = 60


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
        self._charge_orbs: List[_ChargeOrb] = []
        self._speed_lines: List[_SpeedLine] = []
        self._streaks: List[_FlashStreak] = []
        self.camera_shake: CameraShake = CameraShake()
        # Epic ultimate VFX queues
        self._skill_banners: List[_SkillBanner] = []
        self._ultimate_beams: List[_UltimateBeam] = []
        self._ultimate_slams: List[_UltimateSlam] = []

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

    def spawn_charge_orb(self, x: float, y: float,
                          color: Tuple[int, int, int],
                          lifetime_ms: int = CHARGE_ORB_MS,
                          scale: float = 1.0) -> None:
        """Charge ball at the caster's near-hand for cd/special/ultimate windup.

        scale=1.0: basic charge ball (radius 2→12 px).
        scale=2.0: ultimate size (radius 4→24 px) + vertical particle column.
        """
        self._charge_orbs.append(
            _ChargeOrb(x=float(x), y=float(y), color=color,
                       scale=scale, life_ms=lifetime_ms))
        if scale >= 2.0:
            # Vertical column of rising particles for ultimate charge
            for _ in range(10):
                ang = random.uniform(math.pi * 1.1, math.pi * 1.9)  # upward fan
                speed = random.uniform(2.5, 5.5)
                life = random.randint(80, lifetime_ms)
                self._active.append(_Spark(
                    x=float(x) + random.uniform(-10, 10),
                    y=float(y),
                    vx=math.cos(ang) * speed * 0.3,
                    vy=-abs(speed),
                    life_ms=life,
                    color=color))

    def spawn_crit_speed_lines(self, x: int, y: int,
                                color: Tuple[int, int, int]) -> None:
        """4 radial speed lines radiating from the hit point (crit emphasis)."""
        for i in range(4):
            angle = 45.0 + i * 90.0  # 4 diagonal directions
            self._speed_lines.append(
                _SpeedLine(x=float(x), y=float(y),
                           angle_deg=angle, color=color))

    def spawn_flash_streak(self, from_x: float, to_x: float,
                            hip_y: float, color: Tuple[int, int, int],
                            n_ghosts: int = 5) -> None:
        """Flash teleport: n ghost torsos + a streak line between from_x and to_x.

        Ghosts are evenly spaced along the path.  Alpha decays from 180 (closest
        to from_x) to 30 (closest to to_x) so the trail reads left-to-right.
        Each ghost fades to 0 over FLASH_STREAK_MS ms.
        """
        if n_ghosts < 1:
            return
        pts = []
        alphas = []
        for i in range(n_ghosts):
            frac = i / max(1, n_ghosts - 1)   # 0.0 → 1.0
            gx = from_x + (to_x - from_x) * frac
            pts.append((gx, hip_y))
            # alpha: 180 near from_x → 30 near to_x
            alphas.append(int(180 - 150 * frac))
        self._streaks.append(_FlashStreak(
            from_x=from_x, to_x=to_x, hip_y=hip_y,
            color=color,
            ghost_pts=pts,
            ghost_base_alphas=alphas))

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

    # ── Epic ultimate VFX spawners ────────────────────────────────────────────

    def spawn_skill_banner(self, name: str, color: Tuple[int, int, int],
                           surf_size: Tuple[int, int] = (480, 854)) -> None:
        """Display HUGE skill-name text at screen center for ~600 ms.

        Font ~48 pt; fades in 100ms, holds 350ms, fades out 150ms.
        Slight upward drift (SKILL_BANNER_RISE_PX px over lifetime).
        """
        cx = surf_size[0] // 2
        cy = int(surf_size[1] * 0.30)
        self._skill_banners.append(_SkillBanner(
            text=name, color=color, screen_cx=cx, screen_cy=cy))

    def spawn_ultimate_beam(self, x1: float, x2: float, y: float,
                            color: Tuple[int, int, int],
                            surf_size: Tuple[int, int] = (480, 854)) -> None:
        """Massive widened beam for beam-vfx ultimates.

        Draws:
        - 60 px wide brand-color band with 6 px bright white core
        - Full-width 80 px glow column centred on y
        - 6 radial lens-flare rays from caster hand
        Alpha fades from 240→0 over 600 ms.
        """
        self._ultimate_beams.append(_UltimateBeam(
            x1=x1, x2=x2, y=y, color=color,
            surf_w=surf_size[0], surf_h=surf_size[1]))
        # Immediate: massive camera shake
        self.camera_shake.trigger(magnitude_px=8.0, duration_ms=400.0)
        # Immediate: extra sparks radiating from caster hand
        for _ in range(20):
            ang = random.uniform(-math.pi / 3, math.pi / 3)  # forward fan
            speed = random.uniform(5.0, 12.0)
            self._active.append(_Spark(
                x=float(x1), y=float(y),
                vx=math.cos(ang) * speed,
                vy=math.sin(ang) * speed,
                life_ms=random.randint(200, 450),
                color=color))

    def spawn_ultimate_slam(self, impact_x: float, impact_y: float,
                            color: Tuple[int, int, int],
                            surf_size: Tuple[int, int] = (480, 854)) -> None:
        """Descending sword silhouette for slam/dash-vfx ultimates.

        Sword (16 × 200 px) falls from top of frame to impact_y over 150 ms
        with slow-in/fast-out easing. On contact: 8 debris particles + radial
        shockwave (radius 8→80 px over 300 ms).
        """
        self._ultimate_slams.append(_UltimateSlam(
            impact_x=float(impact_x), impact_y=float(impact_y),
            color=color, surf_h=surf_size[1]))
        # Immediate camera shake for the slam
        self.camera_shake.trigger(magnitude_px=9.0, duration_ms=350.0)

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

        # ── Charge orbs ───────────────────────────────────────────────────────
        alive_orbs: List[_ChargeOrb] = []
        for orb in self._charge_orbs:
            orb.age_ms += dt_ms
            if orb.age_ms < orb.life_ms:
                alive_orbs.append(orb)
            else:
                # Explode: 12 radial sparks on the last frame
                if not orb.exploded:
                    orb.exploded = True
                    for i in range(12):
                        ang = (math.tau * i) / 12
                        speed = random.uniform(3.0, 7.0)
                        self._active.append(_Spark(
                            x=orb.x, y=orb.y,
                            vx=math.cos(ang) * speed,
                            vy=math.sin(ang) * speed,
                            life_ms=random.randint(100, 220),
                            color=orb.color))
                continue  # don't re-add to alive_orbs
            frac = orb.age_ms / max(1, orb.life_ms)
            # Radius grows 2→12 px (×scale for ultimate)
            min_r = max(1, int(2 * orb.scale))
            max_r = max(2, int(12 * orb.scale))
            radius = int(min_r + (max_r - min_r) * frac)
            if radius < 1:
                continue
            d = (radius + 4) * 2
            orb_surf = pygame.Surface((d, d), pygame.SRCALPHA)
            cx, cy = radius + 4, radius + 4
            # Outer glow: brand color, fading
            outer_alpha = int(160 * (1.0 - frac * 0.3))
            pygame.draw.circle(orb_surf, (*orb.color, outer_alpha), (cx, cy), radius)
            # Inner core: white-hot
            core_r = max(1, radius // 2)
            pygame.draw.circle(orb_surf, (255, 255, 255, min(255, outer_alpha + 60)),
                               (cx, cy), core_r)
            surf.blit(orb_surf, (int(orb.x) - radius - 4, int(orb.y) - radius - 4))
        self._charge_orbs = alive_orbs

        # ── Flash streak + ghost trail ────────────────────────────────────────
        alive_streaks: List[_FlashStreak] = []
        for fs in self._streaks:
            fs.age_ms += dt_ms
            if fs.age_ms >= fs.life_ms:
                continue
            alive_streaks.append(fs)
            frac = fs.age_ms / fs.life_ms
            fade_mult = max(0.0, 1.0 - frac)

            # Horizontal streak line from from_x to to_x at hip height (8 px wide)
            streak_alpha = int(200 * fade_mult)
            if streak_alpha > 0:
                sl_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                pygame.draw.line(
                    sl_surf,
                    (*fs.color, streak_alpha),
                    (int(fs.from_x), int(fs.hip_y)),
                    (int(fs.to_x), int(fs.hip_y)),
                    8)
                surf.blit(sl_surf, (0, 0))

            # Ghost torso silhouettes: minimal torso + arms cross at each ghost pt
            for (gx, gy), base_alpha in zip(fs.ghost_pts, fs.ghost_base_alphas):
                alpha = int(base_alpha * fade_mult)
                if alpha <= 5:
                    continue
                ghost = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                gc = (*fs.color, alpha)
                torso_top = (int(gx), int(gy) - 100)
                torso_bot = (int(gx), int(gy) - 15)
                pygame.draw.line(ghost, gc, torso_top, torso_bot, 5)
                # Arms cross stroke
                pygame.draw.line(ghost, gc,
                                 (int(gx) - 18, int(gy) - 65),
                                 (int(gx) + 18, int(gy) - 65), 4)
                # Head dot
                pygame.draw.circle(ghost, gc, (int(gx), int(gy) - 115), 8)
                surf.blit(ghost, (0, 0))
        self._streaks = alive_streaks

        # ── Speed lines (crit emphasis) ───────────────────────────────────────
        alive_sl: List[_SpeedLine] = []
        for sl in self._speed_lines:
            sl.age_ms += dt_ms
            if sl.age_ms >= sl.life_ms:
                continue
            alive_sl.append(sl)
            frac = sl.age_ms / sl.life_ms
            # Length grows fast then fades: peak at 40% lifetime
            if frac < 0.4:
                length = int(sl.length * frac / 0.4)
            else:
                length = sl.length
            alpha = max(0, int(255 * (1.0 - frac)))
            if length < 2 or alpha < 5:
                continue
            ang_r = math.radians(sl.angle_deg)
            ex = int(sl.x + math.cos(ang_r) * length)
            ey = int(sl.y + math.sin(ang_r) * length)
            sl_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            pygame.draw.line(sl_surf, (*sl.color, alpha),
                             (int(sl.x), int(sl.y)), (ex, ey), 3)
            # White-hot core line
            if length > 4:
                pygame.draw.line(sl_surf, (255, 255, 255, min(255, alpha + 40)),
                                 (int(sl.x), int(sl.y)),
                                 (int(sl.x + math.cos(ang_r) * length // 2),
                                  int(sl.y + math.sin(ang_r) * length // 2)), 2)
            surf.blit(sl_surf, (0, 0))
        self._speed_lines = alive_sl

        # ── Skill banners (ultimate cast name) ───────────────────────────────────
        alive_banners: List[_SkillBanner] = []
        for bn in self._skill_banners:
            bn.age_ms += dt_ms
            if bn.age_ms >= bn.life_ms:
                continue
            alive_banners.append(bn)
            # Compute alpha: fade-in, hold, fade-out
            age = bn.age_ms
            if age < SKILL_BANNER_FADE_IN_MS:
                alpha = int(255 * age / SKILL_BANNER_FADE_IN_MS)
            elif age < SKILL_BANNER_FADE_IN_MS + SKILL_BANNER_HOLD_MS:
                alpha = 255
            else:
                remaining = bn.life_ms - age
                alpha = max(0, int(255 * remaining / SKILL_BANNER_FADE_OUT_MS))
            if alpha < 2:
                continue
            # Upward drift
            drift_y = int(SKILL_BANNER_RISE_PX * bn.age_ms / max(1, bn.life_ms))
            try:
                font = pygame.font.SysFont(None, SKILL_BANNER_FONT_SIZE * 2)
                # Outline: draw text in dark offset for readability
                outline_col = tuple(max(0, c - 160) for c in bn.color)
                rendered = font.render(bn.text, True, bn.color)
                rendered.set_alpha(alpha)
                rx = bn.screen_cx - rendered.get_width() // 2
                ry = bn.screen_cy - drift_y - rendered.get_height() // 2
                # 4-direction outline for contrast
                outline_surf = font.render(bn.text, True, outline_col)
                outline_surf.set_alpha(min(255, alpha + 60))
                for ox, oy in ((-3, 0), (3, 0), (0, -3), (0, 3)):
                    surf.blit(outline_surf, (rx + ox, ry + oy))
                surf.blit(rendered, (rx, ry))
            except Exception:
                pass
        self._skill_banners = alive_banners

        # ── Ultimate beam (wide band + glow + lens flare) ─────────────────────
        alive_ub: List[_UltimateBeam] = []
        for ub in self._ultimate_beams:
            ub.age_ms += dt_ms
            if ub.age_ms >= ub.life_ms:
                continue
            alive_ub.append(ub)
            frac = ub.age_ms / ub.life_ms
            alpha = max(0, int(240 * (1.0 - frac)))
            if alpha < 2:
                continue
            ub_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            # 1. Full-width 80-px glow column at beam height
            glow_h = 80
            glow_top = int(ub.y) - glow_h // 2
            glow_surf = pygame.Surface((ub.surf_w, glow_h), pygame.SRCALPHA)
            for row in range(glow_h):
                # Gaussian-like alpha falloff from centre
                dist_from_center = abs(row - glow_h // 2)
                row_alpha = int(alpha * 0.5 * max(0.0, 1.0 - dist_from_center / (glow_h / 2)))
                if row_alpha > 0:
                    glow_surf.fill((*ub.color, row_alpha), (0, row, ub.surf_w, 1))
            ub_surf.blit(glow_surf, (0, max(0, glow_top)))
            # 2. Wide beam band (60 px) from x1 to x2
            bx1, bx2 = int(min(ub.x1, ub.x2)), int(max(ub.x1, ub.x2))
            beam_w = max(1, bx2 - bx1)
            beam_band = pygame.Surface((beam_w, 60), pygame.SRCALPHA)
            for row in range(60):
                dist = abs(row - 30)
                row_a = int(alpha * max(0.0, 1.0 - dist / 30))
                if row_a > 0:
                    beam_band.fill((*ub.color, row_a), (0, row, beam_w, 1))
            ub_surf.blit(beam_band, (bx1, int(ub.y) - 30))
            # 3. White-hot 6-px core
            pygame.draw.line(ub_surf, (255, 255, 255, min(255, alpha + 15)),
                             (bx1, int(ub.y)), (bx2, int(ub.y)), 6)
            surf.blit(ub_surf, (0, 0))
            # 4. Lens flare: 6 radial rays from caster hand position
            n_rays = 6
            for i in range(n_rays):
                ang = (math.tau * i) / n_rays
                ray_len = int(50 + 70 * (1.0 - frac))
                ex = int(ub.x1 + math.cos(ang) * ray_len)
                ey = int(ub.y + math.sin(ang) * ray_len)
                ray_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
                pygame.draw.line(ray_surf, (*ub.color, max(0, alpha - 40)),
                                 (int(ub.x1), int(ub.y)), (ex, ey), 3)
                # White core ray
                mid_ex = int(ub.x1 + math.cos(ang) * ray_len * 0.5)
                mid_ey = int(ub.y + math.sin(ang) * ray_len * 0.5)
                pygame.draw.line(ray_surf, (255, 255, 255, max(0, alpha - 80)),
                                 (int(ub.x1), int(ub.y)), (mid_ex, mid_ey), 2)
                surf.blit(ray_surf, (0, 0))
        self._ultimate_beams = alive_ub

        # ── Ultimate slam (descending sword + shockwave) ──────────────────────
        alive_us: List[_UltimateSlam] = []
        for us in self._ultimate_slams:
            us.age_ms += dt_ms
            if us.age_ms >= us.life_ms:
                continue
            alive_us.append(us)
            # Phase 1: sword descends (0 → ULTIMATE_SLAM_DESCEND_MS)
            if us.age_ms <= ULTIMATE_SLAM_DESCEND_MS:
                # Slow-in fast-out easing (ease-in cubic then linear)
                t_frac = us.age_ms / ULTIMATE_SLAM_DESCEND_MS
                eased = t_frac * t_frac * (3.0 - 2.0 * t_frac)  # smoothstep
                sword_start_y = 0
                sword_end_y = int(us.impact_y) - 100  # stop at chest height
                sword_y = int(sword_start_y + (sword_end_y - sword_start_y) * eased)
                # Draw sword silhouette: 16×200 white-and-brand-color rectangle
                sword_surf = pygame.Surface((16, 200), pygame.SRCALPHA)
                sword_surf.fill((*us.color, 220))
                # White core strip
                core_rect = pygame.Rect(5, 0, 6, 200)
                pygame.draw.rect(sword_surf, (255, 255, 255, 240), core_rect)
                sx = int(us.impact_x) - 8
                surf.blit(sword_surf, (sx, sword_y))
            else:
                # Phase 2: impact effects
                if not us.impact_spawned:
                    us.impact_spawned = True
                    # 8 radial debris particles
                    for i in range(8):
                        ang = (math.tau * i) / 8
                        speed = random.uniform(4.0, 9.0)
                        # Large dark-grey debris sparks
                        self._active.append(_Spark(
                            x=us.impact_x, y=us.impact_y - 100,
                            vx=math.cos(ang) * speed,
                            vy=math.sin(ang) * speed - 2.0,
                            life_ms=random.randint(200, 400),
                            color=(80, 80, 90)))
                        # Brand-color sparks too
                        self._active.append(_Spark(
                            x=us.impact_x, y=us.impact_y - 100,
                            vx=math.cos(ang) * speed * 0.7,
                            vy=math.sin(ang) * speed * 0.7,
                            life_ms=random.randint(150, 320),
                            color=us.color))
                # Phase 2 render: expanding shockwave ring
                phase2_age = us.age_ms - ULTIMATE_SLAM_DESCEND_MS
                phase2_life = us.life_ms - ULTIMATE_SLAM_DESCEND_MS
                ring_frac = phase2_age / max(1, phase2_life)
                ring_r = int(8 + (80 - 8) * ring_frac)
                ring_alpha = max(0, int(220 * (1.0 - ring_frac)))
                if ring_r > 2 and ring_alpha > 5:
                    ring_d = ring_r * 2 + 8
                    ring_surf = pygame.Surface((ring_d, ring_d), pygame.SRCALPHA)
                    pygame.draw.circle(ring_surf, (*us.color, ring_alpha),
                                       (ring_r + 4, ring_r + 4), ring_r, 4)
                    # Outer white ring
                    if ring_r > 8:
                        pygame.draw.circle(ring_surf,
                                           (255, 255, 255, ring_alpha // 2),
                                           (ring_r + 4, ring_r + 4), ring_r - 3, 2)
                    surf.blit(ring_surf, (int(us.impact_x) - ring_r - 4,
                                          int(us.impact_y) - 100 - ring_r - 4))
        self._ultimate_slams = alive_us

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
