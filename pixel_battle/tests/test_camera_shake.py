"""Crit screen-shake camera offset."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.play import camera_shake_offset, SHAKE_FRAMES, SHAKE_MAG


def test_no_offset_when_not_shaking():
    assert camera_shake_offset(0) == (0, 0)
    assert camera_shake_offset(-2) == (0, 0)


def test_offset_within_magnitude_while_shaking():
    for frames in range(1, SHAKE_FRAMES + 1):
        for _ in range(40):
            dx, dy = camera_shake_offset(frames)
            assert abs(dx) <= SHAKE_MAG
            assert abs(dy) <= SHAKE_MAG


def test_offset_decays_toward_end_of_shake():
    # The peak possible magnitude at frame 1 is smaller than at full strength.
    early_peak = SHAKE_MAG * (SHAKE_FRAMES / SHAKE_FRAMES)
    late_peak = SHAKE_MAG * (1 / SHAKE_FRAMES)
    assert late_peak < early_peak
