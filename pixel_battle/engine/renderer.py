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
HP_BAR_BG = (60, 60, 60)
HP_BAR_FG = (200, 50, 50)
MP_BAR_FG = (60, 130, 230)
BAR_HEIGHT = 12
PAD = 18
CHAR_W = 110
CHAR_H = 160


class Renderer:
    def __init__(self):
        if not pygame.get_init():
            pygame.init()
        self.surface = pygame.Surface((WIDTH, HEIGHT))

    def render_static(self, left: Character, right: Character) -> None:
        """Paint a frame with both characters in idle pose + HP/MP bars."""
        self.surface.fill(BG_COLOR)
        self._draw_bars(left, x=PAD, top=PAD)
        self._draw_bars(right, x=WIDTH - PAD - self._bar_width(), top=PAD)
        self._draw_character(left, center_x=WIDTH // 4, center_y=HEIGHT // 2)
        self._draw_character(right, center_x=WIDTH * 3 // 4, center_y=HEIGHT // 2)

    def _bar_width(self) -> int:
        return (WIDTH - 3 * PAD) // 2

    def _draw_bars(self, char: Character, x: int, top: int) -> None:
        bw = self._bar_width()
        pygame.draw.rect(self.surface, HP_BAR_BG, (x, top, bw, BAR_HEIGHT))
        fill = int(bw * (char.hp / 100))
        pygame.draw.rect(self.surface, HP_BAR_FG, (x, top, fill, BAR_HEIGHT))
        mp_top = top + BAR_HEIGHT + 4
        pygame.draw.rect(self.surface, HP_BAR_BG, (x, mp_top, bw, BAR_HEIGHT - 4))
        mp_fill = int(bw * (char.mp / char.mp_max))
        pygame.draw.rect(self.surface, MP_BAR_FG, (x, mp_top, mp_fill, BAR_HEIGHT - 4))

    def _draw_character(self, char: Character, center_x: int, center_y: int) -> None:
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
        """Paint a frame with per-character animation state."""
        self.surface.fill(BG_COLOR)
        self._draw_bars(left, x=PAD, top=PAD)
        self._draw_bars(right, x=WIDTH - PAD - self._bar_width(), top=PAD)
        self._draw_anim_character(left, center_x=WIDTH // 4, center_y=HEIGHT // 2,
                                  anim=left_anim, anim_frame=anim_frame, facing_right=True)
        self._draw_anim_character(right, center_x=WIDTH * 3 // 4, center_y=HEIGHT // 2,
                                  anim=right_anim, anim_frame=anim_frame, facing_right=False)

    def _draw_anim_character(
        self, char: Character, center_x: int, center_y: int,
        anim: AnimationState, anim_frame: int, facing_right: bool,
    ) -> None:
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
