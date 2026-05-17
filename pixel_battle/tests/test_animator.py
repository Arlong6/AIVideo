import os
import pygame
import pytest
from pixel_battle.engine.animator import (
    AnimClip, CLIP_DEFINITIONS, CharacterSprites, resolve_pose,
)


def setup_module(_):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()


def test_resolve_pose_idle_returns_idle():
    pose, sub = resolve_pose(AnimClip.IDLE, 0)
    assert pose == "idle"
    pose, sub = resolve_pose(AnimClip.IDLE, 100)
    assert pose == "idle"


def test_resolve_pose_attack_sequence():
    # ATTACK = windup(6) + strike(6) + recover(6) = 18 frames
    pose, _ = resolve_pose(AnimClip.ATTACK, 0)
    assert pose == "attack_windup"
    pose, _ = resolve_pose(AnimClip.ATTACK, 5)
    assert pose == "attack_windup"
    pose, _ = resolve_pose(AnimClip.ATTACK, 6)
    assert pose == "attack_strike"
    pose, _ = resolve_pose(AnimClip.ATTACK, 12)
    assert pose == "attack_recover"
    pose, _ = resolve_pose(AnimClip.ATTACK, 100)
    assert pose == "attack_recover"  # clamps to last


def test_character_sprites_loads_all_poses():
    cs = CharacterSprites("brick_phone")
    # All 9 poses should be loaded
    for pose in ["idle", "attack_windup", "attack_strike", "attack_recover",
                 "hit_recoil", "ko_falling", "ko_landed", "special_charge", "ultimate_pose"]:
        surface = cs.get_pose(pose)
        assert surface is not None
        assert surface.get_height() > 0


def test_unknown_pose_falls_back_to_idle():
    cs = CharacterSprites("brick_phone")
    fallback = cs.get_pose("nonexistent_pose")
    idle = cs.get_pose("idle")
    # Same surface object (fallback returns idle surface)
    assert fallback.get_size() == idle.get_size()


def test_character_sprites_glass_slab_loads():
    cs = CharacterSprites("glass_slab")
    for pose in ["idle", "attack_windup", "attack_strike", "attack_recover",
                 "hit_recoil", "ko_falling", "ko_landed", "special_charge", "ultimate_pose"]:
        surface = cs.get_pose(pose)
        assert surface is not None
        assert surface.get_height() > 0


def test_resolve_pose_hit_sequence():
    # HIT = hit_recoil(8) + idle(4)
    pose, _ = resolve_pose(AnimClip.HIT, 0)
    assert pose == "hit_recoil"
    pose, _ = resolve_pose(AnimClip.HIT, 7)
    assert pose == "hit_recoil"
    pose, _ = resolve_pose(AnimClip.HIT, 8)
    assert pose == "idle"
    pose, _ = resolve_pose(AnimClip.HIT, 100)
    assert pose == "idle"  # clamps


def test_resolve_pose_ko_sequence():
    # KO = ko_falling(10) + ko_landed(30)
    pose, _ = resolve_pose(AnimClip.KO, 0)
    assert pose == "ko_falling"
    pose, _ = resolve_pose(AnimClip.KO, 9)
    assert pose == "ko_falling"
    pose, _ = resolve_pose(AnimClip.KO, 10)
    assert pose == "ko_landed"
    pose, _ = resolve_pose(AnimClip.KO, 200)
    assert pose == "ko_landed"


def test_resolve_pose_sub_progress_in_range():
    for clip in AnimClip:
        for frame in [0, 3, 7, 15, 50]:
            _, sub = resolve_pose(clip, frame)
            assert 0.0 <= sub <= 1.0, f"{clip} frame={frame} sub={sub}"


def test_clip_definitions_all_clips_defined():
    for clip in AnimClip:
        assert clip in CLIP_DEFINITIONS
        assert len(CLIP_DEFINITIONS[clip]) > 0


def test_character_sprites_target_height():
    cs = CharacterSprites("brick_phone", target_height=100)
    surface = cs.get_pose("idle")
    assert surface.get_height() == 100


def test_character_sprites_has_alpha():
    cs = CharacterSprites("brick_phone")
    surface = cs.get_pose("idle")
    # Surface should have per-pixel alpha (convert_alpha was called)
    assert surface.get_bitsize() == 32
