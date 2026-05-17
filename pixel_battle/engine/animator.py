"""Sprite animation system. Loads keyframe PNGs and resolves which pose to show
for a given animation clip + elapsed frame count.
"""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Tuple

import pygame


def _binarize_alpha(sprite: pygame.Surface, threshold: int = 128) -> pygame.Surface:
    """Make alpha purely 0 or 255 — eliminates semi-transparent edge speckle."""
    result = sprite.copy()
    pa = pygame.surfarray.pixels_alpha(result)
    pa[pa >= threshold] = 255
    pa[pa < threshold] = 0
    del pa
    return result


def _add_outline(sprite: pygame.Surface, color=(0, 0, 0), thickness: int = 3) -> pygame.Surface:
    """Paint a solid-color outline by blitting a colored silhouette at offset positions."""
    w, h = sprite.get_size()
    out_w = w + thickness * 2
    out_h = h + thickness * 2
    result = pygame.Surface((out_w, out_h), pygame.SRCALPHA)

    # Build a silhouette: all non-transparent pixels become `color`
    silhouette = sprite.copy()
    pa = pygame.surfarray.pixels_alpha(silhouette)
    pr = pygame.surfarray.pixels_red(silhouette)
    pg = pygame.surfarray.pixels_green(silhouette)
    pb = pygame.surfarray.pixels_blue(silhouette)
    mask = pa > 128  # conservative threshold — only fully-opaque parts contribute
    pr[mask] = color[0]
    pg[mask] = color[1]
    pb[mask] = color[2]
    del pr, pg, pb, pa  # release surface locks

    # Blit silhouette at surrounding offsets
    for dx in range(-thickness, thickness + 1):
        for dy in range(-thickness, thickness + 1):
            if dx == 0 and dy == 0:
                continue
            result.blit(silhouette, (dx + thickness, dy + thickness))
    # Original on top
    result.blit(sprite, (thickness, thickness))
    return result

SPRITES_DIR = Path(__file__).resolve().parents[1] / "assets" / "sprites"


class AnimClip(Enum):
    IDLE = "idle"
    ATTACK = "attack"
    HIT = "hit"
    KO = "ko"
    SPECIAL = "special"
    ULTIMATE = "ultimate"


# Each clip is a list of (keyframe_name, hold_frames) defining the sequence.
CLIP_DEFINITIONS: Dict[AnimClip, List[Tuple[str, int]]] = {
    AnimClip.IDLE: [("idle", 24)],  # static, 0.4s at 60fps — just bobs in render_frame
    AnimClip.ATTACK: [("attack_windup", 6), ("attack_strike", 6), ("attack_recover", 6)],
    AnimClip.HIT: [("hit_recoil", 8), ("idle", 4)],
    AnimClip.KO: [("ko_falling", 10), ("ko_landed", 30)],
    AnimClip.SPECIAL: [("special_charge", 10), ("attack_strike", 6), ("idle", 4)],
    AnimClip.ULTIMATE: [("ultimate_pose", 30)],
}


class CharacterSprites:
    """Loads all *_alpha.png keyframes for a character and serves scaled surfaces."""

    def __init__(self, char_id: str, target_height: int = 320):
        self._frames: Dict[str, pygame.Surface] = {}
        char_dir = SPRITES_DIR / char_id
        for pose_path in sorted(char_dir.glob("*_alpha.png")):
            pose = pose_path.stem.replace("_alpha", "")
            raw = pygame.image.load(str(pose_path))
            # convert_alpha() requires a display mode; fall back gracefully in headless envs.
            try:
                img = raw.convert_alpha()
            except pygame.error:
                img = raw
            w, h = img.get_size()
            scale = target_height / h
            new_w = max(1, int(w * scale))
            scaled = pygame.transform.smoothscale(img, (new_w, target_height))
            scaled = _binarize_alpha(scaled, threshold=128)
            self._frames[pose] = _add_outline(scaled, color=(0, 0, 0), thickness=3)

    def get_pose(self, pose_name: str) -> pygame.Surface:
        """Return the surface for ``pose_name``; falls back to idle if unknown."""
        if pose_name not in self._frames:
            return self._frames.get("idle", next(iter(self._frames.values())))
        return self._frames[pose_name]

    @property
    def pose_names(self) -> list:
        return list(self._frames.keys())


def resolve_pose(clip: AnimClip, frame_in_clip: int) -> Tuple[str, float]:
    """Given elapsed frames within a clip, return (pose_name, sub_progress 0-1).

    sub_progress indicates how far through the current keyframe we are (for
    future tweening). Non-loop clips clamp to the last pose when overrun.
    IDLE loops modulo its total duration.
    """
    seq = CLIP_DEFINITIONS[clip]
    total = sum(hold for _, hold in seq)

    if clip is AnimClip.IDLE:
        frame_in_clip = frame_in_clip % total

    cursor = 0
    for i, (pose_name, hold) in enumerate(seq):
        if frame_in_clip < cursor + hold:
            sub = (frame_in_clip - cursor) / max(1, hold)
            return pose_name, sub
        cursor += hold

    # Past end — return last pose
    last_pose, last_hold = seq[-1]
    return last_pose, 1.0
