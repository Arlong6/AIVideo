"""Pygame Surface painter. Pure rendering — no battle logic.

Designed for headless use (SDL_VIDEODRIVER=dummy) so it can run in CI/tests.
"""
from enum import Enum

import pygame

from pixel_battle.engine.character import Character


class AnimationState(Enum):
    IDLE = "idle"
    WALKING = "walking"   # NEW — character moving
    JUMPING = "jumping"   # NEW — character airborne
    ATTACK = "attack"
    HIT = "hit"
    KO = "ko"

WIDTH = 480
HEIGHT = 854
BG_COLOR = (15, 18, 28)
# HORIZON_Y is the ground/feet line — import from physics to keep in sync
from pixel_battle.engine.physics import GROUND_Y as HORIZON_Y  # noqa: E402


def _build_arena_bg(width: int, height: int) -> pygame.Surface:
    """Vertical gradient sky + ground plane. Built once at Renderer init."""
    bg = pygame.Surface((width, height))
    # Sky: deep navy at top → warm purple at horizon
    for y in range(HORIZON_Y):
        t = y / HORIZON_Y
        r = int(15 + (95 - 15) * t)
        g = int(18 + (45 - 18) * t)
        b = int(40 + (90 - 40) * t)
        pygame.draw.line(bg, (r, g, b), (0, y), (width, y))
    # Ground: brown-orange at horizon → darker at bottom
    for y in range(HORIZON_Y, height):
        t = (y - HORIZON_Y) / max(1, height - HORIZON_Y)
        r = int(80 - 30 * t)
        g = int(50 - 25 * t)
        b = int(40 - 25 * t)
        pygame.draw.line(bg, (r, g, b), (0, y), (width, y))
    # Horizon line accent
    pygame.draw.line(bg, (180, 100, 60), (0, HORIZON_Y), (width, HORIZON_Y), 2)
    return bg
HP_BAR_BG = (60, 60, 60)
HP_BAR_FG = (200, 50, 50)
MP_BAR_FG = (60, 130, 230)
BAR_HEIGHT = 12
PAD = 18
CHAR_W = 110
CHAR_H = 160

# Map AnimationState to animator AnimClip
_ANIM_STATE_TO_CLIP = None  # populated lazily to avoid circular imports at module level


def _get_clip_map():
    global _ANIM_STATE_TO_CLIP
    if _ANIM_STATE_TO_CLIP is None:
        from pixel_battle.engine.animator import AnimClip
        _ANIM_STATE_TO_CLIP = {
            AnimationState.IDLE: AnimClip.IDLE,
            AnimationState.WALKING: AnimClip.WALK,
            AnimationState.JUMPING: AnimClip.JUMP,
            AnimationState.ATTACK: AnimClip.ATTACK,
            AnimationState.HIT: AnimClip.HIT,
            AnimationState.KO: AnimClip.KO,
        }
    return _ANIM_STATE_TO_CLIP


BAR_LERP_RATE = 0.18  # per-frame fraction toward target; ~15 frames to converge


class Renderer:
    def __init__(self):
        if not pygame.get_init():
            pygame.init()
        self.surface = pygame.Surface((WIDTH, HEIGHT))
        self._sprite_cache: dict = {}
        self._arena_bg = _build_arena_bg(WIDTH, HEIGHT)
        # Per-character displayed bar values for smooth lerp toward actual hp/mp
        self._displayed_stats: dict[str, dict[str, float]] = {}
        # Screen shake budget — decays each frame
        self._shake_intensity = 0.0
        # Per-character white flash budget — decays each frame
        self._char_flash: dict[str, float] = {}
        # Particle system
        from pixel_battle.engine.particles import ParticleSystem
        self.particles = ParticleSystem()
        # Hit-stop: freeze frame count
        self.hit_stop_frames = 0

    def _smooth_value(self, char_id: str, key: str, target: float,
                      rate: float = BAR_LERP_RATE) -> float:
        stats = self._displayed_stats.setdefault(char_id, {})
        current = stats.get(key, target)
        new = current + (target - current) * rate
        if abs(target - new) < 0.5:
            new = float(target)
        stats[key] = new
        return new

    def _get_sprites(self, char_id: str):
        if char_id not in self._sprite_cache:
            from pixel_battle.engine.animator import CharacterSprites
            self._sprite_cache[char_id] = CharacterSprites(char_id)
        return self._sprite_cache[char_id]

    # ------------------------------------------------------------------ #
    # Screen shake                                                          #
    # ------------------------------------------------------------------ #

    def add_shake(self, intensity: float) -> None:
        self._shake_intensity = max(self._shake_intensity, intensity)

    def _apply_shake(self) -> None:
        if self._shake_intensity < 0.5:
            self._shake_intensity = 0.0
            return
        import random
        dx = int((random.random() - 0.5) * 2 * self._shake_intensity)
        dy = int((random.random() - 0.5) * 2 * self._shake_intensity)
        # Shift content by (dx, dy): copy, fill with bg, re-blit shifted
        temp = self.surface.copy()
        self.surface.blit(self._arena_bg, (0, 0))
        self.surface.blit(temp, (dx, dy))
        self._shake_intensity *= 0.85  # decay

    # ------------------------------------------------------------------ #
    # Character hit flash                                                   #
    # ------------------------------------------------------------------ #

    def add_char_flash(self, char_id: str, intensity: float = 1.0) -> None:
        self._char_flash[char_id] = max(self._char_flash.get(char_id, 0.0), intensity)

    def request_hit_stop(self, frames: int) -> None:
        self.hit_stop_frames = max(self.hit_stop_frames, frames)

    # ------------------------------------------------------------------ #
    # Public render methods                                                 #
    # ------------------------------------------------------------------ #

    def render_static(self, left: Character, right: Character) -> None:
        """Paint a frame with both characters in idle pose + HP/MP bars."""
        self.surface.blit(self._arena_bg, (0, 0))
        self._draw_bars(left, x=PAD, top=PAD)
        self._draw_bars(right, x=WIDTH - PAD - self._bar_width(), top=PAD)
        self._draw_character(left, center_x=WIDTH // 4, center_y=HEIGHT // 2)
        self._draw_character(right, center_x=WIDTH * 3 // 4, center_y=HEIGHT // 2)

    def _bar_width(self) -> int:
        return (WIDTH - 3 * PAD) // 2

    def _draw_bars(self, char: Character, x: int, top: int) -> None:
        bw = self._bar_width()
        displayed_hp = self._smooth_value(char.id, "hp", float(char.hp))
        displayed_mp = self._smooth_value(char.id, "mp", float(char.mp))
        displayed_alive = self._smooth_value(char.id, "alive",
                                              0.0 if char.is_ko() else 1.0,
                                              rate=0.10)

        if displayed_alive < 0.02:
            return  # fully faded — skip drawing

        # Render bars onto a temporary SRCALPHA surface for unified alpha control
        bar_h = BAR_HEIGHT + 4 + (BAR_HEIGHT - 4)
        layer = pygame.Surface((bw, bar_h), pygame.SRCALPHA)

        # HP bar
        pygame.draw.rect(layer, HP_BAR_BG, (0, 0, bw, BAR_HEIGHT))
        pygame.draw.rect(layer, HP_BAR_FG,
                         (0, 0, int(bw * displayed_hp / 100), BAR_HEIGHT))

        # MP bar
        mp_top = BAR_HEIGHT + 4
        pygame.draw.rect(layer, HP_BAR_BG, (0, mp_top, bw, BAR_HEIGHT - 4))
        mp_fill = int(bw * (displayed_mp / char.mp_max))
        pygame.draw.rect(layer, MP_BAR_FG, (0, mp_top, mp_fill, BAR_HEIGHT - 4))

        # MP full pulse — glow rim + "ULT!" text
        if displayed_mp >= char.mp_max - 1 and displayed_alive > 0.5:
            pulse = (pygame.time.get_ticks() % 600) / 600.0  # 0-1
            if pulse < 0.5:
                glow_alpha = int(200 * (pulse * 2))
            else:
                glow_alpha = int(200 * (2 - pulse * 2))
            rim_w = bw + 6
            rim_h = BAR_HEIGHT - 4 + 6
            rim = pygame.Surface((rim_w, rim_h), pygame.SRCALPHA)
            pygame.draw.rect(rim, (100, 200, 255, glow_alpha),
                             (0, 0, rim_w, rim_h), border_radius=4)
            layer.blit(rim, (-3, mp_top - 3))
            # "ULT!" label
            if not hasattr(self, "_ult_font"):
                if not pygame.font.get_init():
                    pygame.font.init()
                self._ult_font = pygame.font.Font(None, 18)
            ult_text = self._ult_font.render("ULT!", True, (255, 220, 80))
            layer.blit(ult_text, (bw - ult_text.get_width() - 2, mp_top - 2))

        layer.set_alpha(int(255 * displayed_alive))
        self.surface.blit(layer, (x, top))

    def _draw_character(self, char: Character, center_x: int, center_y: int) -> None:
        """Backward-compat rectangle fallback (used by render_static and tests)."""
        x = center_x - CHAR_W // 2
        y = center_y - CHAR_H // 2
        pygame.draw.rect(self.surface, char.color, (x, y, CHAR_W, CHAR_H), border_radius=10)
        sw, sh = CHAR_W - 24, CHAR_H - 60
        pygame.draw.rect(
            self.surface, char.accent_color,
            (x + 12, y + 20, sw, sh), border_radius=4,
        )

    def render_frame(
        self,
        left: Character,
        right: Character,
        left_anim: AnimationState,
        right_anim: AnimationState,
        anim_frame: int,
    ) -> None:
        """Paint a frame with per-character animation state using sprites.

        Uses character world positions (pos_x, pos_y) if set (physics mode),
        otherwise falls back to fixed lane positions (legacy mode for intro screen).
        """
        self.surface.blit(self._arena_bg, (0, 0))
        self._draw_bars(left, x=PAD, top=PAD)
        self._draw_bars(right, x=WIDTH - PAD - self._bar_width(), top=PAD)

        # Use world positions if physics has been initialized (pos_x != 0),
        # else fall back to fixed center positions for backward compatibility.
        if left.pos_x != 0.0:
            left_x = int(left.pos_x)
            left_y = int(left.pos_y)
        else:
            left_x = WIDTH // 4
            left_y = HORIZON_Y

        if right.pos_x != 0.0:
            right_x = int(right.pos_x)
            right_y = int(right.pos_y)
        else:
            right_x = WIDTH * 3 // 4
            right_y = HORIZON_Y

        self._draw_sprite_char(left, left_x, left_y, left_anim, anim_frame,
                               facing_right=(left.facing == 1))
        self._draw_sprite_char(right, right_x, right_y, right_anim, anim_frame,
                               facing_right=(right.facing == 1))
        self.particles.update()
        self.particles.render(self.surface)
        # Apply screen shake last (after all content is drawn)
        self._apply_shake()

    def _draw_sprite_char(
        self,
        char: Character,
        world_x: int,
        world_y: int,
        anim_state: AnimationState,
        anim_frame: int,
        facing_right: bool,
    ) -> None:
        """Draw character sprite with feet positioned at (world_x, world_y)."""
        from pixel_battle.engine.animator import resolve_pose
        clip_map = _get_clip_map()
        clip = clip_map.get(anim_state)
        if clip is None:
            # Unknown state — draw a fallback rectangle (center-based for compat)
            self._draw_character(char, world_x, world_y - CHAR_H // 2)
            return

        pose_name, _ = resolve_pose(clip, anim_frame)
        sprites = self._get_sprites(char.id)
        sprite = sprites.get_pose(pose_name)
        if not facing_right:
            sprite = pygame.transform.flip(sprite, True, False)
        # Use midbottom: world_y is the feet position, sprite extends upward
        rect = sprite.get_rect(midbottom=(world_x, world_y))
        self.surface.blit(sprite, rect)

        # White flash overlay — applied after blitting the sprite
        flash = self._char_flash.get(char.id, 0.0)
        if flash > 0.05:
            white_overlay = sprite.copy()
            arr = pygame.surfarray.pixels3d(white_overlay)
            arr[:] = 255  # fill RGB channels with white
            del arr  # release write lock before further surface operations
            white_overlay.set_alpha(int(180 * flash))
            self.surface.blit(white_overlay, rect)
            self._char_flash[char.id] = flash * 0.75  # decay

    # ------------------------------------------------------------------ #
    # Legacy rectangle painter — kept for backward compatibility            #
    # ------------------------------------------------------------------ #

    def _draw_anim_character(
        self, char: Character, center_x: int, center_y: int,
        anim: AnimationState, anim_frame: int, facing_right: bool,
    ) -> None:
        """Original rectangle-based animated character (kept for compat)."""
        dx, dy = 0, 0
        w, h = CHAR_W, CHAR_H
        if anim is AnimationState.IDLE:
            dy = -2 if (anim_frame // 4) % 2 == 0 else 2
        elif anim is AnimationState.ATTACK:
            lunge = 20 * (1 - abs(4 - anim_frame) / 4)
            dx = int(lunge) * (1 if facing_right else -1)
        elif anim is AnimationState.HIT:
            dx = (-1 if facing_right else 1) * (6 if anim_frame % 2 == 0 else -6)
        elif anim is AnimationState.KO:
            w, h = CHAR_H, CHAR_W
            dy = 60

        x = center_x - w // 2 + dx
        y = center_y - h // 2 + dy
        pygame.draw.rect(self.surface, char.color, (x, y, w, h), border_radius=10)
        sw, sh = w - 24, h - 60
        pygame.draw.rect(
            self.surface, char.accent_color,
            (x + 12, y + 20, sw, sh), border_radius=4,
        )
