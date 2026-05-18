"""HUD overlay: skill icons + DPS counter + damage popups + MP charge ring.

Pure rendering — owns no game logic. Driven by record_hit() calls from the
episode runner, plus reading Character state during render().
"""
from dataclasses import dataclass
from typing import List, Tuple

import math
import pygame

from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType


# ---------------------------------------------------------------------------
# Damage popup — floating "-N" text that scale-pops and drifts up
# ---------------------------------------------------------------------------


@dataclass
class DamagePopup:
    x: float
    y: float
    dmg: int
    is_crit: bool
    age: int = 0


class DamagePopupLayer:
    LIFETIME_FRAMES = 30
    RISE_PX = 60          # total upward drift over lifetime
    PEAK_SCALE = 1.4
    PEAK_FRAME = 6        # frames to reach peak scale, then settle

    def __init__(self):
        self.popups: List[DamagePopup] = []
        self._font: pygame.font.Font | None = None
        self._font_big: pygame.font.Font | None = None

    def _get_fonts(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 28)
            self._font_big = pygame.font.Font(None, 36)
        return self._font, self._font_big

    def spawn(self, x: float, y: float, dmg: int, is_crit: bool) -> None:
        self.popups.append(DamagePopup(x=x, y=y, dmg=dmg, is_crit=is_crit, age=0))

    def update_and_render(self, surface: pygame.Surface) -> None:
        font_small, font_big = self._get_fonts()
        survivors: List[DamagePopup] = []
        for p in self.popups:
            p.age += 1
            if p.age >= self.LIFETIME_FRAMES:
                continue
            # Drift up
            t = p.age / self.LIFETIME_FRAMES
            p.y = p.y - (self.RISE_PX / self.LIFETIME_FRAMES)
            # Scale-pop
            if p.age < self.PEAK_FRAME:
                scale = 1.0 + (self.PEAK_SCALE - 1.0) * (p.age / self.PEAK_FRAME)
            else:
                # Settle from PEAK_SCALE to 1.0 over next 8 frames, then hold
                settle_t = min(1.0, (p.age - self.PEAK_FRAME) / 8.0)
                scale = self.PEAK_SCALE - (self.PEAK_SCALE - 1.0) * settle_t
            alpha = max(0, int(255 * (1.0 - t)))
            color = (255, 90, 90) if p.is_crit else (255, 230, 90)
            text = f"-{p.dmg}!" if p.is_crit else f"-{p.dmg}"
            base_font = font_big if p.is_crit else font_small
            text_img = base_font.render(text, True, color)
            tw, th = text_img.get_size()
            sw = max(1, int(tw * scale))
            sh = max(1, int(th * scale))
            text_img = pygame.transform.smoothscale(text_img, (sw, sh))
            # Black shadow
            shadow = base_font.render(text, True, (0, 0, 0))
            shadow = pygame.transform.smoothscale(shadow, (sw, sh))
            shadow.set_alpha(alpha)
            text_img.set_alpha(alpha)
            surface.blit(shadow, (int(p.x - sw / 2 + 2), int(p.y - sh / 2 + 2)))
            surface.blit(text_img, (int(p.x - sw / 2), int(p.y - sh / 2)))
            survivors.append(p)
        self.popups = survivors
