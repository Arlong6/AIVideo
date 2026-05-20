"""Load a trained PPO checkpoint, render a self-play fight as mp4.

Stage 3: visual richness — textured floor, back-wall lines, character shadows,
HP/MP HUD, impact bursts, landing dust, screen shake, projectile particles
for cooldown attacks, and skill / ultimate banners.
"""
from __future__ import annotations
import argparse
import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402
from stable_baselines3 import PPO  # noqa: E402

from pixel_battle.rl.env import PixelBattleEnv  # noqa: E402
from pixel_battle.rl.stick_renderer import (  # noqa: E402
    draw_stick_figure,
    ProjectileLayer,
    spawn_impact_burst,
    spawn_landing_dust,
)
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


# ── HUD font cache ────────────────────────────────────────────────────────────
_HUD_FONT_CACHE: dict = {}


def _get_hud_font(size: int = 14) -> pygame.font.Font:
    """Lazily create/cache a bold arial font of the given size.

    Defensive about pygame.font init — calling _get_hud_font before pygame.init()
    still works (we call pygame.font.init() ourselves).
    """
    if not pygame.font.get_init():
        pygame.font.init()
    f = _HUD_FONT_CACHE.get(size)
    if f is None:
        f = pygame.font.SysFont("arial", size, bold=True)
        _HUD_FONT_CACHE[size] = f
    return f


# ── Background / arena helpers ────────────────────────────────────────────────

def _draw_back_wall(surf: pygame.Surface) -> None:
    """Draw decorative diagonal lines in the upper background to suggest a stage."""
    wall_color = (40, 50, 80)
    for x in range(-100, WIDTH + 100, 100):
        pygame.draw.line(surf, wall_color, (x, 0), (x + 80, 200), 1)


def _draw_floor(surf: pygame.Surface) -> None:
    """Thicker ground band + horizontal hatch lines for parallax feel."""
    pygame.draw.rect(surf, (28, 34, 56), (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y))
    pygame.draw.line(surf, (90, 110, 170), (0, GROUND_Y), (WIDTH, GROUND_Y), 3)
    # Hatch — two staggered rows of short segments
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
    w = int(36 * scale)
    h = int(6 * scale)
    if w < 6 or h < 2:
        return
    shadow = pygame.Surface((w * 2, h * 2), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0, 0, 0, 110), (0, 0, w * 2, h * 2))
    surf.blit(shadow, (int(char.pos_x) - w, ground - h))


# ── HUD ───────────────────────────────────────────────────────────────────────

def _draw_hud(surf: pygame.Surface, env) -> None:
    """Two-corner HUD — name, HP, MP."""
    _draw_player_hud(surf, env.left, RED, x=12, name="BRICK")
    _draw_player_hud(surf, env.right, BLUE, x=WIDTH - 12 - 200, name="GLASS",
                      right_align=True)


def _draw_player_hud(surf: pygame.Surface, char, color, x: int, name: str,
                      right_align: bool = False) -> None:
    bar_w = 200
    bar_h = 14
    y = 16
    # Name label
    font = _get_hud_font(14)
    name_surf = font.render(name, True, (240, 240, 255))
    if right_align:
        surf.blit(name_surf, (x + bar_w - name_surf.get_width(), y - 16))
    else:
        surf.blit(name_surf, (x, y - 16))
    # HP background
    pygame.draw.rect(surf, (40, 40, 50), (x, y, bar_w, bar_h))
    # HP fill
    hp_frac = max(0.0, char.hp / max(1, getattr(char, "hp_max", 100)))
    fill_w = int(bar_w * hp_frac)
    if right_align:
        pygame.draw.rect(surf, color, (x + bar_w - fill_w, y, fill_w, bar_h))
    else:
        pygame.draw.rect(surf, color, (x, y, fill_w, bar_h))
    # HP outline
    pygame.draw.rect(surf, (210, 210, 230), (x, y, bar_w, bar_h), 1)
    # MP bar (slimmer, below HP)
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
    """Centered banner near top — used for skill names and ULTIMATE!."""
    font = _get_hud_font(22)
    text_surf = font.render(text, True, (255, 240, 120))
    rect = text_surf.get_rect(center=(WIDTH // 2, 70))
    plate = pygame.Surface((rect.width + 24, rect.height + 12), pygame.SRCALPHA)
    plate.fill((0, 0, 0, 180))
    surf.blit(plate, (rect.x - 12, rect.y - 6))
    surf.blit(text_surf, rect)


# ── Audio routing (unchanged from before) ─────────────────────────────────────

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


# ── Main match driver ────────────────────────────────────────────────────────

def run_one_match(model, seed: int, out_dir: Path,
                   max_seconds: float = 60.0,
                   match_name: str = "final") -> dict:
    """Run a single self-play match. Returns:
        {"finished_by_ko": bool,
         "duration_s": float,
         "winner": "left"|"right"|None,
         "mp4_path": Path,
         "raw_path": Path,
         "audio_path": Path}
    The mp4 is written to out_dir/{match_name}.mp4. Caller decides whether
    to keep or discard based on finished_by_ko.
    Assumes pygame is already initialized (caller's responsibility).
    """
    # Defensive font init (pygame.init() also does it, but be explicit)
    if not pygame.font.get_init():
        pygame.font.init()

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_video = out_dir / f"{match_name}_raw.mp4"
    audio_out = out_dir / f"{match_name}_audio.wav"
    final_mp4 = out_dir / f"{match_name}.mp4"

    env = PixelBattleEnv(seed=seed)
    (obs_left, obs_right), _ = env.reset()

    recorder = FrameRecorder(str(raw_video), fps=FPS,
                              width=WIDTH, height=HEIGHT)
    recorder.start()
    mixer = AudioMixer(sample_rate=48000)

    surf = pygame.Surface((WIDTH, HEIGHT))
    total_frames = int(max_seconds * FPS)
    event_video_ms: dict = {}
    terminated = False
    frame = 0

    # Cross-frame visual state
    projectiles = ProjectileLayer()
    screen_shake_frames_left = 0
    banner_text = None
    banner_until_frame = -1
    flash_frames_left = 0
    prev_on_ground_left = env.left.on_ground
    prev_on_ground_right = env.right.on_ground

    # Lazy import (only here so module-level import surface stays clean)
    import random

    for frame in range(total_frames):
        left_act, _ = model.predict(obs_left, deterministic=False)
        right_act, _ = model.predict(obs_right, deterministic=False)

        prev_ev_n = len(env.battle.events)
        (obs_left, obs_right), _, terminated, truncated, _ = env.step(
            (int(left_act), int(right_act))
        )

        # ── Per-frame visual state from new events ──────────────────────────
        pending_bursts: list = []
        for ev in env.battle.events[prev_ev_n:]:
            event_video_ms[id(ev)] = int(frame * FRAME_MS)
            et = ev.type.value
            if et == "hit":
                defender = env.right if ev.target == env.right.id else env.left
                attacker = env.left if ev.actor == env.left.id else env.right
                is_crit = bool((ev.extra or {}).get("crit", False))
                burst_size = 28 if is_crit else 20
                burst_color = RED if attacker is env.left else BLUE
                pending_bursts.append((
                    int(defender.pos_x),
                    int(defender.pos_y) - 40,
                    burst_color,
                    burst_size,
                ))
                screen_shake_frames_left = max(screen_shake_frames_left, 5)
            elif et == "crit":
                defender = env.right if ev.target == env.right.id else env.left
                attacker = env.left if ev.actor == env.left.id else env.right
                burst_color = RED if attacker is env.left else BLUE
                pending_bursts.append((
                    int(defender.pos_x),
                    int(defender.pos_y) - 40,
                    burst_color,
                    32,
                ))
                screen_shake_frames_left = max(screen_shake_frames_left, 7)
            elif et == "attack_windup":
                kind = (ev.extra or {}).get("skill_type")
                actor_obj = env.left if ev.actor == env.left.id else env.right
                target_obj = env.right if actor_obj is env.left else env.left
                if kind == "cooldown":
                    shoulder_y = int(actor_obj.pos_y) - 60
                    target_y = int(target_obj.pos_y) - 30
                    color = RED if actor_obj is env.left else BLUE
                    projectiles.spawn(
                        start=(int(actor_obj.pos_x), shoulder_y),
                        end=(int(target_obj.pos_x), target_y),
                        color=color,
                        current_ms=int(frame * FRAME_MS),
                        duration_ms=280,
                    )
                if kind in ("cooldown", "special"):
                    skill_id = (ev.extra or {}).get("skill_id", "?")
                    banner_text = str(skill_id).upper().replace("_", " ") + "!"
                    banner_until_frame = frame + 36  # ~600ms at 60fps
            elif et == "ultimate_start":
                banner_text = "ULTIMATE!"
                banner_until_frame = frame + 90  # ~1500ms
                flash_frames_left = 9              # ~150ms

        # ── Landing dust: ground-touch edge detection ───────────────────────
        pending_dust: list = []
        if env.left.on_ground and not prev_on_ground_left:
            pending_dust.append((int(env.left.pos_x), int(env.left.pos_y)))
        if env.right.on_ground and not prev_on_ground_right:
            pending_dust.append((int(env.right.pos_x), int(env.right.pos_y)))
        prev_on_ground_left = env.left.on_ground
        prev_on_ground_right = env.right.on_ground

        # ── Draw frame ──────────────────────────────────────────────────────
        surf.fill(BG)
        _draw_back_wall(surf)
        _draw_floor(surf)

        _draw_shadow(surf, env.left)
        _draw_shadow(surf, env.right)

        draw_stick_figure(surf, env.left, RED)
        draw_stick_figure(surf, env.right, BLUE)

        projectiles.draw(surf, int(frame * FRAME_MS))

        for (bx, by, bcolor, bsize) in pending_bursts:
            spawn_impact_burst(surf, bx, by, bcolor, bsize)

        for (dx, dy) in pending_dust:
            spawn_landing_dust(surf, dx, dy, (180, 180, 200), intensity=1.0)

        if flash_frames_left > 0:
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 100))
            surf.blit(flash, (0, 0))
            flash_frames_left -= 1

        _draw_hud(surf, env)

        if banner_text is not None and frame <= banner_until_frame:
            _draw_banner(surf, banner_text)
        elif banner_text is not None and frame > banner_until_frame:
            banner_text = None

        # ── Screen shake: copy into a jittered buffer ───────────────────────
        if screen_shake_frames_left > 0:
            ox = random.randint(-2, 2)
            oy = random.randint(-2, 2)
            shaken = pygame.Surface((WIDTH, HEIGHT))
            shaken.fill(BG)
            shaken.blit(surf, (ox, oy))
            recorder.write_frame(shaken)
            screen_shake_frames_left -= 1
        else:
            recorder.write_frame(surf)

        if terminated:
            for _ in range(120):  # 2s hold on the last drawn frame
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

    # Determine winner
    if terminated:
        if env.right.is_ko() and not env.left.is_ko():
            winner = "left"
        elif env.left.is_ko() and not env.right.is_ko():
            winner = "right"
        else:
            winner = None
    else:
        winner = None

    return {
        "finished_by_ko": bool(terminated),
        "duration_s": total_duration_ms / 1000.0,
        "winner": winner,
        "mp4_path": final_mp4,
        "raw_path": raw_video,
        "audio_path": audio_out,
    }


def main(checkpoint: Path = DEFAULT_CKPT, max_seconds: float = 60.0,
          seed: int = 1234):
    pygame.init()
    pygame.display.set_mode((1, 1))
    model = PPO.load(str(checkpoint))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    result = run_one_match(model, seed=seed, out_dir=OUT_DIR,
                            max_seconds=max_seconds, match_name="final")
    print(f"RL play: {result['mp4_path']} ({result['duration_s']:.1f}s)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    p.add_argument("--max_seconds", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=1234)
    args = p.parse_args()
    main(checkpoint=args.checkpoint,
          max_seconds=args.max_seconds, seed=args.seed)
