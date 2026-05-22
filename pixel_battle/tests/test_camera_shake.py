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
    """The offset's bound shrinks as the shake runs out of frames."""
    full_mag = int(SHAKE_MAG * (SHAKE_FRAMES / SHAKE_FRAMES))   # frame at full strength
    last_mag = int(SHAKE_MAG * (1 / SHAKE_FRAMES))              # final frame
    assert last_mag < full_mag
    # The function's actual output on the last frame must respect the decayed bound.
    for _ in range(40):
        dx, dy = camera_shake_offset(1)
        assert abs(dx) <= last_mag
        assert abs(dy) <= last_mag
