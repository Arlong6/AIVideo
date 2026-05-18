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


# ---------------------------------------------------------------------------
# DPS counter — rolling 3-second window of damage dealt
# ---------------------------------------------------------------------------


class DPSCounter:
    WINDOW_MS = 3000

    def __init__(self):
        # entries: list of (t_ms, dmg)
        self._entries: List[Tuple[int, int]] = []
        self._font: pygame.font.Font | None = None

    def _get_font(self) -> pygame.font.Font:
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 18)
        return self._font

    def record_hit(self, dmg: int, t_ms: int) -> None:
        self._entries.append((t_ms, dmg))
        self._prune(t_ms)

    def _prune(self, now_ms: int) -> None:
        cutoff = now_ms - self.WINDOW_MS
        self._entries = [(t, d) for (t, d) in self._entries if t > cutoff]

    def current_dps(self, now_ms: int) -> float:
        self._prune(now_ms)
        if not self._entries:
            return 0.0
        total = sum(d for _, d in self._entries)
        return total / (self.WINDOW_MS / 1000.0)

    def render(self, surface: pygame.Surface, x: int, y: int, now_ms: int) -> None:
        font = self._get_font()
        dps = self.current_dps(now_ms)
        text = f"DPS {dps:4.1f}"
        img = font.render(text, True, (255, 230, 150))
        shadow = font.render(text, True, (0, 0, 0))
        surface.blit(shadow, (x + 1, y + 1))
        surface.blit(img, (x, y))


# ---------------------------------------------------------------------------
# Skill icon bar — shows basic + CD skill icons with CD arc countdown
# ---------------------------------------------------------------------------


_ICON_COLOR_BY_TYPE = {
    SkillType.BASIC:    (220, 220, 180),
    SkillType.COOLDOWN: ( 80, 180, 255),
    SkillType.SPECIAL:  (255, 140,  40),
    SkillType.ULTIMATE: (255,  80, 200),
}

_ICON_GLYPH_BY_TYPE = {
    SkillType.BASIC:    "B",
    SkillType.COOLDOWN: "C",
    SkillType.SPECIAL:  "S",
    SkillType.ULTIMATE: "U",
}


class SkillIconBar:
    """Renders icons for character's basic + CD skills (the two non-MP slots).
    Specials live in the MP bar, ultimate has its own indicator.
    """
    ICON_SIZE = 28
    ICON_GAP = 6

    def __init__(self, character: Character):
        self.character = character
        # Display the basic + first cooldown skill (if any)
        self._slots = []
        basics = character.skills_of_type(SkillType.BASIC)
        cooldowns = character.skills_of_type(SkillType.COOLDOWN)
        if basics:
            self._slots.append(basics[0])
        if cooldowns:
            self._slots.append(cooldowns[0])
        self._font: pygame.font.Font | None = None

    @property
    def num_slots(self) -> int:
        return len(self._slots)

    def _get_font(self):
        if not pygame.font.get_init():
            pygame.font.init()
        if self._font is None:
            self._font = pygame.font.Font(None, 22)
        return self._font

    def _cd_fill_ratio(self, skill_id: str, now_ms: int) -> float:
        """0.0 = ready (no CD), 1.0 = just used (full CD remaining)."""
        ready_at = self.character.skill_cd_ready_at.get(skill_id, 0)
        skill = next((s for s in self._slots if s.id == skill_id), None)
        if skill is None or skill.cooldown_ms <= 0:
            return 0.0
        remaining = max(0, ready_at - now_ms)
        return min(1.0, remaining / skill.cooldown_ms)

    def render(self, surface: pygame.Surface, x: int, y: int, now_ms: int) -> None:
        font = self._get_font()
        for i, skill in enumerate(self._slots):
            icon_x = x + i * (self.ICON_SIZE + self.ICON_GAP)
            color = _ICON_COLOR_BY_TYPE.get(skill.skill_type, (200, 200, 200))
            # Background tile
            pygame.draw.rect(surface, (40, 40, 50),
                             (icon_x, y, self.ICON_SIZE, self.ICON_SIZE),
                             border_radius=4)
            pygame.draw.rect(surface, color,
                             (icon_x, y, self.ICON_SIZE, self.ICON_SIZE),
                             width=2, border_radius=4)
            glyph = _ICON_GLYPH_BY_TYPE.get(skill.skill_type, "?")
            img = font.render(glyph, True, color)
            rect = img.get_rect(center=(icon_x + self.ICON_SIZE // 2,
                                         y + self.ICON_SIZE // 2))
            surface.blit(img, rect)
            # CD arc overlay (darken portion still on CD)
            fill = self._cd_fill_ratio(skill.id, now_ms)
            if fill > 0.02:
                overlay = pygame.Surface((self.ICON_SIZE, self.ICON_SIZE),
                                          pygame.SRCALPHA)
                overlay.fill((0, 0, 0, int(180 * fill)))
                surface.blit(overlay, (icon_x, y))
                # Small countdown numerals (seconds)
                ready_at = self.character.skill_cd_ready_at.get(skill.id, 0)
                rem_s = max(0, (ready_at - now_ms) / 1000.0)
                cd_text = font.render(f"{rem_s:.1f}", True, (255, 255, 255))
                cd_rect = cd_text.get_rect(center=(icon_x + self.ICON_SIZE // 2,
                                                    y + self.ICON_SIZE // 2))
                surface.blit(cd_text, cd_rect)


# ---------------------------------------------------------------------------
# MP charge ring — 3 orbiting sparkles around character when MP == max
# ---------------------------------------------------------------------------


class MPChargeRing:
    NUM_SPARKLES = 3
    ORBIT_RADIUS_PX = 80
    ORBIT_PERIOD_MS = 1000   # one rotation per second

    def render(self, surface: pygame.Surface, char: Character,
               char_x: int, char_y: int, t_ms: int) -> None:
        if char.mp < char.mp_max:
            return
        for i in range(self.NUM_SPARKLES):
            phase = (t_ms / self.ORBIT_PERIOD_MS + i / self.NUM_SPARKLES) * 2 * math.pi
            sx = int(char_x + math.cos(phase) * self.ORBIT_RADIUS_PX)
            sy = int(char_y - 70 + math.sin(phase) * self.ORBIT_RADIUS_PX * 0.5)
            # Sparkle: small bright circle with halo
            halo = pygame.Surface((20, 20), pygame.SRCALPHA)
            pygame.draw.circle(halo, (120, 200, 255, 90), (10, 10), 9)
            pygame.draw.circle(halo, (200, 230, 255, 200), (10, 10), 5)
            pygame.draw.circle(halo, (255, 255, 255, 255), (10, 10), 2)
            surface.blit(halo, (sx - 10, sy - 10))
