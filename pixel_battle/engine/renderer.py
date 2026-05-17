"""Pygame Surface painter. Pure rendering — no battle logic.

Designed for headless use (SDL_VIDEODRIVER=dummy) so it can run in CI/tests.
"""
from enum import Enum

import pygame

from pixel_battle.engine.character import Character


class AnimationState(Enum):
    IDLE = "idle"
    ATTACK = "attack"
    HIT = "hit"
    KO = "ko"

WIDTH = 480
HEIGHT = 854
BG_COLOR = (15, 18, 28)
HORIZON_Y = int(HEIGHT * 0.62)


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
        # Lerp displayed bar values toward actual values for smooth drain/fill
        displayed_hp = self._smooth_value(char.id, "hp", float(char.hp))
        displayed_mp = self._smooth_value(char.id, "mp", float(char.mp))

        pygame.draw.rect(self.surface, HP_BAR_BG, (x, top, bw, BAR_HEIGHT))
        fill = int(bw * (displayed_hp / 100))
        pygame.draw.rect(self.surface, HP_BAR_FG, (x, top, fill, BAR_HEIGHT))
        mp_top = top + BAR_HEIGHT + 4
        pygame.draw.rect(self.surface, HP_BAR_BG, (x, mp_top, bw, BAR_HEIGHT - 4))
        mp_fill = int(bw * (displayed_mp / char.mp_max))
        pygame.draw.rect(self.surface, MP_BAR_FG, (x, mp_top, mp_fill, BAR_HEIGHT - 4))

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
        """Paint a frame with per-character animation state using sprites."""
        self.surface.blit(self._arena_bg, (0, 0))
        self._draw_bars(left, x=PAD, top=PAD)
        self._draw_bars(right, x=WIDTH - PAD - self._bar_width(), top=PAD)
        char_y = HORIZON_Y - 120  # feet at horizon, character extends up (~half of new ~320px char height)
        self._draw_sprite_char(left, WIDTH // 4, char_y, left_anim, anim_frame, facing_right=True)
        self._draw_sprite_char(right, WIDTH * 3 // 4, char_y, right_anim, anim_frame, facing_right=False)

    def _draw_sprite_char(
        self,
        char: Character,
        center_x: int,
        center_y: int,
        anim_state: AnimationState,
        anim_frame: int,
        facing_right: bool,
    ) -> None:
        from pixel_battle.engine.animator import resolve_pose
        clip_map = _get_clip_map()
        clip = clip_map.get(anim_state)
        if clip is None:
            # Unknown state — draw a fallback rectangle
            self._draw_character(char, center_x, center_y)
            return

        pose_name, _ = resolve_pose(clip, anim_frame)
        sprites = self._get_sprites(char.id)
        sprite = sprites.get_pose(pose_name)
        if not facing_right:
            sprite = pygame.transform.flip(sprite, True, False)
        rect = sprite.get_rect(center=(center_x, center_y))
        self.surface.blit(sprite, rect)

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
