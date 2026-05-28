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
from pixel_battle.engine.physics import GROUND_Y  # noqa: E402


WIDTH, HEIGHT = 480, 854
FPS = 60
FRAME_MS = 1000.0 / FPS
RENDER_FPS = 120          # output frame rate (doubled for sub-frame smoothness)
RENDER_MS = 1000.0 / RENDER_FPS   # 8.333 ms per render frame
ENGINE_HZ = 60            # engine tick rate (unchanged)
ENGINE_MS = 1000.0 / ENGINE_HZ    # 16.667 ms per engine tick
HIT_FLASH = (255, 255, 255)   # color a fighter flashes to when struck
BG = (18, 22, 40)
# GROUND_Y is imported from the physics engine — the renderer MUST use the
# same feet-landing line the simulation uses, or the camera and floor will
# be offset from where the fighters actually stand.

# Camera — zoom + horizontal follow so fighters fill the vertical frame
# instead of sitting tiny in the bottom strip. The world is drawn at native
# size, then a sub-region is cropped + upscaled to the output resolution.
CAM_ZOOM = 1.0             # whole arena in frame — best for reading long-range kiting
CAM_VIEW_W = int(WIDTH / CAM_ZOOM)            # 480 — horizontal world span shown
CAM_VIEW_H = int(HEIGHT / CAM_ZOOM)           # 854 — vertical world span shown
CAM_VIEW_Y = GROUND_Y - int(CAM_VIEW_H * 0.82)  # frame the floor ~82% down
CAM_FOLLOW = 0.12                              # lerp factor for x tracking

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


# ── Background / arena helpers ────────────────────────────────────────────────

def _draw_back_wall(surf: pygame.Surface) -> None:
    """Fill the area above the floor: vertical gradient + diagonal accent lines."""
    for i in range(0, GROUND_Y, 6):
        t = i / GROUND_Y
        c = (int(18 + 12 * t), int(22 + 14 * t), int(40 + 20 * t))
        pygame.draw.rect(surf, c, (0, i, WIDTH, 6))
    wall_color = (46, 56, 88)
    for x in range(-240, WIDTH + 240, 120):
        pygame.draw.line(surf, wall_color, (x, 0), (x + 260, GROUND_Y), 2)


def _draw_floor(surf: pygame.Surface) -> None:
    """Thicker ground band + horizontal hatch lines for parallax feel."""
    pygame.draw.rect(surf, (28, 34, 56), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
    pygame.draw.line(surf, (90, 110, 170), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
    for x in range(0, WIDTH, 40):
        pygame.draw.line(surf, (50, 60, 95), (x, GROUND_Y + 8),
                          (x + 20, GROUND_Y + 8), 1)
    for x in range(20, WIDTH, 40):
        pygame.draw.line(surf, (50, 60, 95), (x, GROUND_Y + 22),
                          (x + 20, GROUND_Y + 22), 1)


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
    """Whirling blades around the caster — Garen's Judgment, etc."""
    t = age / max(1, life)
    if t >= 1.0:
        return
    radius = int(46 + 28 * t)
    n = 6
    for i in range(n):
        ang = age * 0.55 + i * (2 * math.pi / n)
        ix = cx + math.cos(ang) * radius * 0.35
        iy = cy + math.sin(ang) * radius * 0.35
        ox = cx + math.cos(ang) * radius
        oy = cy + math.sin(ang) * radius
        pygame.draw.line(surf, color, (int(ix), int(iy)), (int(ox), int(oy)), 5)
    ring = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
    pygame.draw.circle(ring, (*color, int(95 * (1.0 - t))),
                       (radius + 4, radius + 4), radius, 3)
    surf.blit(ring, (cx - radius - 4, cy - radius - 4))


def _draw_aura(surf: pygame.Surface, cx: int, cy: int, color: tuple,
                age: int, life: int) -> None:
    """A pulsing buff aura on the caster — concentric expanding rings."""
    t = age / max(1, life)
    if t >= 1.0:
        return
    for k in range(3):
        rt = (t * 1.4 + k * 0.33) % 1.0
        radius = int(18 + 64 * rt)
        alpha = int(170 * (1.0 - rt) * (1.0 - t))
        if alpha <= 0:
            continue
        ring = pygame.Surface((radius * 2 + 8, radius * 2 + 8), pygame.SRCALPHA)
        pygame.draw.circle(ring, (*color, alpha),
                           (radius + 4, radius + 4), radius, 4)
        surf.blit(ring, (cx - radius - 4, cy - radius - 4))


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
    _draw_back_wall(surf)
    _draw_floor(surf)

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
    _draw_back_wall(surf)
    _draw_floor(surf)

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
                   max_seconds: float, end_hold_frames: int = 0) -> dict:
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
    from pixel_battle.engine.battle import BattleState as _BattleState
    from pixel_battle.engine.skill import SkillType as _SkillType

    (obs_left, obs_right), _ = env.reset()
    lcol = _char_color(env.left)
    rcol = _char_color(env.right)

    hud_overlay = _HUD()
    impact_fx = _ImpactFX()
    ko_seq = _KOSequence()

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
    BEAM_LIFE, SPIN_LIFE, AURA_LIFE = 10, 16, 18
    prev_on_ground_left = env.left.on_ground
    prev_on_ground_right = env.right.on_ground
    cam_x = (env.left.pos_x + env.right.pos_x) / 2.0
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
                # Drive the battle engine directly with the scaled dt
                env.battle.tick_ms(effective_dt, skip_ai=False)
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
                    burst_size = 78 if is_crit else 52
                    burst_color = lcol if attacker is env.left else rcol
                    active_bursts.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, burst_size, 0,
                    ])
                    if defender is env.left:
                        left_flash_frames = max(left_flash_frames, 8)
                    else:
                        right_flash_frames = max(right_flash_frames, 8)
                    # ── Camera shake on hit ──
                    if is_crit:
                        impact_fx.camera_shake.trigger(magnitude_px=5.0, duration_ms=200.0)
                    else:
                        impact_fx.camera_shake.trigger(magnitude_px=2.0, duration_ms=120.0)
                    # ── Hit-confirm ring at defender's hip ──
                    impact_fx.spawn_hit_ring(
                        x=int(defender.pos_x),
                        y=int(defender.pos_y) - 60,
                        color=burst_color)
                    # ── Attacker recoil: mark near-hand kick-back for 100 ms ──
                    _attacker_recoil[id(attacker)] = 100
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
                    if vfx == "bolt":
                        projectiles.spawn(start=(ax, ay - 130), end=(tx, ty - 90),
                                           color=a_color, current_ms=now_ms,
                                           duration_ms=280)
                    elif vfx == "multishot":
                        for off in (-44, -22, 0, 22, 44):
                            projectiles.spawn(start=(ax, ay - 110),
                                               end=(tx, ty - 90 + off),
                                               color=a_color, current_ms=now_ms,
                                               duration_ms=300)
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
                        active_bursts.append([ax, ay - 90, a_color, 40, 0])
                        # New: dash afterimage from caster toward target
                        impact_fx.spawn_dash_afterimage(
                            sx=float(ax), sy=float(ay),
                            ex=float(tx), ey=float(ty),
                            color=a_color)
                    elif vfx == "slam":
                        active_shockwaves.append([tx, ty - 90, a_color, 0, 16, 300])
                    kind = (ev.extra or {}).get("skill_type")
                    if kind in ("cooldown", "special"):
                        skill_id = (ev.extra or {}).get("skill_id", "?")
                        banner_text = str(skill_id).upper().replace("_", " ") + "!"
                        banner_until_frame = frame + 72   # doubled: was 36 @ 60fps
                        # Charge orb at caster's near-hand height (shoulder ~-130 px)
                        impact_fx.spawn_charge_orb(
                            x=ax, y=ay - 130, color=brand_col,
                            lifetime_ms=150, scale=1.0)
                elif et == "ultimate_start":
                    banner_text = "ULTIMATE!"
                    banner_until_frame = frame + 156   # doubled: was 78 @ 60fps
                    flash_frames_left = 20             # doubled: was 10 @ 60fps
                    defender = env.right if ev.target == env.right.id else env.left
                    actor_obj = env.left if ev.actor == env.left.id else env.right
                    burst_color = lcol if actor_obj is env.left else rcol
                    brand_col_ult = getattr(actor_obj, "brand_color",
                                            getattr(actor_obj, "color", burst_color))
                    active_bursts.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, 120, 0,
                    ])
                    active_bursts.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        (255, 240, 120), 80, 0,
                    ])
                    # Two screen-filling shockwave rings — the ultimate's "炸裂"
                    active_shockwaves.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        (255, 240, 150), 0, 20, 460,
                    ])
                    active_shockwaves.append([
                        int(defender.pos_x), int(defender.pos_y) - 90,
                        burst_color, 0, 24, 520,
                    ])
                    screen_shake_frames_left = max(screen_shake_frames_left, 32)  # doubled
                    screen_shake_mag = max(screen_shake_mag, 11)
                    if defender is env.left:
                        left_flash_frames = max(left_flash_frames, 14)  # doubled
                    else:
                        right_flash_frames = max(right_flash_frames, 14)
                    # ── NEW: ultimate burst (flash + 30 sparks + text) ──
                    impact_fx.spawn_ultimate_burst(
                        x=int(actor_obj.pos_x),
                        y=int(actor_obj.pos_y) - 60,
                        color=brand_col_ult,
                        surf_size=(WIDTH, HEIGHT))
                    # Larger camera shake via CameraShake helper
                    impact_fx.camera_shake.trigger(magnitude_px=5.0, duration_ms=200.0)
                    # ── Ultimate slow-mo: short, single beat (no stack from spam) ──
                    _slowmo_remaining_ms = max(_slowmo_remaining_ms, 80.0)
                    _slowmo_dt_scale = 0.4
                    # Ultimate charge orb — 2× scale with rising particle column
                    impact_fx.spawn_charge_orb(
                        x=int(actor_obj.pos_x), y=int(actor_obj.pos_y) - 130,
                        color=brand_col_ult, lifetime_ms=300, scale=2.0)
                    ult_vfx = (ev.extra or {}).get("vfx", "slam")
                    u_ax, u_ay = int(actor_obj.pos_x), int(actor_obj.pos_y)
                    u_tx, u_ty = int(defender.pos_x), int(defender.pos_y)
                    if ult_vfx == "beam":
                        bx = u_tx + (u_tx - u_ax) // 2
                        active_beams.append([u_ax, u_ay - 95, bx, u_ty - 95,
                                             (255, 255, 255), 0])
                        active_beams.append([u_ax, u_ay - 95, bx, u_ty - 95,
                                             burst_color, 0])
                        impact_fx.spawn_beam_fx(x1=u_ax, x2=bx, y=u_ay - 95,
                                                 color=brand_col_ult)
                    elif ult_vfx == "bolt":
                        projectiles.spawn(start=(u_ax, u_ay - 130),
                                           end=(u_tx, u_ty - 90),
                                           color=burst_color,
                                           current_ms=int(frame * RENDER_MS),
                                           duration_ms=240)
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

        # KO sequence — drives slow-mo + zoom once battle.state == KO
        ko_active = env.battle.state == _BattleState.KO
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
        _draw_back_wall(world)
        _draw_floor(world)

        # Temporarily override pos_x/pos_y with interpolated values for drawing only
        def _set_draw_pos(char, ix, iy):
            char._orig_pos_x, char._orig_pos_y = char.pos_x, char.pos_y
            char.pos_x, char.pos_y = ix, iy

        def _restore_draw_pos(char):
            char.pos_x, char.pos_y = char._orig_pos_x, char._orig_pos_y

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

            _draw_with_recoil(world, env.left, left_color,
                               opp_x=float(env.right.pos_x))
            _draw_with_recoil(world, env.right, right_color,
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

        # Camera — follow midpoint (biased toward loser during KO), crop + upscale
        # Use interpolated draw positions for smooth camera follow
        mid_x = (_draw_left_x + _draw_right_x) / 2.0
        if ko_result.zoom > 1.0:
            # Bias camera center toward the loser for dramatic framing
            mid_x = mid_x * 0.4 + ko_result.zoom_focus_x * 0.6
        cam_x += (mid_x - cam_x) * CAM_FOLLOW
        # Combine old crit-shake with new per-hit ImpactFX CameraShake
        sx0, sy0 = camera_shake_offset(shake_frames)
        sx1, sy1 = impact_fx.camera_shake.update(RENDER_MS)
        sx = sx0 + sx1
        sy = sy0 + sy1
        # KO zoom: tighter crop window so the loser fills more of the frame
        frame_zoom = ko_result.zoom * CAM_ZOOM
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

        _draw_hud(surf, env)

        # New KOF-style HUD (top bars + name plates + timer) and impact FX
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

        if terminated:
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
