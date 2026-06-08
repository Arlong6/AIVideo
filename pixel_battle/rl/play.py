"""Render a trained PPO fight as a complete mp4 episode.

A full episode = VS intro -> fight -> K.O. / winner card, stitched into one
video. The fight stage has the camera, HUD, impact bursts, hit-flash,
screen shake, projectiles and skill banners.
"""
from __future__ import annotations
import argparse
import math
import os
import random
from pathlib import Path
from typing import Optional

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.engine.character import Character  # noqa: E402
from pixel_battle.rl.stick_renderer import (  # noqa: E402
    draw_stick_figure,
    draw_effect_indicators,
    ProjectileLayer,
    spawn_impact_burst,
    spawn_landing_dust,
    spawn_flash_puff,
)
from pixel_battle.video.recorder import FrameRecorder  # noqa: E402
from pixel_battle.video.audio_mixer import AudioMixer  # noqa: E402
from pixel_battle.video.compose import (  # noqa: E402
    _load_wav, _loop_to_length, _load_sfx_samples_or_none,
    mux_audio_video, BGM_DIR,
)
from pixel_battle.engine.physics import GROUND_Y, ARENA_LEFT, ARENA_RIGHT  # noqa: E402


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
RENDER_FPS = 60           # output frame rate — match engine; 120fps mp4s confuse QuickTime into slow playback
RENDER_MS = 1000.0 / RENDER_FPS   # 16.667 ms per render frame
ENGINE_HZ = 60            # engine tick rate (unchanged)
ENGINE_MS = 1000.0 / ENGINE_HZ    # 16.667 ms per engine tick
HIT_FLASH = (255, 255, 255)   # color a fighter flashes to when struck
# True arcane casters — get a magic circle + rune aura on their casts so they
# read as spellcasters (the deliberate opposite of the de-magified assassins).
_MAGE_IDS = frozenset({"lux", "pyre"})
# Per-shooter projectile visual (marksmen each fire something distinct).
_PROJECTILE_KIND = {
    "lux": "orb", "pyre": "fire", "ashe": "ice", "jinx": "rocket",
    "deadeye": "bullet", "quarrel": "bolt", "venom": "kunai", "outlaw": "bullet",
}
BG = (18, 22, 40)
# GROUND_Y is imported from the physics engine — the renderer MUST use the
# same feet-landing line the simulation uses, or the camera and floor will
# be offset from where the fighters actually stand.

# Camera — zoom + horizontal follow so fighters fill the vertical frame
# instead of sitting tiny in the bottom strip. The world is drawn at native
# size, then a sub-region is cropped + upscaled to the output resolution.
CAM_ZOOM = 1.0             # base zoom; the live camera zoom is now DYNAMIC (see below)
CAM_VIEW_W = int(WIDTH / CAM_ZOOM)            # 480 — horizontal world span shown
CAM_VIEW_H = int(HEIGHT / CAM_ZOOM)           # 854 — vertical world span shown
CAM_VIEW_Y = GROUND_Y - int(CAM_VIEW_H * 0.82)  # frame the floor ~82% down
CAM_FOLLOW = 0.12                              # lerp factor for x tracking
# Dynamic framing: zoom to FIT both fighters. Close quarters -> tighter crop
# (melee reads big and punchy); far apart -> pull back to reveal the whole arena
# (kiting/separation reads as real space). Fixes the "everything clumped in the
# middle" look of a static wide shot.
CAM_MIN_VIEW_W = 465       # near-never zoom in (480/465 = 1.03×) — fighters stay small, arena stays wide
CAM_FRAME_MARGIN = 220     # more breathing room beyond each fighter ⇒ more visible separation
CAM_ZOOM_LERP = 0.045      # ease the dynamic zoom so it glides, never snaps

# ── Ultimate knockback ───────────────────────────────────────────────────────
# When the ultimate connects, the renderer blasts the DEFENDER away from the
# caster on a ballistic arc — into the arena wall, then gravity drops them. The
# engine freezes on KO, so this launch is a purely renderer-side draw-position
# override during the cinematic aftermath (no engine change, no regression risk).
ULT_LAUNCH_VX = 13.0       # initial horizontal blast speed (px / 60fps frame)
ULT_LAUNCH_VY = 17.0       # initial upward pop
ULT_LAUNCH_GRAVITY = 1.15  # downward accel per frame
ULT_LAUNCH_WALL_BOUNCE = 0.38   # velocity retained (reversed) on wall impact
ULT_LAUNCH_EDGE_PAD = 26   # keep the body this far off the very edge

SHAKE_FRAMES = 8           # frames a crit screen-shake lasts
SHAKE_MAG = 14             # peak shake offset, world px
MOTION_BLUR_ALPHA = 89    # ~35 % of 255 — cinematic blur strength


def camera_shake_offset(frames_remaining: int) -> tuple:
    """Decaying random camera offset for a crit screen-shake.

    Returns (0, 0) when not shaking; otherwise a random (dx, dy) whose
    magnitude decays linearly as `frames_remaining` counts down.
    """
    if frames_remaining <= 0:
        return (0, 0)
    mag = int(SHAKE_MAG * (frames_remaining / SHAKE_FRAMES))
    return (random.randint(-mag, mag), random.randint(-mag, mag))


INTRO_FRAMES = int(1.8 * RENDER_FPS)   # 216 frames at 120fps — same 1.8s duration
RESULT_FRAMES = int(3.0 * RENDER_FPS)  # 360 frames at 120fps — same 3.0s duration

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CKPT = ROOT / "data" / "rl_checkpoints" / "ppo_final.zip"
OUT_DIR = ROOT / "pixel_battle" / "output" / "rl_play"


# ── small math helpers ────────────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _char_color(char) -> tuple:
    """The render color for a character (its JSON `color`, as a tuple)."""
    return tuple(char.color)


# ── HUD font cache ────────────────────────────────────────────────────────────
_HUD_FONT_CACHE: dict = {}


def _get_hud_font(size: int = 14) -> pygame.font.Font:
    """Lazily create/cache a bold arial font of the given size."""
    if not pygame.font.get_init():
        pygame.font.init()
    f = _HUD_FONT_CACHE.get(size)
    if f is None:
        f = pygame.font.SysFont("arial", size, bold=True)
        _HUD_FONT_CACHE[size] = f
    return f


# ── Background / arena themes ─────────────────────────────────────────────────
# Per-script selectable arena. set_arena() is called from the renderer entry
# (play_scripted) before a fight; the batch rotates themes so the reel varies.
_ARENA_THEMES = ("dusk", "dojo", "ruins")
_ARENA_THEME = "ruins"


def set_arena(theme: str) -> None:
    """Select the arena backdrop for subsequent renders."""
    global _ARENA_THEME
    if theme in _ARENA_THEMES:
        _ARENA_THEME = theme


def _vgrad(surf, top, bottom, y0=0, y1=None) -> None:
    """Vertical gradient band from `top` to `bottom` colour over [y0, y1)."""
    if y1 is None:
        y1 = GROUND_Y
    span = max(1, y1 - y0)
    for i in range(y0, y1, 4):
        t = (i - y0) / span
        pygame.draw.rect(surf, (int(top[0] + (bottom[0] - top[0]) * t),
                                int(top[1] + (bottom[1] - top[1]) * t),
                                int(top[2] + (bottom[2] - top[2]) * t)),
                         (0, i, WIDTH, 4))


def _soft_glow(surf, cx, cy, rings) -> None:
    """Additive-ish soft glow: concentric translucent circles."""
    rmax = max(r for r, _ in rings)
    g = pygame.Surface((rmax * 2 + 4, rmax * 2 + 4), pygame.SRCALPHA)
    for r, (col) in rings:
        pygame.draw.circle(g, col, (rmax + 2, rmax + 2), r)
    surf.blit(g, (cx - rmax - 2, cy - rmax - 2))


def _back_dusk(surf, frame: int) -> None:
    """Neon dusk colosseum: indigo→magenta sky, tiered crowd, embers."""
    _vgrad(surf, (26, 16, 46), (74, 28, 66))
    for ry, col in ((0.30, (40, 28, 60)), (0.45, (52, 32, 70)), (0.60, (66, 40, 84))):
        y = int(GROUND_Y * ry)
        for x in range(8, WIDTH - 8, 26):
            pygame.draw.rect(surf, col, (x, y, 16, 9))
    for i in range(26):                                   # crowd twinkle
        if (frame + i * 7) % 130 < 26:
            x = (i * 53) % WIDTH
            y = int(GROUND_Y * 0.30) + (i * 37) % int(GROUND_Y * 0.34)
            pygame.draw.circle(surf, (255, 212, 150), (x, y), 1)
    for px in (14, WIDTH - 26):                           # side pillars
        pygame.draw.rect(surf, (28, 18, 38), (px, 0, 12, GROUND_Y))
    for i in range(20):                                   # rising embers
        ex = int((i * 61 + 9 * math.sin((frame + i * 20) / 40.0)) % WIDTH)
        ey = GROUND_Y - ((frame + i * 43) % GROUND_Y)
        a = max(0, 190 - int(170 * (GROUND_Y - ey) / GROUND_Y))
        s = pygame.Surface((3, 3), pygame.SRCALPHA)
        pygame.draw.circle(s, (255, 150, 60, a), (1, 1), 1)
        surf.blit(s, (ex, ey))


def _back_dojo(surf, frame: int) -> None:
    """Torch-lit dojo: warm shoji grid, hanging lanterns, falling petals."""
    _vgrad(surf, (42, 28, 18), (20, 13, 9))
    grid = (74, 56, 38)
    for x in range(0, WIDTH + 1, 48):
        pygame.draw.line(surf, grid, (x, 0), (x, GROUND_Y), 2)
    for y in range(0, GROUND_Y, 60):
        pygame.draw.line(surf, grid, (0, y), (WIDTH, y), 2)
    for lx in (58, WIDTH - 58):                           # lanterns
        _soft_glow(surf, lx, 92, [(32, (255, 170, 70, 45)),
                                  (20, (255, 185, 90, 80)), (11, (255, 210, 120, 140))])
        pygame.draw.circle(surf, (255, 200, 110), (lx, 92), 5)
    for i in range(18):                                   # cherry petals
        px = int((i * 57 + 14 * math.sin((frame + i * 30) / 50.0)) % WIDTH)
        py = (frame + i * 47) % GROUND_Y
        s = pygame.Surface((4, 3), pygame.SRCALPHA)
        pygame.draw.ellipse(s, (255, 182, 200, 205), (0, 0, 4, 3))
        surf.blit(s, (px, py))


def _back_ruins(surf, frame: int) -> None:
    """Moonlit ruins in rain: broken pillars, moon glow, animated rain."""
    _vgrad(surf, (16, 20, 38), (32, 38, 62))
    _soft_glow(surf, WIDTH - 70, 80, [(50, (180, 200, 235, 26)),
                                      (32, (190, 208, 238, 44)), (18, (210, 225, 245, 90))])
    pygame.draw.circle(surf, (212, 226, 246), (WIDTH - 70, 80), 15)
    for px, h in ((40, 0.50), (150, 0.34), (WIDTH - 66, 0.42), (WIDTH - 158, 0.30)):
        top = int(GROUND_Y * (1 - h))
        pygame.draw.rect(surf, (24, 28, 46), (px, top, 20, GROUND_Y - top))
    for i in range(64):                                   # rain
        rx = (i * 37 + frame * 6) % (WIDTH + 80) - 40
        ry = (i * 53 + frame * 14) % GROUND_Y
        pygame.draw.line(surf, (120, 140, 190), (rx, ry), (rx - 6, ry + 14), 1)


def _draw_back_wall(surf: pygame.Surface, frame: int = 0) -> None:
    """Themed backdrop above the floor (gradient + parallax + particles)."""
    if _ARENA_THEME == "dusk":
        _back_dusk(surf, frame)
    elif _ARENA_THEME == "dojo":
        _back_dojo(surf, frame)
    else:
        _back_ruins(surf, frame)


def _draw_floor(surf: pygame.Surface, frame: int = 0) -> None:
    """Themed ground band matching the active arena."""
    if _ARENA_THEME == "dusk":
        pygame.draw.rect(surf, (30, 18, 40), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.line(surf, (255, 90, 180), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
        pygame.draw.line(surf, (80, 220, 255), (0, GROUND_Y + 4), (WIDTH, GROUND_Y + 4), 1)
        for x in range(0, WIDTH, 60):
            pygame.draw.line(surf, (62, 30, 72), (x, GROUND_Y + 14), (x + 30, GROUND_Y + 14), 1)
    elif _ARENA_THEME == "dojo":
        pygame.draw.rect(surf, (58, 40, 26), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.line(surf, (120, 90, 55), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
        for y in range(GROUND_Y + 12, HEIGHT, 16):
            pygame.draw.line(surf, (44, 30, 20), (0, y), (WIDTH, y), 1)
        for x in range(0, WIDTH, 80):
            pygame.draw.line(surf, (44, 30, 20), (x, GROUND_Y), (x, HEIGHT), 1)
    else:
        pygame.draw.rect(surf, (28, 34, 56), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
        pygame.draw.line(surf, (90, 110, 170), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
        for x in range(0, WIDTH, 40):
            pygame.draw.line(surf, (50, 60, 95), (x, GROUND_Y + 8), (x + 20, GROUND_Y + 8), 1)
        for x in range(20, WIDTH, 40):
            pygame.draw.line(surf, (50, 60, 95), (x, GROUND_Y + 22), (x + 20, GROUND_Y + 22), 1)


def _draw_shadow(surf: pygame.Surface, char) -> None:
    """Translucent black ellipse under the character; shrinks when airborne."""
    ground = GROUND_Y
    air_height = max(0, ground - int(char.pos_y))
    scale = max(0.35, 1.0 - air_height / 250.0)
    w = int(54 * scale)
    h = int(9 * scale)
    if w < 6 or h < 2:
        return
    shadow = pygame.Surface((w * 2, h * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 110), (0, 0, w * 2, h * 2))
    surf.blit(shadow, (int(char.pos_x) - w, ground - h))


def _draw_shockwave(surf: pygame.Surface, x: int, y: int,
                     color: tuple, age: int, life: int, max_radius: int) -> None:
    """An expanding, fading ring — the screen-filling punch of a big hit."""
    t = age / max(1, life)
    if t >= 1.0:
        return
    radius = int(24 + (max_radius - 24) * _ease_out(t))
    alpha = int(210 * (1.0 - t))
    if alpha <= 0 or radius < 2:
        return
    w = max(2, int(12 * (1.0 - t)))
    pad = w + 4
    ring = pygame.Surface((radius * 2 + pad * 2, radius * 2 + pad * 2),
                          pygame.SRCALPHA)
    pygame.draw.circle(ring, (*color, alpha),
                       (radius + pad, radius + pad), radius, w)
    surf.blit(ring, (x - radius - pad, y - radius - pad))


def _draw_beam(surf: pygame.Surface, sx: int, sy: int, ex: int, ey: int,
                color: tuple, age: int, life: int) -> None:
    """A thick bright beam from (sx,sy) to (ex,ey) with a white-hot core."""
    t = age / max(1, life)
    if t >= 1.0:
        return
    w = int(30 * (1.0 - t) + 4)
    pygame.draw.line(surf, color, (sx, sy), (ex, ey), w)
    pygame.draw.line(surf, (255, 255, 255), (sx, sy), (ex, ey), max(2, w // 3))


def _draw_spin(surf: pygame.Surface, cx: int, cy: int, color: tuple,
                age: int, life: int) -> None:
    """Whirling BLADE STORM around the caster — Garen's Judgment.

    A bright additive glow disc, 8 white-cored sweeping blades with motion-blur
    echoes, and two luminous rings — reads as a real spinning ultimate, not a flick.
    """
    t = age / max(1, life)
    if t >= 1.0:
        return
    fade = 1.0 - t
    radius = int(54 + 40 * t)
    # Two sharp crescent blade-arcs sweeping opposite sides — whirling STEEL, not
    # a glowing magic nova. Each arc has a white leading edge over a colour body;
    # no additive rings (those are what made a spin read as a spell).
    spin = age * 0.9
    for k in range(2):
        base = spin + k * math.pi
        body, edge = [], []
        for j in range(9):
            a = base + (j / 8.0) * 1.6           # ~92° crescent sweep
            body.append((cx + math.cos(a) * radius, cy + math.sin(a) * radius))
            edge.append((cx + math.cos(a) * radius * 0.9,
                         cy + math.sin(a) * radius * 0.9))
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.lines(layer, (*color, int(165 * fade)), False,
                          [(int(x), int(y)) for x, y in body], 5)
        pygame.draw.lines(layer, (255, 255, 255, int(235 * fade)), False,
                          [(int(x), int(y)) for x, y in edge], 2)
        surf.blit(layer, (0, 0))


def _draw_aura(surf: pygame.Surface, cx: int, cy: int, color: tuple,
                age: int, life: int) -> None:
    """A POWER-SURGE buff aura on the caster — Garen's Courage.

    Bright additive body glow + multiple expanding rings + rising energy motes,
    so it clearly reads as "powering up", not a faint flicker.
    """
    t = age / max(1, life)
    if t >= 1.0:
        return
    fade = 1.0 - t
    # Additive body glow that pulses (sine) around the caster
    pulse = 0.6 + 0.4 * math.sin(age * 0.5)
    gr = int(58 * (0.8 + 0.4 * t))
    gd = gr * 2 + 8
    glow = pygame.Surface((gd, gd), pygame.SRCALPHA)
    for rr, ga in ((gr, 55), (int(gr * 0.6), 85), (int(gr * 0.3), 120)):
        pygame.draw.circle(glow, (*color, int(ga * fade * pulse)),
                           (gd // 2, gd // 2), rr)
    surf.blit(glow, (cx - gd // 2, cy - gd // 2), special_flags=pygame.BLEND_RGB_ADD)
    # Expanding bright rings
    for k in range(4):
        rt = (t * 1.5 + k * 0.25) % 1.0
        radius = int(20 + 78 * rt)
        alpha = int(190 * (1.0 - rt) * fade)
        if alpha <= 0:
            continue
        ring = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*color, alpha), (radius + 4, radius + 4), radius, 4)
        if radius > 14:
            pygame.draw.circle(ring, (255, 255, 255, alpha // 2),
                               (radius + 4, radius + 4), radius - 3, 2)
        surf.blit(ring, (cx - radius - 4, cy - radius - 4))
    # Rising energy motes (additive) — sell the "charging up" feel
    for i in range(7):
        ph = (age * 0.06 + i * 0.9)
        rise = (ph % 1.0)
        mx = cx + int(math.cos(i * 1.7) * 34 * (1.0 - rise))
        my = cy + 20 - int(rise * 96)
        ma = int(200 * (1.0 - rise) * fade)
        if ma <= 0:
            continue
        mote = pygame.Surface((10, 10), pygame.SRCALPHA)
        pygame.draw.circle(mote, (*color, ma), (5, 5), 4)
        pygame.draw.circle(mote, (255, 255, 255, ma), (5, 5), 2)
        surf.blit(mote, (mx - 5, my - 5), special_flags=pygame.BLEND_RGB_ADD)


def _draw_ult_sig(surf, aid, cx, ty, age, life, color, ground_y):
    """Per-champion ULTIMATE signature, drawn over `life` frames at the target.
    Each champion gets a distinct flourish (a falling sword vs a meteor vs ice
    spikes vs a bullet barrage…) so ults stop reading as one generic explosion."""
    t = age / max(1, life)
    if t >= 1.0:
        return
    fade = 1.0 - t
    iy = ty - 90                      # impact height (chest)
    W = (255, 255, 255)

    def add_circle(x, y, r, col, a):
        s = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col, a), (r + 2, r + 2), r)
        surf.blit(s, (int(x) - r - 2, int(y) - r - 2), special_flags=pygame.BLEND_RGB_ADD)

    def add_ring(x, y, r, col, a, w=5):
        s = pygame.Surface((r * 2 + 6, r * 2 + 6), pygame.SRCALPHA)
        pygame.draw.circle(s, (*col, a), (r + 3, r + 3), r, w)
        surf.blit(s, (int(x) - r - 3, int(y) - r - 3), special_flags=pygame.BLEND_RGB_ADD)

    def descend(top=330, land=0.45):
        p = min(1.0, t / land)
        return iy - int(top * (1 - p)), p

    # ── descending weapon strikes ────────────────────────────────────────────
    if aid == "garen":                # VANGUARD — a giant blade of light falls
        y, p = descend(420)
        bl = 130
        pts = [(cx, y + bl), (cx - 13, y), (cx + 13, y)]
        pygame.draw.polygon(surf, (205, 228, 255), [(int(a), int(b)) for a, b in pts])
        pygame.draw.polygon(surf, W, [(int(a), int(b)) for a, b in pts], 2)
        pygame.draw.line(surf, (185, 205, 255), (cx - 28, y + 8), (cx + 28, y + 8), 6)
        if p >= 1.0:
            add_ring(cx, iy, int(40 + 260 * (t - 0.45)), (200, 225, 255), int(170 * fade), 6)
    elif aid == "pantheon":           # SKYLANCE — a spear comet streaks down at an angle
        p = min(1.0, t / 0.45)
        sx = cx - int(190 * (1 - p)); sy = iy - int(340 * (1 - p))
        for k in range(7):
            f = k / 7.0
            add_circle(sx - 58 * f, sy - 108 * f, max(2, 6 - k // 2), (255, 175, 80), int(130 * (1 - f) * fade + 40))
        pygame.draw.line(surf, (255, 205, 120), (sx - 44, sy - 78), (sx, sy), 5)
        pygame.draw.polygon(surf, W, [(sx, sy), (sx - 11, sy - 17), (sx + 7, sy - 13)])
        if p >= 1.0:
            add_ring(cx, iy, int(30 + 240 * (t - 0.45)), (255, 190, 90), int(150 * fade), 5)
    elif aid == "wrecker":            # WRECKER — a giant spiked ball drops & smashes
        y, p = descend(380)
        r = 38
        for a in range(0, 360, 40):
            sp = (cx + int(math.cos(math.radians(a)) * (r + 11)),
                  y + int(math.sin(math.radians(a)) * (r + 11)))
            pygame.draw.line(surf, (120, 110, 110), (cx, y), sp, 3)
        pygame.draw.circle(surf, (152, 142, 142), (cx, y), r)
        pygame.draw.circle(surf, (80, 75, 75), (cx, y), r, 3)
        if p >= 1.0:
            for s in (-1, 1):       # debris kicked sideways
                add_circle(cx + s * int(60 * (t - 0.45) * 3), iy + 30, 5, (150, 140, 130), int(150 * fade))
            add_ring(cx, ground_y - 6, int(30 + 230 * (t - 0.45)), (210, 200, 190), int(150 * fade), 8)
    elif aid == "pyre":               # PYRE — a flaming meteor falls + fire pool
        p = min(1.0, t / 0.45)
        my = iy - int(340 * (1 - p))
        for k in range(8):
            f = k / 8.0
            add_circle(cx + int(6 * math.sin(age * 0.5 + k)), my - 80 * f - 18,
                       max(2, 9 - k), (255, 120 - k * 8, 30), int(150 * (1 - f) * fade + 30))
        add_circle(cx, my, 16, (255, 150, 50), 220)
        add_circle(cx, my, 9, (255, 230, 150), 240)
        if p >= 1.0:                  # fire pool spreading on the ground
            fw = int(40 + 230 * (t - 0.45))
            for i in range(7):
                fx = cx - fw + int(2 * fw * i / 6)
                add_circle(fx, ground_y - 8, int(10 * fade) + 4, (255, 110, 30), int(160 * fade))

    # ── elemental / ranged ───────────────────────────────────────────────────
    elif aid == "lux":                # LUMEN — a fan of radiant prism rays
        for k, col in enumerate(((255, 120, 120), (255, 230, 120), (140, 255, 160),
                                 (130, 190, 255), (210, 150, 255))):
            ang = -90 + (k - 2) * 22
            ln = int(55 + 430 * min(1.0, t / 0.4)) * fade if t > 0.4 else int(55 + 430 * (t / 0.4))
            ex = cx + int(math.cos(math.radians(ang)) * ln)
            ey = iy + int(math.sin(math.radians(ang)) * ln)
            lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            pygame.draw.line(lay, (*col, int(180 * fade)), (cx, iy), (ex, ey), 6)
            pygame.draw.line(lay, (*W, int(200 * fade)), (cx, iy), (ex, ey), 2)
            surf.blit(lay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        add_circle(cx, iy, int(16 + 20 * fade), (255, 255, 230), int(220 * fade))
    elif aid == "jinx":               # WILDFIRE — a huge rocket fireball blooms
        r = int(28 + 210 * t)
        add_circle(cx, iy, r, (255, 90, 40), int(150 * fade))
        add_circle(cx, iy, int(r * 0.6), (255, 170, 60), int(180 * fade))
        add_circle(cx, iy, int(r * 0.3), (255, 240, 160), int(220 * fade))
        for k in range(10):
            a = k * 36 + age * 4
            rr = r + int(18 * math.sin(age * 0.3 + k))
            add_circle(cx + int(math.cos(math.radians(a)) * rr),
                       iy + int(math.sin(math.radians(a)) * rr), 4, (90, 90, 90), int(120 * fade))
    elif aid == "ashe":               # FROSTBOW — ice spikes erupt from the ground
        n = 11
        for i in range(n):
            sx = cx - 190 + int(380 * i / (n - 1))
            gh = int((115 + 75 * math.sin(i * 1.7)) * min(1.0, t / 0.4))
            tipy = ground_y - gh
            pygame.draw.polygon(surf, (180, 235, 255),
                                [(sx - 12, ground_y), (sx + 12, ground_y), (sx, tipy)])
            pygame.draw.polygon(surf, W, [(sx - 12, ground_y), (sx + 12, ground_y), (sx, tipy)], 2)
        add_circle(cx, iy, int(44 * fade) + 8, (200, 240, 255), int(150 * fade))
    elif aid == "quarrel":            # QUARREL — one massive piercing bolt + crack
        p = min(1.0, t / 0.4)
        bx = cx - int(320 * (1 - p))
        pygame.draw.line(surf, (150, 185, 70), (bx - 60, iy), (bx, iy), 7)
        pygame.draw.polygon(surf, (235, 235, 235), [(bx + 18, iy), (bx, iy - 9), (bx, iy + 9)])
        if p >= 1.0:
            add_ring(cx, iy, int(24 + 220 * (t - 0.4)), (180, 210, 90), int(150 * fade), 5)
    elif aid in ("deadeye", "outlaw"):  # gunners — a BULLET barrage / high-noon shot
        n = 6 if aid == "deadeye" else 2
        ax = cx - 260
        for k in range(n):
            p = min(1.0, (t - k * 0.05) / 0.3)
            if p <= 0:
                continue
            spread = (k - n / 2) * 16
            bx = ax + int((cx - ax + 30) * p)
            lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            pygame.draw.line(lay, (*color, 150), (bx - 26, iy + spread), (bx, iy + spread), 2)
            surf.blit(lay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
            add_circle(bx, iy + spread, 3, (255, 255, 220), 220)
        if t < 0.3:                   # muzzle flash at the shooter
            add_circle(ax, iy, int(22 * (1 - t / 0.3)) + 6, (255, 230, 140), 220)
        if t > 0.4:
            add_ring(cx, iy, int(20 + 180 * (t - 0.4)), color, int(150 * fade), 4)
    elif aid == "venom":              # VENOM — a fan of poison blades spreads out
        for k in range(7):
            ang = -150 + k * 25
            ln = int(55 + 280 * min(1.0, t / 0.4))
            ex = cx + int(math.cos(math.radians(ang)) * ln)
            ey = iy + int(math.sin(math.radians(ang)) * ln)
            pygame.draw.line(surf, (150, 230, 70), (cx, iy), (ex, ey), 3)
            pygame.draw.polygon(surf, (210, 255, 150),
                                [(ex, ey), (ex - 5, ey - 7), (ex + 5, ey - 4)])
        add_circle(cx, iy, int(24 * fade) + 6, (150, 255, 90), int(120 * fade))

    # ── physical / spin / melee ──────────────────────────────────────────────
    elif aid in ("katarina", "reaver", "cyclone", "cleaver"):  # whirling-blade ults
        spin = age * 0.85
        rad = int(60 + 70 * t)
        arccol = {"katarina": (255, 90, 110), "reaver": (150, 255, 120),
                  "cyclone": (130, 230, 150), "cleaver": (255, 70, 60)}.get(aid, color)
        for kk in range(3):
            base = spin + kk * (2 * math.pi / 3)
            pts = []
            for j in range(8):
                a = base + (j / 7.0) * 1.5
                pts.append((cx + math.cos(a) * rad, iy + math.sin(a) * rad))
            lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            pygame.draw.lines(lay, (*arccol, int(170 * fade)), False,
                              [(int(x), int(y)) for x, y in pts], 5)
            pygame.draw.lines(lay, (*W, int(220 * fade)), False,
                              [(int(x), int(y)) for x, y in pts], 2)
            surf.blit(lay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    elif aid == "ironfist":           # IRONFIST — a rapid flurry of punch impacts
        for k in range(6):
            p = (t - k * 0.06)
            if p <= 0 or p > 0.18:
                continue
            px = cx + int(28 * math.sin(k * 2.1)); py = iy + int(20 * math.cos(k * 1.7))
            add_circle(px, py, int(26 * (1 - p / 0.18)) + 4, (255, 200, 120), 220)
            for a in range(0, 360, 45):
                e = (px + int(math.cos(math.radians(a)) * 22), py + int(math.sin(math.radians(a)) * 22))
                pygame.draw.line(surf, (255, 230, 160), (px, py), e, 2)
    elif aid == "yasuo":              # RONIN — a single horizontal iaido flash-slash
        p = min(1.0, t / 0.3)
        x2 = cx - 200 + int(440 * p)
        lay = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        pygame.draw.line(lay, (*W, int(230 * fade)), (cx - 200, iy), (x2, iy), 4)
        pygame.draw.line(lay, (160, 200, 255, int(150 * fade)), (cx - 200, iy + 4), (x2, iy + 4), 8)
        surf.blit(lay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    elif aid == "mordekaiser":        # JUGGERNAUT — the ground SHATTERS, rock chunks fly
        for a in (-1, 1):             # radiating ground cracks
            for seg in range(4):
                x1 = cx + a * (seg * 34); x2 = cx + a * (seg * 34 + 30)
                yy = ground_y - 2 + (seg % 2) * 4
                pygame.draw.line(surf, (40, 34, 30), (x1, yy), (x2, yy + (4 if seg % 2 else -4)), 3)
        for k in range(7):            # rock chunks tossed up
            p = t
            rx = cx + (k - 3) * 26
            ry = ground_y - int((130 * p - 130 * p * p) * 4)   # parabola up then down
            pygame.draw.rect(surf, (90, 80, 72), (rx - 4, ry - 4, 8, 8))
        add_ring(cx, ground_y - 4, int(30 + 250 * t), (180, 160, 140), int(150 * fade), 7)
    elif aid == "bulwark":            # BULWARK — a hexagonal shield force-burst
        rad = int(30 + 220 * t)
        for ring_w, a in ((6, int(190 * fade)), (2, int(230 * fade))):
            pts = [(cx + int(math.cos(math.radians(60 * k - 90)) * rad),
                    iy + int(math.sin(math.radians(60 * k - 90)) * rad)) for k in range(6)]
            col = color if ring_w == 6 else W
            pygame.draw.polygon(surf, col, pts, ring_w)
    else:                              # default — a champion-colour star burst
        for a in range(0, 360, 30):
            ln = int(40 + 280 * t)
            ex = cx + int(math.cos(math.radians(a)) * ln)
            ey = iy + int(math.sin(math.radians(a)) * ln)
            pygame.draw.line(surf, color, (cx, iy), (ex, ey), 4)
        add_circle(cx, iy, int(24 * fade) + 6, color, int(150 * fade))


# ── HUD ───────────────────────────────────────────────────────────────────────

def _draw_hud(surf: pygame.Surface, env) -> None:
    """Two-corner HUD — champion name, HP, MP, in each fighter's own color."""
    _draw_player_hud(surf, env.left, _char_color(env.left), x=12,
                      name=env.left.display_name.upper())
    _draw_player_hud(surf, env.right, _char_color(env.right), x=WIDTH - 12 - 200,
                      name=env.right.display_name.upper(), right_align=True)


def _draw_player_hud(surf: pygame.Surface, char, color, x: int, name: str,
                      right_align: bool = False) -> None:
    bar_w = 200
    bar_h = 14
    y = 16
    font = _get_hud_font(14)
    name_surf = font.render(name, True, (240, 240, 255))
    if right_align:
        surf.blit(name_surf, (x + bar_w - name_surf.get_width(), y - 16))
    else:
        surf.blit(name_surf, (x, y - 16))
    pygame.draw.rect(surf, (40, 40, 50), (x, y, bar_w, bar_h))
    hp_frac = max(0.0, char.hp / max(1, getattr(char, "hp_max", 100)))
    fill_w = int(bar_w * hp_frac)
    if right_align:
        pygame.draw.rect(surf, color, (x + bar_w - fill_w, y, fill_w, bar_h))
    else:
        pygame.draw.rect(surf, color, (x, y, fill_w, bar_h))
    pygame.draw.rect(surf, (210, 210, 230), (x, y, bar_w, bar_h), 1)
    mp_y = y + bar_h + 4
    pygame.draw.rect(surf, (30, 30, 40), (x, mp_y, bar_w, 6))
    mp_frac = max(0.0, char.mp / max(1, getattr(char, "mp_max", 100)))
    mp_w = int(bar_w * mp_frac)
    mp_color = (180, 200, 80)
    if right_align:
        pygame.draw.rect(surf, mp_color, (x + bar_w - mp_w, mp_y, mp_w, 6))
    else:
        pygame.draw.rect(surf, mp_color, (x, mp_y, mp_w, 6))
    pygame.draw.rect(surf, (180, 180, 200), (x, mp_y, bar_w, 6), 1)


def _draw_banner(surf: pygame.Surface, text: str) -> None:
    """Centered banner near top — skill names and ULTIMATE!."""
    font = _get_hud_font(22)
    text_surf = font.render(text, True, (255, 240, 120))
    rect = text_surf.get_rect(center=(WIDTH // 2, 70))
    plate = pygame.Surface((rect.width + 24, rect.height + 12), pygame.SRCALPHA)
    plate.fill((0, 0, 0, 180))
    surf.blit(plate, (rect.x - 12, rect.y - 6))
    surf.blit(text_surf, rect)


# ── Audio routing ─────────────────────────────────────────────────────────────

def _route_audio_for_events(events, event_video_ms, mixer):
    """Route battle events to SFX buses using compose.py's convention."""
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


# ── Intro / result screens ────────────────────────────────────────────────────

def _draw_vs_intro(surf: pygame.Surface, left_char, right_char,
                    frame: int, total: int) -> None:
    """One frame of the VS intro — both champions slide in, big VS, names."""
    surf.fill(BG)
    _draw_back_wall(surf, frame)
    _draw_floor(surf, frame)

    t = frame / max(1, total)
    slide = _ease_out(min(1.0, t / 0.45))     # slide-in completes at 45%
    lx_final, rx_final = 150, 330

    left_char.pos_y = GROUND_Y
    left_char.facing = 1
    left_char.pos_x = int(_lerp(-90, lx_final, slide))
    right_char.pos_y = GROUND_Y
    right_char.facing = -1
    right_char.pos_x = int(_lerp(WIDTH + 90, rx_final, slide))

    _draw_shadow(surf, left_char)
    _draw_shadow(surf, right_char)
    draw_stick_figure(surf, left_char, _char_color(left_char))
    draw_stick_figure(surf, right_char, _char_color(right_char))

    # Champion names (appear once slid in)
    if slide > 0.6:
        font_name = _get_hud_font(24)
        ln = font_name.render(left_char.display_name.upper(), True,
                              _char_color(left_char))
        rn = font_name.render(right_char.display_name.upper(), True,
                              _char_color(right_char))
        surf.blit(ln, (lx_final - ln.get_width() // 2, 300))
        surf.blit(rn, (rx_final - rn.get_width() // 2, 300))

    # "VS" pops in after 40%
    vs_t = _ease_out(min(1.0, max(0.0, (t - 0.4) / 0.3)))
    if vs_t > 0:
        vs_size = int(50 + 46 * vs_t)
        font_vs = _get_hud_font(vs_size)
        vs = font_vs.render("VS", True, (255, 230, 120))
        plate = pygame.Surface((vs.get_width() + 28, vs.get_height() + 14),
                               pygame.SRCALPHA)
        plate.fill((0, 0, 0, 170))
        cx, cy = WIDTH // 2, 250
        surf.blit(plate, (cx - plate.get_width() // 2,
                          cy - plate.get_height() // 2))
        surf.blit(vs, (cx - vs.get_width() // 2, cy - vs.get_height() // 2))


def _draw_ko_result(surf: pygame.Surface, winner_char,
                     frame: int, total: int) -> None:
    """One frame of the K.O. / winner card."""
    surf.fill(BG)
    _draw_back_wall(surf, frame)
    _draw_floor(surf, frame)

    t = frame / max(1, total)

    # Winner stands center, idle
    winner_char.pos_x = WIDTH // 2
    winner_char.pos_y = GROUND_Y
    winner_char.facing = 1
    winner_char.action_state = "idle"
    winner_char.attack_phase = "none"
    winner_char.attack_anim_hint = "jab"
    winner_char.on_ground = True
    winner_char.vel_x = 0.0
    _draw_shadow(surf, winner_char)
    draw_stick_figure(surf, winner_char, _char_color(winner_char))

    if t < 0.26:
        # Phase 1 — huge "K.O." slamming in + white flash
        ko_t = _ease_out(t / 0.26)
        ko_size = int(70 + 78 * ko_t)
        font_ko = _get_hud_font(ko_size)
        ko = font_ko.render("K.O.", True, (255, 80, 70))
        surf.blit(ko, (WIDTH // 2 - ko.get_width() // 2,
                       200 - ko.get_height() // 2))
        if t < 0.09:
            fl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 255, 255, int(190 * (1 - t / 0.09))))
            surf.blit(fl, (0, 0))
    else:
        # Phase 2 — winner card
        font_w = _get_hud_font(22)
        wl = font_w.render("WINNER", True, (255, 230, 120))
        surf.blit(wl, (WIDTH // 2 - wl.get_width() // 2, 150))
        font_n = _get_hud_font(46)
        nm = font_n.render(winner_char.display_name.upper(), True,
                           _char_color(winner_char))
        plate = pygame.Surface((nm.get_width() + 32, nm.get_height() + 16),
                               pygame.SRCALPHA)
        plate.fill((0, 0, 0, 170))
        surf.blit(plate, (WIDTH // 2 - plate.get_width() // 2, 188))
        surf.blit(nm, (WIDTH // 2 - nm.get_width() // 2, 196))


# ── Fight renderer ────────────────────────────────────────────────────────────

def _rl_action_source(model):
    """Adapt a PPO model to the (env, obs) -> (left_act, right_act) interface."""
    def _source(env, obs):
        obs_left, obs_right = obs
        left_act, _ = model.predict(obs_left, deterministic=False)
        right_act, _ = model.predict(obs_right, deterministic=False)
        return int(left_act), int(right_act)
    return _source


def _render_fight(recorder: FrameRecorder, action_source, env,
                   max_seconds: float, end_hold_frames: int = 0,
                   left_start_mp: Optional[int] = None,
                   right_start_mp: Optional[int] = None,
                   left_start_hp: Optional[int] = None,
                   right_start_hp: Optional[int] = None) -> dict:
    """Run the fight, writing frames to `recorder`. Returns:
        {n_frames, events, event_video_ms, winner, terminated}
    `event_video_ms` maps event id -> ms relative to the FIRST fight frame.
    `winner` is 'left'/'right' (KO, or higher HP on timeout) or None on a draw.
    `action_source` is a callable ``(env, obs) -> (left_act, right_act)``
        returning the two characters' action integers for the tick.
    """
    from pixel_battle.rl.hud import HUD as _HUD
    from pixel_battle.rl.impact_fx import ImpactFX as _ImpactFX
    from pixel_battle.rl.ko_sequence import KOSequence as _KOSequence
    from pixel_battle.rl.ultimate_sequence import UltimateSequence as _UltSequence
    from pixel_battle.rl.poses import select_pose_id as _select_pose_id
    from pixel_battle.engine.battle import BattleState as _BattleState
    from pixel_battle.engine.skill import SkillType as _SkillType

    (obs_left, obs_right), _ = env.reset()
    # Per-script starting-MP override MUST be applied *after* env.reset() — reset
    # zeroes MP, so applying it before this call (as the caller naturally would)
    # is silently clobbered. This is what let scripted ultimates fail to charge.
    if left_start_mp is not None:
        env.battle.left.mp = min(env.battle.left.mp_max, left_start_mp)
    if right_start_mp is not None:
        env.battle.right.mp = min(env.battle.right.mp_max, right_start_mp)
    # Per-script HP override (also after reset). Higher HP lets a long cinematic
    # fight trade REAL hits over 40s without someone dying early — the engine's
    # default 30 HP forces a hit-starved, dull footsie dance. Sets hp and hp_max.
    if left_start_hp is not None:
        env.battle.left.hp = env.battle.left.hp_max = left_start_hp
    if right_start_hp is not None:
        env.battle.right.hp = env.battle.right.hp_max = right_start_hp
    lcol = _char_color(env.left)
    rcol = _char_color(env.right)

    hud_overlay = _HUD()
    impact_fx = _ImpactFX()
    ko_seq = _KOSequence()
    ult_seq = _UltSequence()
    _ult_phase_particle_timer: int = 0  # ms since last converging-particle spawn batch
    _ult_pending_vfx: str = ""
    _ult_actor_x: float = 0.0
    _ult_actor_y: float = 0.0
    _ult_target_x: float = 0.0
    _ult_target_y: float = 0.0
    _ult_brand_col: tuple = (255, 240, 120)
    _ult_burst_color: tuple = (255, 255, 255)
    # Ultimate knockback launch state (renderer-side ballistic override)
    _ult_def_is_left: bool = False
    _launch_active: bool = False
    _launch_x: float = 0.0
    _launch_y: float = 0.0
    _launch_vx: float = 0.0
    _launch_vy: float = 0.0

    surf = pygame.Surface((WIDTH, HEIGHT))
    world = pygame.Surface((WIDTH, HEIGHT))
    total_frames = int(max_seconds * RENDER_FPS)
    event_video_ms: dict = {}
    terminated = False
    frame = 0
    # ── Sub-frame interpolation state ─────────────────────────────────────────
    _accum_ms: float = 0.0
    _prev_left_x: float = env.left.pos_x
    _prev_left_y: float = env.left.pos_y
    _prev_right_x: float = env.right.pos_x
    _prev_right_y: float = env.right.pos_y
    _interp_frac: float = 0.0
    _engine_this_frame: bool = True   # first render frame always ticks engine

    projectiles = ProjectileLayer()
    # Attacker-recoil cache: maps id(char) -> remaining_ms for the near-hand recoil nudge
    _attacker_recoil: dict = {}
    # Old full-screen shake — now used only for "beam" windup and "ultimate_start".
    # Crits and hits use the newer camera_shake_offset system (world-space, HUD stable).
    screen_shake_frames_left = 0
    screen_shake_mag = 0
    banner_text = None
    banner_until_frame = -1
    flash_frames_left = 0
    left_flash_frames = 0
    right_flash_frames = 0
    active_bursts: list = []          # [x, y, color, base_size, age]
    BURST_LIFE = 6
    active_shockwaves: list = []       # [x, y, color, age, life, max_radius]
    active_beams: list = []           # [sx, sy, ex, ey, color, age]
    active_spins: list = []           # [cx, cy, color, age]
    active_auras: list = []           # [cx, cy, color, age]
    active_ult_sigs: list = []        # [actor_id, cx, gy, age, color] — per-champion ult signature
    ULT_SIG_LIFE = 68
    BEAM_LIFE, SPIN_LIFE, AURA_LIFE = 10, 34, 46   # spin/aura linger longer to read
    prev_on_ground_left = env.left.on_ground
    prev_on_ground_right = env.right.on_ground
    cam_x = (env.left.pos_x + env.right.pos_x) / 2.0
    _cam_zoom_smooth = 1.0     # eased dynamic zoom (fit both fighters)
    shake_frames = 0
    n_written = 0

    # ── Motion blur ───────────────────────────────────────────────────────────
    # Blend the previous world surface at ~35 % alpha onto the current frame.
    # MOTION_BLUR_ALPHA is defined at module scope for testability.
    prev_world: Optional[pygame.Surface] = None

    # ── Slow-mo controller ────────────────────────────────────────────────────
    # When a crit or pre-KO event fires, we reduce effective dt fed to the engine.
    # The renderer still runs at 60 fps wall-clock; the engine receives slower time.
    _slowmo_remaining_ms: float = 0.0   # wall-clock ms of slow-mo left
    _slowmo_dt_scale: float = 1.0       # dt multiplier (< 1 = slower)

    # ── Ultimate camera zoom controller ───────────────────────────────────────
    # On ULTIMATE_START: zoom 1.0 → 1.35 over 200 ms, hold 200 ms, back to 1.0
    # over 200 ms. Focus on the caster's x position.
    _ULT_ZOOM_IN_MS = 800       # zoom in over first 800ms of anticipation
    _ULT_ZOOM_HOLD_MS = 700     # hold at max through rest of anticipation + release
    _ULT_ZOOM_OUT_MS = 400      # pull back during aftermath
    _ULT_ZOOM_TOTAL_MS = _ULT_ZOOM_IN_MS + _ULT_ZOOM_HOLD_MS + _ULT_ZOOM_OUT_MS
    _ULT_ZOOM_MAX = 1.5         # slightly tighter crop for drama
    _ult_zoom_age_ms: float = _ULT_ZOOM_TOTAL_MS   # starts "expired" (no zoom)
    _ult_zoom_focus_x: float = WIDTH / 2.0

    for frame in range(total_frames):
        # ── Sub-frame accumulator: engine ticks at ENGINE_HZ, render at RENDER_FPS ──
        # Every other render frame (when accumulator crosses 16.67ms) we advance
        # the engine once.  In-between frames draw with lerped positions for smoothness.
        _accum_ms += RENDER_MS
        _engine_this_frame = _accum_ms >= ENGINE_MS
        if _engine_this_frame:
            _accum_ms -= ENGINE_MS
            _interp_frac = 0.0
            # Snapshot previous character positions for position lerp
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
            # Slow-mo: advance the engine at a reduced rate this frame.
            # When _slowmo_remaining_ms > 0 we pass a scaled dt to the battle.
            if _slowmo_remaining_ms > 0:
                _slowmo_remaining_ms -= ENGINE_MS
                effective_dt = int(ENGINE_MS * _slowmo_dt_scale)
                # Apply the caller-provided actions ourselves (scripted driver OR
                # RL model) and tick with skip_ai=True — exactly like env.step,
                # just at the scaled dt. Previously this ran the engine's INTERNAL
                # AI (skip_ai=False), which hijacked scripted choreography and drained
                # the caster's MP, so the scripted ultimate would silently fail to
                # fire. Honoring the provided actions keeps slow-mo faithful.
                env._apply_action(env.left, env.right, int(left_act))
                env._apply_action(env.right, env.left, int(right_act))
                env.battle.tick_ms(effective_dt, skip_ai=True)
                # Re-derive observations from the existing env state
                try:
                    obs_left, obs_right = env._obs_pair()
                except Exception:
                    pass   # obs not critical for scripted renderer
                terminated = env.battle.state is _BattleState.KO
                truncated = False
            else:
                _slowmo_dt_scale = 1.0
                (obs_left, obs_right), _, terminated, truncated, _ = env.step(
                    (left_act, right_act)
                )
        else:
            prev_ev_n = len(env.battle.events)  # no new events on in-between frames

        # Interpolated draw positions (lerp prev→current by _interp_frac)
        _draw_left_x = _prev_left_x + (env.left.pos_x - _prev_left_x) * _interp_frac
        _draw_left_y = _prev_left_y + (env.left.pos_y - _prev_left_y) * _interp_frac
        _draw_right_x = _prev_right_x + (env.right.pos_x - _prev_right_x) * _interp_frac
        _draw_right_y = _prev_right_y + (env.right.pos_y - _prev_right_y) * _interp_frac

        if _engine_this_frame:
            for ev in env.battle.events[prev_ev_n:]:
                event_video_ms[id(ev)] = int(frame * RENDER_MS)
                et = ev.type.value
                if et == "hit":
                    defender = env.right if ev.target == env.right.id else env.left
                    attacker = env.left if ev.actor == env.left.id else env.right
                    is_crit = bool((ev.extra or {}).get("crit", False))
                    burst_size = 84 if is_crit else 62
                    burst_color = lcol if attacker is env.left else rcol
                    active_bursts.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, burst_size, 0,
                    ])
                    if defender is env.left:
                        left_flash_frames = max(left_flash_frames, 8)
                    else:
                        right_flash_frames = max(right_flash_frames, 8)
                    # ── Spark SPRAY at the contact point — the missing "it connected!"
                    #    feedback. Without this a clean hit read as a whiff. ──
                    impact_fx.spawn_hit_spark(
                        x=int(defender.pos_x), y=int(defender.pos_y) - 78,
                        damage=(10 if is_crit else 7), color=burst_color)
                    # quick white impact pop
                    impact_fx.flash_screen(color=(255, 255, 255),
                                           alpha=(150 if is_crit else 70))
                    # ── Camera shake on hit (punchier) ──
                    if is_crit:
                        impact_fx.camera_shake.trigger(magnitude_px=6.0, duration_ms=220.0)
                    else:
                        impact_fx.camera_shake.trigger(magnitude_px=3.5, duration_ms=140.0)
                    # ── Hit-confirm ring at defender's hip ──
                    impact_fx.spawn_hit_ring(
                        x=int(defender.pos_x),
                        y=int(defender.pos_y) - 60,
                        color=burst_color)
                    # ── Attacker recoil: mark near-hand kick-back for 100 ms ──
                    _attacker_recoil[id(attacker)] = 100
                    # ── Brief HITSTOP — a ~45ms near-freeze on contact gives the
                    #    "thunk" of a real hit (short, so it stays punchy not sluggish). ──
                    _slowmo_remaining_ms = max(_slowmo_remaining_ms, 45.0)
                    _slowmo_dt_scale = min(_slowmo_dt_scale, 0.12) if _slowmo_remaining_ms > 0 else 0.12
                    # ── Pre-KO slow-mo: final blow gives a "going down" beat ──
                    if defender.hp <= 0:
                        _slowmo_remaining_ms = max(_slowmo_remaining_ms, 200.0)
                        _slowmo_dt_scale = 0.3
                elif et == "crit":
                    defender = env.right if ev.target == env.right.id else env.left
                    attacker = env.left if ev.actor == env.left.id else env.right
                    burst_color = lcol if attacker is env.left else rcol
                    brand_col_crit = getattr(attacker, "brand_color",
                                             getattr(attacker, "color", burst_color))
                    active_bursts.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, 88, 0,
                    ])
                    active_shockwaves.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, 0, 14, 230,
                    ])
                    if defender is env.left:
                        left_flash_frames = max(left_flash_frames, 10)
                    else:
                        right_flash_frames = max(right_flash_frames, 10)
                    shake_frames = SHAKE_FRAMES * 2  # doubled for 120fps
                    # ── Crit emphasis: full-screen white flash + speed lines ──
                    impact_fx.flash_screen(color=(255, 255, 255), alpha=200)
                    impact_fx.spawn_crit_speed_lines(
                        x=int(defender.pos_x),
                        y=int(defender.pos_y) - 90,
                        color=brand_col_crit)
                    # Slow-mo fires ONLY on pre-KO; per-crit slow-mo was too frequent.
                    if defender.hp <= 0:
                        _slowmo_remaining_ms = max(_slowmo_remaining_ms, 200.0)
                        _slowmo_dt_scale = 0.3
                elif et == "attack_windup":
                    vfx = (ev.extra or {}).get("vfx", "melee")
                    skill_type_str = (ev.extra or {}).get("skill_type", "")
                    actor_obj = env.left if ev.actor == env.left.id else env.right
                    target_obj = env.right if actor_obj is env.left else env.left
                    a_color = lcol if actor_obj is env.left else rcol
                    brand_col = getattr(actor_obj, "brand_color",
                                        getattr(actor_obj, "color", a_color))
                    ax, ay = int(actor_obj.pos_x), int(actor_obj.pos_y)
                    tx, ty = int(target_obj.pos_x), int(target_obj.pos_y)
                    now_ms = int(frame * RENDER_MS)
                    # Arcane casters: a rune ring pulse at the feet + a radial
                    # starburst so spells read as channelled magic (vs assassin steel).
                    if actor_obj.id in _MAGE_IDS and vfx in ("bolt", "multishot", "beam", "aura", "shield"):
                        impact_fx.spawn_hit_ring(x=ax, y=GROUND_Y, color=brand_col)
                        impact_fx.spawn_aura_starburst(x=ax, y=ay - 80, color=brand_col)
                    pkind = _PROJECTILE_KIND.get(actor_obj.id, "orb")
                    if vfx == "bolt":
                        projectiles.spawn(start=(ax, ay - 130), end=(tx, ty - 90),
                                           color=a_color, current_ms=now_ms,
                                           duration_ms=280, kind=pkind)
                    elif vfx == "multishot":
                        for off in (-44, -22, 0, 22, 44):
                            projectiles.spawn(start=(ax, ay - 110),
                                               end=(tx, ty - 90 + off),
                                               color=a_color, current_ms=now_ms,
                                               duration_ms=300, kind=pkind)
                        # Multishot fan sparks from caster hand
                        for off_deg in (-20, -10, 0, 10, 20):
                            impact_fx.spawn_hit_spark(
                                x=ax, y=ay - 110, damage=2, color=a_color)
                    elif vfx == "beam":
                        bx = tx + (tx - ax) // 3
                        active_beams.append([ax, ay - 95, bx, ty - 95, a_color, 0])
                        # New: high-alpha beam overlay from ImpactFX
                        impact_fx.spawn_beam_fx(x1=ax, x2=bx, y=ay - 95,
                                                 color=brand_col)
                        screen_shake_frames_left = max(screen_shake_frames_left, 12)
                        screen_shake_mag = max(screen_shake_mag, 5)
                    elif vfx == "spin":
                        active_spins.append([ax, ay - 90, a_color, 0])
                    elif vfx == "aura":
                        active_auras.append([ax, ay - 90, a_color, 0])
                        # New: radial starburst from ImpactFX
                        impact_fx.spawn_aura_starburst(x=ax, y=ay - 90,
                                                        color=brand_col)
                    elif vfx == "shield":
                        # New: buff pillar — bright vertical particles
                        impact_fx.spawn_buff_pillar(x=ax, y=ay - 20, color=brand_col)
                        active_auras.append([ax, ay - 90, a_color, 0])
                    elif vfx == "dash":
                        # Blink-strike: afterimage trail + a flash streak + speed
                        # lines at the landing — reads as a fast physical lunge.
                        impact_fx.spawn_dash_afterimage(
                            sx=float(ax), sy=float(ay),
                            ex=float(tx), ey=float(ty),
                            color=a_color)
                        impact_fx.spawn_flash_streak(
                            from_x=float(ax), to_x=float(tx), hip_y=float(ay - 70),
                            color=a_color, n_ghosts=4)
                        impact_fx.spawn_crit_speed_lines(
                            x=int(tx), y=int(ty - 95), color=(255, 255, 255))
                        impact_fx.spawn_hit_spark(x=int(tx), y=int(ty - 95),
                                                  damage=3, color=a_color)
                    elif vfx == "slam":
                        active_shockwaves.append([tx, ty - 90, a_color, 0, 16, 300])
                    kind = (ev.extra or {}).get("skill_type")
                    if kind in ("cooldown", "special"):
                        skill_id = (ev.extra or {}).get("skill_id", "?")
                        banner_text = str(skill_id).upper().replace("_", " ") + "!"
                        banner_until_frame = frame + 72   # doubled: was 36 @ 60fps
                        if vfx in ("bolt", "multishot", "beam", "aura", "shield"):
                            # Real caster channel — a glowing charge orb reads as magic.
                            impact_fx.spawn_charge_orb(
                                x=ax, y=ay - 130, color=brand_col,
                                lifetime_ms=150, scale=1.0)
                        else:
                            # Physical cast (melee/dash/spin): a steel spark at the
                            # strike point, NOT a magic glow orb — the glow orb is
                            # what made assassins/warriors read like mages.
                            hx = ax + (44 if tx >= ax else -44)
                            impact_fx.spawn_hit_spark(x=hx, y=ay - 95, damage=3, color=a_color)
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
                    # Banner fires immediately (non-visual timing doesn't matter)
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
                    # Store deferred VFX info for RELEASE phase
                    _ult_pending_vfx = (ev.extra or {}).get("vfx", "slam")
                    _ult_actor_id = actor_obj.id
                    _ult_actor_x = float(actor_obj.pos_x)
                    _ult_actor_y = float(actor_obj.pos_y)
                    _ult_target_x = float(defender.pos_x)
                    _ult_target_y = float(defender.pos_y)
                    _ult_brand_col = brand_col_ult
                    _ult_burst_color = burst_color
                    _ult_def_is_left = (defender is env.left)
                    # Reset camera zoom to track anticipation
                    _ult_zoom_age_ms = 0.0
                    _ult_zoom_focus_x = float(actor_obj.pos_x)
                    # Flash the defender during anticipation startup
                    if defender is env.left:
                        left_flash_frames = max(left_flash_frames, 6)
                    else:
                        right_flash_frames = max(right_flash_frames, 6)
                elif et == "flash":
                    fx = ev.extra or {}
                    ground_y = GROUND_Y
                    actor_obj_fl = env.left if ev.actor == env.left.id else env.right
                    actor_col = lcol if ev.actor == env.left.id else rcol
                    from_x_fl = fx.get("from_x", 0)
                    to_x_fl = fx.get("to_x", 0)
                    # Ghost streak between from_x and to_x at hip height
                    hip_y_fl = ground_y - 55   # approximate hip: ~55 px above feet
                    impact_fx.spawn_flash_streak(
                        from_x=float(from_x_fl), to_x=float(to_x_fl),
                        hip_y=float(hip_y_fl), color=actor_col, n_ghosts=5)
                    # After-shadow torsos along the blink path + a steel spark at
                    # the landing — the teleport reads as a STRIKE, not just a hop.
                    impact_fx.spawn_dash_afterimage(
                        sx=float(from_x_fl), sy=float(ground_y),
                        ex=float(to_x_fl), ey=float(ground_y), color=actor_col)
                    impact_fx.spawn_hit_spark(
                        x=int(to_x_fl), y=int(ground_y - 95), damage=3, color=actor_col)
                    # Keep the original puffs at origin/destination for extra punch
                    spawn_flash_puff(world, from_x_fl, ground_y, actor_col)
                    spawn_flash_puff(world, to_x_fl, ground_y, actor_col)

            # Route new events to the impact FX layer (KOF-style sparks + text)
            for ev in env.battle.events[prev_ev_n:]:
                ev_t = ev.type.value
                if ev_t in ("hit", "crit"):
                    target = env.right if ev.target == env.right.id else env.left
                    attacker_ev = env.left if ev.actor == env.left.id else env.right
                    col = hud_overlay._color(target.id)
                    burst_col_ev = lcol if attacker_ev is env.left else rcol
                    impact_fx.spawn_hit_spark(x=int(target.pos_x),
                                              y=int(target.pos_y) - 20,
                                              damage=ev.amount, color=col)
                    is_crit_ev = (ev_t == "crit") or bool((ev.extra or {}).get("crit"))
                    if is_crit_ev:
                        impact_fx.flash_screen(color=(255, 240, 180), alpha=160)
                        # Bigger (1.5×) brand-colored CRIT! text
                        crit_brand = getattr(attacker_ev, "brand_color",
                                             getattr(attacker_ev, "color", burst_col_ev))
                        impact_fx.spawn_floating_text(x=int(target.pos_x),
                                                      y=int(target.pos_y) - 40,
                                                      text="CRIT!", color=crit_brand,
                                                      font_size=66)  # ~1.5× of default 44
                    else:
                        impact_fx.spawn_floating_text(x=int(target.pos_x),
                                                      y=int(target.pos_y) - 40,
                                                      text="HIT!", color=(255, 240, 200))
                    # Hit-confirm ring (also for crit — ring appears at defender hip)
                    impact_fx.spawn_hit_ring(x=int(target.pos_x),
                                             y=int(target.pos_y) - 60,
                                             color=burst_col_ev)
                elif ev_t == "ultimate_start":
                    impact_fx.flash_screen(color=(255, 60, 60), alpha=200)

        # ── Ultimate sequence — per-frame cinematic phase dispatch ────────────
        ult_result = ult_seq.tick(triggered=False, dt_ms=RENDER_MS)
        # True while ANY ultimate phase (anticipation/release/aftermath) is playing.
        # The ultimate KOs instantly on the engine side, so without this guard the
        # KO-drama break (below) would fire mid-anticipation and the cinematic
        # release + aftermath would never render.
        _ult_active = ult_result.phase is not None
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
                impact_fx.spawn_magic_circle(
                    cx=ult_result.caster_x,
                    ground_y=GROUND_Y,
                    radius=40 + ult_result.magic_circle_t * 40,
                    color=ult_result.color,
                    rotation=ult_result.magic_circle_t * math.pi * 4)
            # Converging particles: spawn every ~3 render frames
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
                impact_fx.spawn_release_flash(
                    cx=_ult_actor_x, cy=_ult_actor_y - 90,
                    color=ult_result.color)
            if ult_result.spawn_beam:
                # Fire the beam VFX deferred from the event handler
                if _ult_pending_vfx == "beam":
                    bx = _ult_target_x + (_ult_target_x - _ult_actor_x) / 2
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
                    # Impact punch where the beam strikes the defender — expanding
                    # shockwave rings + a spark burst so the hit reads as the climax.
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 95,
                        (255, 255, 255), 0, 18, 380])
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 95,
                        _ult_brand_col, 0, 22, 440])
                    impact_fx.spawn_hit_spark(
                        int(_ult_target_x), int(_ult_target_y) - 95, 30, _ult_brand_col)
                    impact_fx.spawn_ultimate_slam(
                        impact_x=float(_ult_target_x),
                        impact_y=float(_ult_target_y),
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
                    # EXECUTION: a ground crater — debris kicked up + dust + a
                    # wide low ground-crack ring, and a heavier shake below.
                    for _d in range(3):
                        impact_fx.spawn_hit_spark(int(_ult_target_x), GROUND_Y - 6,
                                                  26, _ult_brand_col)
                    impact_fx.spawn_smoke_cloud(x=float(_ult_target_x),
                                                y=float(GROUND_Y), color=(150, 142, 130))
                    active_shockwaves.append([
                        int(_ult_target_x), GROUND_Y - 4, (230, 220, 200), 0, 13, 580])
                    screen_shake_frames_left = max(screen_shake_frames_left, 40)
                    screen_shake_mag = max(screen_shake_mag, 14)
                elif _ult_pending_vfx == "bolt":
                    # A converging VOLLEY (e.g. 3 giant ice shards) + an impact punch
                    # — a single bolt read too thin for a climax.
                    _bk = _PROJECTILE_KIND.get(_ult_actor_id, "orb")
                    for _o in (-15, 0, 15):
                        projectiles.spawn(
                            start=(int(_ult_actor_x), int(_ult_actor_y) - 130),
                            end=(int(_ult_target_x), int(_ult_target_y) - 90 + _o),
                            color=_ult_burst_color,
                            current_ms=int(frame * RENDER_MS),
                            duration_ms=240, kind=_bk)
                    impact_fx.spawn_hit_spark(
                        int(_ult_target_x), int(_ult_target_y) - 95, 30, _ult_brand_col)
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 95,
                        _ult_brand_col, 0, 18, 410])
                elif _ult_pending_vfx == "multishot":
                    # Gunslinger bullet-hell / ninja blade-fan: a spread of
                    # projectiles converging on the defender.
                    _ukind = _PROJECTILE_KIND.get(_ult_actor_id, "orb")
                    for _k in range(5):
                        _spread = (_k - 2) * 24
                        projectiles.spawn(
                            start=(int(_ult_actor_x), int(_ult_actor_y) - 130),
                            end=(int(_ult_target_x), int(_ult_target_y) - 90 + _spread),
                            color=_ult_burst_color,
                            current_ms=int(frame * RENDER_MS),
                            duration_ms=240, kind=_ukind)
                    impact_fx.spawn_hit_spark(
                        int(_ult_target_x), int(_ult_target_y) - 95, 26, _ult_brand_col)
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 90,
                        _ult_brand_col, 0, 18, 400])
                elif _ult_pending_vfx == "spin":
                    # Assassin blade-storm: whirling rings on the caster + a
                    # shockwave burst where the blades shred the defender.
                    impact_fx.spawn_ultimate_slam(
                        impact_x=float(_ult_target_x),
                        impact_y=float(_ult_target_y),
                        color=_ult_brand_col, surf_size=(WIDTH, HEIGHT))
                    active_spins.append([int(_ult_actor_x), int(_ult_actor_y) - 90,
                                         _ult_burst_color, 0])
                    active_spins.append([int(_ult_target_x), int(_ult_target_y) - 90,
                                         _ult_brand_col, 0])
                    active_shockwaves.append([
                        int(_ult_target_x), int(_ult_target_y) - 90,
                        (255, 240, 150), 0, 22, 480])
                # Per-champion SIGNATURE flourish — each ult its own identity on
                # top of the shared base effect (a descending sword vs a meteor vs
                # ice spikes vs a bullet barrage…).
                active_ult_sigs.append([_ult_actor_id, int(_ult_target_x),
                                        int(_ult_target_y), 0, _ult_brand_col])
                # Camera shake + flash on release — clean white-gold (an ultimate
                # discharge), NOT the red hit-flash that read as "getting punched".
                impact_fx.flash_screen(color=(255, 244, 210), alpha=210)
                impact_fx.camera_shake.trigger(magnitude_px=5.0, duration_ms=200.0)
                screen_shake_frames_left = max(screen_shake_frames_left, 32)
                screen_shake_mag = max(screen_shake_mag, 11)
                # Blast the defender off their feet — away from the caster, up,
                # then gravity + wall collision carry them down over the aftermath.
                _launch_active = True
                _launch_x = float(_ult_target_x)
                _launch_y = float(_ult_target_y)
                _launch_vx = ULT_LAUNCH_VX * (1.0 if _ult_target_x >= _ult_actor_x else -1.0)
                _launch_vy = -ULT_LAUNCH_VY
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
        # Override slow-mo dt during ultimate anticipation / release
        if ult_result.phase is not None and ult_result.dt_scale < 1.0:
            _slowmo_remaining_ms = max(_slowmo_remaining_ms, ENGINE_MS * 2)
            _slowmo_dt_scale = ult_result.dt_scale

        # KO sequence — drives slow-mo + zoom once battle.state == KO.
        # If the ultimate cinematic is mid-anticipation (engine frozen), DEFER
        # the KO sequence so the audience sees the full ult buildup before
        # the KO splash + zoom takes over.
        ko_active = (env.battle.state == _BattleState.KO) and not _ult_active
        ko_loser_x = (int(env.battle.left.pos_x)
                      if env.battle.left.hp <= 0 else int(env.battle.right.pos_x))
        ko_result = ko_seq.tick(ko_active=ko_active, ko_loser_x=ko_loser_x, dt_ms=RENDER_MS)
        if ko_result.spawn_flash:
            impact_fx.flash_screen(color=(255, 255, 255), alpha=255)
        if ko_result.spawn_splash:
            impact_fx.spawn_floating_text(x=WIDTH // 2, y=HEIGHT // 2 - 80,
                                          text="K.O.!", color=(255, 80, 80))

        # Landing dust — ground-touch edge detection
        pending_dust: list = []
        if env.left.on_ground and not prev_on_ground_left:
            pending_dust.append((int(env.left.pos_x), int(env.left.pos_y)))
        if env.right.on_ground and not prev_on_ground_right:
            pending_dust.append((int(env.right.pos_x), int(env.right.pos_y)))
        prev_on_ground_left = env.left.on_ground
        prev_on_ground_right = env.right.on_ground

        # World layer — apply interpolated draw positions for the render frame
        world.fill(BG)
        _draw_back_wall(world, frame)
        _draw_floor(world, frame)

        # Temporarily override pos_x/pos_y with interpolated values for drawing only
        def _set_draw_pos(char, ix, iy):
            char._orig_pos_x, char._orig_pos_y = char.pos_x, char.pos_y
            char.pos_x, char.pos_y = ix, iy

        def _restore_draw_pos(char):
            char.pos_x, char.pos_y = char._orig_pos_x, char._orig_pos_y

        # ── Ultimate knockback: ballistic launch of the defender (renderer-only) ──
        if _launch_active:
            _launch_vy += ULT_LAUNCH_GRAVITY
            _launch_x += _launch_vx
            _launch_y += _launch_vy
            # Wall thud — bounce off the arena edges, shedding most of the speed
            if _launch_x <= ARENA_LEFT + ULT_LAUNCH_EDGE_PAD:
                _launch_x = ARENA_LEFT + ULT_LAUNCH_EDGE_PAD
                _launch_vx = -_launch_vx * ULT_LAUNCH_WALL_BOUNCE
            elif _launch_x >= ARENA_RIGHT - ULT_LAUNCH_EDGE_PAD:
                _launch_x = ARENA_RIGHT - ULT_LAUNCH_EDGE_PAD
                _launch_vx = -_launch_vx * ULT_LAUNCH_WALL_BOUNCE
            # Ground landing — settle with skid friction
            if _launch_y >= GROUND_Y:
                _launch_y = GROUND_Y
                _launch_vy = 0.0
                _launch_vx *= 0.6
            # Force a knocked-out look: airborne -> tucked "jump" pose (reads as a
            # body flung through the air); grounded -> "hit_react" slumped recoil.
            _def_obj = env.left if _ult_def_is_left else env.right
            if _launch_y < GROUND_Y - 1:
                _def_obj.on_ground = False
                _def_obj.action_state = "ko"
            else:
                _def_obj.on_ground = True
                _def_obj.action_state = "hit_stagger"
            if _ult_def_is_left:
                _draw_left_x, _draw_left_y = _launch_x, _launch_y
            else:
                _draw_right_x, _draw_right_y = _launch_x, _launch_y

        _set_draw_pos(env.left, _draw_left_x, _draw_left_y)
        _set_draw_pos(env.right, _draw_right_x, _draw_right_y)
        try:
            _draw_shadow(world, env.left)
            _draw_shadow(world, env.right)

            left_color = HIT_FLASH if left_flash_frames > 0 else lcol
            right_color = HIT_FLASH if right_flash_frames > 0 else rcol
            left_flash_frames = max(0, left_flash_frames - 1)
            right_flash_frames = max(0, right_flash_frames - 1)

            # Attacker recoil: tick down timers and apply temporary pos nudge
            # so the near-hand reads as "kicked back on contact."
            # We store remaining_ms in _attacker_recoil keyed by id(char).
            for char in (env.left, env.right):
                cid = id(char)
                if cid in _attacker_recoil:
                    _attacker_recoil[cid] = max(0, _attacker_recoil[cid] - int(RENDER_MS))
                    if _attacker_recoil[cid] == 0:
                        del _attacker_recoil[cid]
            # Apply the recoil nudge: temporarily shift pos_y by +4 px (downward = arm kick-back).
            _cur_time_ms = frame * RENDER_MS

            def _draw_with_recoil(surf, char, color, opp_x):
                cid = id(char)
                if cid in _attacker_recoil:
                    orig_y = char.pos_y
                    char.pos_y = orig_y + 4
                    try:
                        draw_stick_figure(surf, char, color, time_ms=_cur_time_ms,
                                          opponent_x=opp_x)
                    finally:
                        char.pos_y = orig_y
                else:
                    draw_stick_figure(surf, char, color, time_ms=_cur_time_ms,
                                      opponent_x=opp_x)

            def _draw_char(surf, char, color, opp_x):
                # JUDGMENT whirlwind: render the WHOLE figure (body + blade) to a
                # temp layer and rotate it around the mid-body, so the character
                # literally spins — not just a VFX overlay on a static pose.
                if _select_pose_id(char) == "spin":
                    TS = 240
                    tmp = pygame.Surface((TS, TS), pygame.SRCALPHA)
                    ox, oy = char.pos_x, char.pos_y
                    # Place the mid-body near the temp-surface centre so rotation
                    # pivots about the torso (feet sit ~30px below centre).
                    char.pos_x, char.pos_y = TS / 2.0, TS / 2.0 + 30
                    try:
                        draw_stick_figure(tmp, char, color, time_ms=_cur_time_ms,
                                          opponent_x=ox + (1 if opp_x >= ox else -1) * 100)
                    finally:
                        char.pos_x, char.pos_y = ox, oy
                    ang = (_cur_time_ms * 1.15) % 360.0   # ~1 turn / 0.3s
                    rot = pygame.transform.rotate(tmp, ang)
                    rect = rot.get_rect(center=(int(ox), int(oy) - 30))
                    surf.blit(rot, rect)
                else:
                    _draw_with_recoil(surf, char, color, opp_x)

            _draw_char(world, env.left, left_color,
                       opp_x=float(env.right.pos_x))
            _draw_char(world, env.right, right_color,
                       opp_x=float(env.left.pos_x))
            draw_effect_indicators(world, env.left, current_ms=int(frame * RENDER_MS))
            draw_effect_indicators(world, env.right, current_ms=int(frame * RENDER_MS))
        finally:
            _restore_draw_pos(env.left)
            _restore_draw_pos(env.right)

        projectiles.draw(world, int(frame * RENDER_MS))

        still_live = []
        for b in active_bursts:
            bx, by, bcolor, bsize, age = b
            grow = 1.0 + 0.55 * (age / BURST_LIFE)
            spawn_impact_burst(world, bx, by, bcolor, int(bsize * grow))
            b[4] = age + 1
            if b[4] < BURST_LIFE:
                still_live.append(b)
        active_bursts = still_live

        # Expanding shockwave rings (crit / ultimate)
        live_sw = []
        for sw in active_shockwaves:
            sx, sy, scolor, sage, slife, smax = sw
            _draw_shockwave(world, sx, sy, scolor, sage, slife, smax)
            sw[3] = sage + 1
            if sw[3] < slife:
                live_sw.append(sw)
        active_shockwaves = live_sw

        live_beams = []
        for bm in active_beams:
            _draw_beam(world, bm[0], bm[1], bm[2], bm[3], bm[4], bm[5], BEAM_LIFE)
            bm[5] += 1
            if bm[5] < BEAM_LIFE:
                live_beams.append(bm)
        active_beams = live_beams

        live_spins = []
        for sp in active_spins:
            _draw_spin(world, sp[0], sp[1], sp[2], sp[3], SPIN_LIFE)
            sp[3] += 1
            if sp[3] < SPIN_LIFE:
                live_spins.append(sp)
        active_spins = live_spins

        live_sigs = []
        for sg in active_ult_sigs:
            _draw_ult_sig(world, sg[0], sg[1], sg[2], sg[3], ULT_SIG_LIFE, sg[4], GROUND_Y)
            sg[3] += 1
            if sg[3] < ULT_SIG_LIFE:
                live_sigs.append(sg)
        active_ult_sigs = live_sigs

        live_auras = []
        for au in active_auras:
            _draw_aura(world, au[0], au[1], au[2], au[3], AURA_LIFE)
            au[3] += 1
            if au[3] < AURA_LIFE:
                live_auras.append(au)
        active_auras = live_auras

        for (dx, dy) in pending_dust:
            spawn_landing_dust(world, dx, dy, (180, 180, 200), intensity=1.7)

        # ── Motion blur: blend previous world at 20 % alpha onto current ────
        # Skip during KO HOLD state so the final frame reads crisp.
        if prev_world is not None and not ko_result.zoom > 1.0:
            blur_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            blur_overlay.blit(prev_world, (0, 0))
            blur_overlay.set_alpha(MOTION_BLUR_ALPHA)
            world.blit(blur_overlay, (0, 0))
        prev_world = world.copy()

        # ── Ultimate zoom: advance age and compute zoom factor ───────────────
        _ult_zoom_age_ms += RENDER_MS
        if _ult_zoom_age_ms < _ULT_ZOOM_TOTAL_MS:
            if _ult_zoom_age_ms < _ULT_ZOOM_IN_MS:
                _uz_frac = _ult_zoom_age_ms / _ULT_ZOOM_IN_MS
                _uz_factor = 1.0 + (_ULT_ZOOM_MAX - 1.0) * _uz_frac
            elif _ult_zoom_age_ms < _ULT_ZOOM_IN_MS + _ULT_ZOOM_HOLD_MS:
                _uz_factor = _ULT_ZOOM_MAX
            else:
                _uz_out_frac = (_ult_zoom_age_ms - _ULT_ZOOM_IN_MS - _ULT_ZOOM_HOLD_MS) / _ULT_ZOOM_OUT_MS
                _uz_factor = _ULT_ZOOM_MAX - (_ULT_ZOOM_MAX - 1.0) * min(1.0, _uz_out_frac)
        else:
            _uz_factor = 1.0

        # Camera — follow midpoint (biased toward loser during KO), crop + upscale
        # Use interpolated draw positions for smooth camera follow
        mid_x = (_draw_left_x + _draw_right_x) / 2.0
        if ko_result.zoom > 1.0:
            # Bias camera center toward the loser for dramatic framing
            mid_x = mid_x * 0.4 + ko_result.zoom_focus_x * 0.6
        elif _uz_factor > 1.0:
            # Ultimate zoom: bias camera toward caster
            mid_x = mid_x * 0.4 + _ult_zoom_focus_x * 0.6
        cam_x += (mid_x - cam_x) * CAM_FOLLOW
        # Combine old crit-shake with new per-hit ImpactFX CameraShake
        sx0, sy0 = camera_shake_offset(shake_frames)
        sx1, sy1 = impact_fx.camera_shake.update(RENDER_MS)
        sx = sx0 + sx1
        sy = sy0 + sy1
        # Dynamic framing: ease a base zoom that fits both fighters + margin.
        _span = abs(_draw_left_x - _draw_right_x)
        _target_w = max(CAM_MIN_VIEW_W, min(WIDTH, _span + CAM_FRAME_MARGIN * 2))
        _dyn_zoom = WIDTH / _target_w
        _cam_zoom_smooth += (_dyn_zoom - _cam_zoom_smooth) * CAM_ZOOM_LERP
        # KO zoom and ultimate zoom keep their dramatic FIXED framing (override the
        # dynamic base); normal play uses the eased fit-to-fighters zoom.
        if ko_result.zoom > 1.0:
            frame_zoom = ko_result.zoom * CAM_ZOOM
        elif _uz_factor > 1.0:
            frame_zoom = _uz_factor * CAM_ZOOM
        else:
            frame_zoom = _cam_zoom_smooth
        view_w = int(WIDTH / frame_zoom)
        view_h = int(HEIGHT / frame_zoom)
        view_w = max(1, min(WIDTH, view_w))
        view_h = max(1, min(HEIGHT, view_h))
        view_x = int(cam_x - view_w / 2) + sx
        view_x = max(0, min(WIDTH - view_w, view_x))
        cam_view_y_adjusted = GROUND_Y - int(view_h * 0.82)
        view_y = max(0, min(HEIGHT - view_h, cam_view_y_adjusted + sy))
        sub = world.subsurface((view_x, view_y, view_w, view_h))
        pygame.transform.scale(sub, (WIDTH, HEIGHT), surf)
        if shake_frames > 0:
            shake_frames -= 1

        # Screen-space overlays
        if flash_frames_left > 0:
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 100))
            surf.blit(flash, (0, 0))
            flash_frames_left -= 1

        # Single KOF-style HUD (HP green->red + thin blue MP + names + timer).
        # The old two-corner _draw_hud was removed — drawing both stacked their
        # near-overlapping bars and duplicated the names (the "ghost text").
        hud_overlay.draw(surf, env.battle, elapsed_ms=int(frame * RENDER_MS))
        impact_fx.update_and_draw(surf, dt_ms=RENDER_MS)

        # KO splash text held on screen during HOLD phase
        if ko_result.splash_alpha > 0 and not ko_result.spawn_splash:
            # splash_alpha held at 255 in HOLD — just let the floating text handle it
            pass

        if banner_text is not None and frame <= banner_until_frame:
            _draw_banner(surf, banner_text)
        elif banner_text is not None and frame > banner_until_frame:
            banner_text = None

        # Screen shake
        if screen_shake_frames_left > 0:
            mag = max(2, screen_shake_mag)
            ox = random.randint(-mag, mag)
            oy = random.randint(-mag, mag)
            shaken = pygame.Surface((WIDTH, HEIGHT))
            shaken.fill(BG)
            # A crit's camera_shake_offset may still be decaying when this fires for an
            # ultimate; the brief visual overlap is acceptable.
            shaken.blit(surf, (ox, oy))
            recorder.write_frame(shaken)
            screen_shake_frames_left -= 1
            if screen_shake_frames_left == 0:
                screen_shake_mag = 0
        else:
            recorder.write_frame(surf)
        n_written += 1

        if terminated and not _ult_active:
            # KO drama: first run KO sequence frames (slow-mo zoom + splash),
            # then the standard whiteout that hands off to the result card.
            # The engine is already frozen (BattleState.KO → tick_ms no-ops).
            # We generate ~75 extra drama frames using the KO sequence controller.
            ko_drama_frames = int(1.5 * RENDER_FPS)  # ~1.5s of drama at 120fps
            ko_surf_base = surf.copy()               # snapshot of the last fight frame
            for _kf in range(ko_drama_frames):
                _ko_r = ko_seq.tick(ko_active=True, ko_loser_x=ko_loser_x, dt_ms=RENDER_MS)
                if _ko_r.spawn_flash:
                    impact_fx.flash_screen(color=(255, 255, 255), alpha=255)
                if _ko_r.spawn_splash:
                    impact_fx.spawn_floating_text(x=WIDTH // 2, y=HEIGHT // 2 - 80,
                                                  text="K.O.!", color=(255, 80, 80))

                # Redraw world with KO zoom applied
                _fz = _ko_r.zoom * CAM_ZOOM
                _vw = max(1, min(WIDTH, int(WIDTH / _fz)))
                _vh = max(1, min(HEIGHT, int(HEIGHT / _fz)))
                _vx = int(ko_result.zoom_focus_x - _vw / 2)
                _vx = max(0, min(WIDTH - _vw, _vx))
                _cam_view_y_ko = GROUND_Y - int(_vh * 0.82)
                _vy = max(0, min(HEIGHT - _vh, _cam_view_y_ko))
                try:
                    _sub = world.subsurface((_vx, _vy, _vw, _vh))
                    pygame.transform.scale(_sub, (WIDTH, HEIGHT), surf)
                except Exception:
                    surf.blit(ko_surf_base, (0, 0))

                hud_overlay.draw(surf, env.battle, elapsed_ms=int(frame * RENDER_MS))
                impact_fx.update_and_draw(surf, dt_ms=RENDER_MS)
                recorder.write_frame(surf)
                n_written += 1

            # Standard whiteout into the result card (32 frames = 16 @ 60fps)
            final_frame = surf.copy()
            for k in range(32):
                ko_frame = final_frame.copy()
                wa = int(215 * (k / 32) ** 1.4)
                wl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                wl.fill((255, 255, 255, wa))
                ko_frame.blit(wl, (0, 0))
                recorder.write_frame(ko_frame)
                n_written += 1
            for _ in range(end_hold_frames):
                recorder.write_frame(final_frame)
                n_written += 1
            break

    # Winner — by KO, or higher HP on a timeout
    if env.right.is_ko() and not env.left.is_ko():
        winner = "left"
    elif env.left.is_ko() and not env.right.is_ko():
        winner = "right"
    elif env.left.hp > env.right.hp:
        winner = "left"
    elif env.right.hp > env.left.hp:
        winner = "right"
    else:
        winner = None

    return {
        "n_frames": n_written,
        "events": list(env.battle.events),
        "event_video_ms": event_video_ms,
        "winner": winner,
        "terminated": bool(terminated),
    }


# ── Drivers ───────────────────────────────────────────────────────────────────

def run_one_match(model, seed: int, out_dir: Path,
                   max_seconds: float = 60.0,
                   match_name: str = "final") -> dict:
    """Render a single fight (no intro/result) to out_dir/{match_name}.mp4."""
    if not pygame.font.get_init():
        pygame.font.init()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_video = out_dir / f"{match_name}_raw.mp4"
    audio_out = out_dir / f"{match_name}_audio.wav"
    final_mp4 = out_dir / f"{match_name}.mp4"

    env = PixelBattleEnv(seed=seed)
    recorder = FrameRecorder(str(raw_video), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
    recorder.start()
    mixer = AudioMixer(sample_rate=48000)

    fight = _render_fight(recorder, _rl_action_source(model), env, max_seconds, end_hold_frames=120)
    recorder.stop()

    hit_count = sum(1 for ev in fight["events"] if ev.type.value == "hit")

    total_duration_ms = int(fight["n_frames"] * RENDER_MS)
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    _route_audio_for_events(fight["events"], fight["event_video_ms"], mixer)

    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))

    duration_s = total_duration_ms / 1000.0
    return {
        "finished_by_ko": fight["terminated"],
        "duration_s": duration_s,
        "winner": fight["winner"],
        "mp4_path": final_mp4,
        "raw_path": raw_video,
        "audio_path": audio_out,
        "action_score": hit_count / max(duration_s, 0.1),
    }


def run_full_episode(model, out_dir: Path, left_id: str, right_id: str,
                      seed: int = 2000, max_seconds: float = 60.0,
                      episode_name: str = "episode") -> dict:
    """Render a complete episode: VS intro -> fight -> K.O./winner card.

    Output: out_dir/{episode_name}.mp4 — a single stitched video.
    """
    if not pygame.font.get_init():
        pygame.font.init()
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_video = out_dir / f"{episode_name}_raw.mp4"
    audio_out = out_dir / f"{episode_name}_audio.wav"
    final_mp4 = out_dir / f"{episode_name}.mp4"

    env = PixelBattleEnv(seed=seed, left_id=left_id, right_id=right_id)

    recorder = FrameRecorder(str(raw_video), fps=RENDER_FPS, width=WIDTH, height=HEIGHT)
    recorder.start()
    mixer = AudioMixer(sample_rate=48000)
    surf = pygame.Surface((WIDTH, HEIGHT))

    # ── INTRO ────────────────────────────────────────────────────────────────
    intro_left = Character.load(left_id)
    intro_right = Character.load(right_id)
    for f in range(INTRO_FRAMES):
        _draw_vs_intro(surf, intro_left, intro_right, f, INTRO_FRAMES)
        recorder.write_frame(surf)

    # ── FIGHT ────────────────────────────────────────────────────────────────
    fight = _render_fight(recorder, _rl_action_source(model), env, max_seconds, end_hold_frames=0)

    # ── RESULT ───────────────────────────────────────────────────────────────
    winner_side = fight["winner"]
    winner_id = right_id if winner_side == "right" else left_id
    winner_char = Character.load(winner_id)
    for f in range(RESULT_FRAMES):
        _draw_ko_result(surf, winner_char, f, RESULT_FRAMES)
        recorder.write_frame(surf)

    recorder.stop()

    total_frames = INTRO_FRAMES + fight["n_frames"] + RESULT_FRAMES
    total_duration_ms = int(total_frames * RENDER_MS)

    # ── AUDIO ────────────────────────────────────────────────────────────────
    bgm_path = BGM_DIR / "battle_loop.mp3"
    if bgm_path.exists():
        bgm = _load_wav(bgm_path, mixer.sr)
        looped = _loop_to_length(bgm, total_duration_ms, mixer.sr)
        mixer.bgm_bus.add(looped, t_ms=0)
    # Shift fight events past the intro
    intro_offset_ms = int(INTRO_FRAMES * RENDER_MS)
    shifted = {k: v + intro_offset_ms for k, v in fight["event_video_ms"].items()}
    _route_audio_for_events(fight["events"], shifted, mixer)
    # A KO stinger at the result-card boundary
    ko_at = int((INTRO_FRAMES + fight["n_frames"]) * RENDER_MS)
    ko_samp = _load_sfx_samples_or_none("ko", mixer.sr)
    if ko_samp is not None:
        mixer.hit_bus.add(ko_samp, ko_at)

    mixer.export(total_duration_ms, str(audio_out))
    mux_audio_video(str(raw_video), str(audio_out), str(final_mp4))

    return {
        "winner": winner_side,
        "winner_id": winner_id,
        "finished_by_ko": fight["terminated"],
        "duration_s": total_duration_ms / 1000.0,
        "mp4_path": final_mp4,
        "raw_path": raw_video,
        "audio_path": audio_out,
    }


def main(checkpoint: Path = DEFAULT_CKPT, max_seconds: float = 60.0,
          seed: int = 2000, left: str = "garen", right: str = "lux") -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))
    model = PPO.load(str(checkpoint))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = run_full_episode(model, OUT_DIR, left_id=left, right_id=right,
                               seed=seed, max_seconds=max_seconds,
                               episode_name="episode")
    print(f"Episode: {result['mp4_path']} ({result['duration_s']:.1f}s) "
          f"winner={result['winner_id']}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--max_seconds", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=2000)
    p.add_argument("--left", type=str, default="garen")
    p.add_argument("--right", type=str, default="lux")
    args = p.parse_args()
    main(checkpoint=args.checkpoint, max_seconds=args.max_seconds,
          seed=args.seed, left=args.left, right=args.right)
