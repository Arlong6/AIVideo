"""KOF-style top HUD: two health bars + name plates + match timer.

Stateless except for the smoothed-bar lerp state, which is per-HUD-instance.
A new HUD is constructed per render in `_render_fight`."""
from __future__ import annotations
import json
import pygame

from pixel_battle.engine.character import DATA_PATH

HUD_HEIGHT = 70                # px from top reserved for HUD
BAR_WIDTH = 180
BAR_HEIGHT = 14
BAR_Y = 28
MP_BAR_HEIGHT = 5              # thin mana bar tucked under the HP bar
MP_BAR_GAP = 3                 # gap between HP and MP bars
NAME_FONT_SIZE = 14
TIMER_FONT_SIZE = 14
BAR_DRAIN_LERP_RATE = 0.18     # per-frame towards target HP fraction (faster for test stability)
BAR_BG = (40, 40, 50)
MP_BAR_BG = (28, 30, 42)
BAR_BORDER = (220, 220, 220)
NAME_COLOR = (230, 230, 230)
NAME_SHADOW = (10, 10, 14)
TIMER_COLOR = (180, 180, 180)
# Universal HP / MP colors — HP reads as health (green->yellow->red by amount),
# MP as mana (blue). Character identity comes from name + stick-figure color, NOT
# the bar color, so the two bars are never the same hue (the old confusion).
HP_HIGH = (90, 210, 100)
HP_MID = (235, 200, 60)
HP_LOW = (228, 72, 60)
MP_COLOR = (80, 175, 255)


def _hp_color(frac: float) -> tuple:
    if frac > 0.5:
        return HP_HIGH
    if frac > 0.25:
        return HP_MID
    return HP_LOW


def _load_char_color(char_id: str) -> tuple:
    """Read the character's brand_color from data, fallback to color, then white."""
    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    char_data = data.get(char_id, {})
    rgb = char_data.get("brand_color") or char_data.get("color")
    if not rgb:
        return (220, 220, 220)
    return tuple(rgb[:3])


class HUD:
    """KOF-style top HUD. Construct once per render; call `draw` each frame."""

    def __init__(self):
        self._left_lerp = 1.0
        self._right_lerp = 1.0
        self._name_font = pygame.font.SysFont(None, NAME_FONT_SIZE * 2)
        self._timer_font = pygame.font.SysFont(None, TIMER_FONT_SIZE * 2)
        self._color_cache: dict = {}

    def _color(self, char_id: str):
        if char_id not in self._color_cache:
            self._color_cache[char_id] = _load_char_color(char_id)
        return self._color_cache[char_id]

    def draw(self, surf: pygame.Surface, battle, elapsed_ms: int) -> None:
        W = surf.get_width()
        left_frac = max(0.0, battle.left.hp / max(1, getattr(battle.left, "hp_max", 100)))
        right_frac = max(0.0, battle.right.hp / max(1, getattr(battle.right, "hp_max", 100)))
        self._left_lerp += (left_frac - self._left_lerp) * BAR_DRAIN_LERP_RATE
        self._right_lerp += (right_frac - self._right_lerp) * BAR_DRAIN_LERP_RATE

        # Draw a dark backing for the whole HUD strip so it's readable over any bg
        hud_bg = pygame.Surface((W, HUD_HEIGHT), pygame.SRCALPHA)
        hud_bg.fill((0, 0, 0, 140))
        surf.blit(hud_bg, (0, 0))

        left_mp = max(0.0, battle.left.mp / max(1, getattr(battle.left, "mp_max", 100)))
        right_mp = max(0.0, battle.right.mp / max(1, getattr(battle.right, "mp_max", 100)))

        # left bar: x_right = W//2 - 30, drains right-to-left
        left_bar_right = W // 2 - 30
        left_bar_left = left_bar_right - BAR_WIDTH
        self._draw_bar(surf, x=left_bar_left, width=BAR_WIDTH, frac=self._left_lerp,
                       color=_hp_color(self._left_lerp), direction=-1)
        self._draw_mp_bar(surf, x=left_bar_left, width=BAR_WIDTH, frac=left_mp, direction=-1)

        # right bar: x_left = W//2 + 30, drains left-to-right
        right_bar_left = W // 2 + 30
        self._draw_bar(surf, x=right_bar_left, width=BAR_WIDTH, frac=self._right_lerp,
                       color=_hp_color(self._right_lerp), direction=+1)
        self._draw_mp_bar(surf, x=right_bar_left, width=BAR_WIDTH, frac=right_mp, direction=+1)

        # Name plates
        self._draw_name(surf, battle.left.id, x=left_bar_left, align="left")
        self._draw_name(surf, battle.right.id, x=right_bar_left + BAR_WIDTH, align="right")

        # Center separator ticks
        cx = W // 2
        pygame.draw.line(surf, BAR_BORDER, (cx - 2, BAR_Y - 4), (cx - 2, BAR_Y + BAR_HEIGHT + 4), 2)
        pygame.draw.line(surf, BAR_BORDER, (cx + 2, BAR_Y - 4), (cx + 2, BAR_Y + BAR_HEIGHT + 4), 2)

        # Timer — below the MP bar so they don't overlap
        self._draw_timer(surf, elapsed_ms, x=cx,
                         y=BAR_Y + BAR_HEIGHT + MP_BAR_GAP + MP_BAR_HEIGHT + 3)

    def _draw_bar(self, surf, x, width, frac, color, direction):
        """Draw a health bar at (x, BAR_Y) of given width.
        direction=-1: fill anchored on right side (left player, drains left)
        direction=+1: fill anchored on left side (right player, drains right)
        """
        pygame.draw.rect(surf, BAR_BG, (x, BAR_Y, width, BAR_HEIGHT))
        fill_w = max(0, int(width * frac))
        if direction == -1:
            # Left player: bar fills from RIGHT toward left; drains by shrinking left side
            fill_x = x + (width - fill_w)
        else:
            # Right player: bar fills from LEFT toward right; drains by shrinking right side
            fill_x = x
        if fill_w > 0:
            pygame.draw.rect(surf, color, (fill_x, BAR_Y, fill_w, BAR_HEIGHT))
        pygame.draw.rect(surf, BAR_BORDER, (x, BAR_Y, width, BAR_HEIGHT), width=1)

    def _draw_mp_bar(self, surf, x, width, frac, direction):
        """Thin blue mana bar tucked just under the HP bar, same drain direction."""
        my = BAR_Y + BAR_HEIGHT + MP_BAR_GAP
        pygame.draw.rect(surf, MP_BAR_BG, (x, my, width, MP_BAR_HEIGHT))
        fill_w = max(0, int(width * frac))
        fill_x = x + (width - fill_w) if direction == -1 else x
        if fill_w > 0:
            pygame.draw.rect(surf, MP_COLOR, (fill_x, my, fill_w, MP_BAR_HEIGHT))
        pygame.draw.rect(surf, (110, 130, 170), (x, my, width, MP_BAR_HEIGHT), width=1)

    def _draw_name(self, surf, name, x, align):
        text = name.replace("_", " ").upper()
        shadow = self._name_font.render(text, True, NAME_SHADOW)
        label = self._name_font.render(text, True, NAME_COLOR)
        if align == "left":
            x_pos = x
        else:
            x_pos = x - label.get_width()
        name_y = BAR_Y - label.get_height() - 2
        if name_y < 2:
            name_y = 2
        surf.blit(shadow, (x_pos + 1, name_y + 1))
        surf.blit(label, (x_pos, name_y))

    def _draw_timer(self, surf, elapsed_ms, x, y):
        seconds = max(0, elapsed_ms // 1000)
        text = f"{seconds // 60:02d}:{seconds % 60:02d}"
        label = self._timer_font.render(text, True, TIMER_COLOR)
        surf.blit(label, (x - label.get_width() // 2, y))
