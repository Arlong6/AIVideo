"""Skill-name banner system: flashes a big "SKILL NAME!" text across the screen
when a notable skill connects. Slides in from left, holds at center, fades out.

Pure rendering — no game logic. One banner at a time; newer spawn replaces older.
"""
from dataclasses import dataclass
from typing import Optional, Tuple

import pygame


@dataclass
class Banner:
    text: str
    color: Tuple[int, int, int]
    x: float = -200.0
    age: int = 0


class BannerSystem:
    LIFETIME_FRAMES = 36       # ~0.6s at 60fps
    SLIDE_IN_FRAMES = 10
    FADE_OUT_START = 26
    X_START = -200
    X_END = 240                # screen center (480 / 2)
    Y_CENTER = 270
    FONT_SIZE = 48

    def __init__(self):
        self.active: Optional[Banner] = None
        self._font: Optional[pygame.font.Font] = None

    def _get_font(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, self.FONT_SIZE)
        return self._font

    def spawn(self, text: str, color: Tuple[int, int, int]) -> None:
        self.active = Banner(text=text, color=color, x=float(self.X_START), age=0)

    def update_and_render(self, surface: pygame.Surface) -> None:
        if self.active is None:
            return
        b = self.active
        b.age += 1
        if b.age >= self.LIFETIME_FRAMES:
            self.active = None
            return

        # Phase 1: slide in 0 → SLIDE_IN_FRAMES (x lerps START → END)
        if b.age <= self.SLIDE_IN_FRAMES:
            t = b.age / self.SLIDE_IN_FRAMES
            # Ease-out for snappy entry
            t = 1.0 - (1.0 - t) ** 2
            b.x = self.X_START + (self.X_END - self.X_START) * t
        else:
            b.x = float(self.X_END)

        # Phase 3: fade alpha FADE_OUT_START → LIFETIME_FRAMES
        if b.age >= self.FADE_OUT_START:
            fade_t = (b.age - self.FADE_OUT_START) / max(
                1, self.LIFETIME_FRAMES - self.FADE_OUT_START)
            alpha = max(0, int(255 * (1.0 - fade_t)))
        else:
            alpha = 255

        font = self._get_font()
        img = font.render(b.text, True, b.color)
        shadow = font.render(b.text, True, (0, 0, 0))
        img.set_alpha(alpha)
        shadow.set_alpha(alpha)
        rect = img.get_rect(center=(int(b.x), self.Y_CENTER))
        surface.blit(shadow, (rect.x + 3, rect.y + 3))
        surface.blit(img, rect)
