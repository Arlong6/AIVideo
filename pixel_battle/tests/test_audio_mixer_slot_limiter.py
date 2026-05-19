"""SlotLimiter caps concurrent-overlapping events on a bus."""
from pixel_battle.video.audio_mixer import SlotLimiter


def test_fresh_limiter_accepts_first_event():
    lim = SlotLimiter(max_concurrent=2)
    assert lim.can_add(t_ms=0, duration_ms=300) is True


def test_limiter_accepts_up_to_max_concurrent():
    lim = SlotLimiter(max_concurrent=2)
    assert lim.can_add(0, 300) is True
    assert lim.can_add(50, 300) is True
    # Third overlapping event rejected
    assert lim.can_add(100, 300) is False


def test_limiter_accepts_after_window_expires():
    lim = SlotLimiter(max_concurrent=2)
    lim.can_add(0, 300)
    lim.can_add(50, 300)
    # At t=500, both windows (ending 300, 350) have expired
    assert lim.can_add(500, 300) is True


def test_limiter_non_overlapping_all_accepted():
    lim = SlotLimiter(max_concurrent=1)
    for t in (0, 400, 800, 1200):
        assert lim.can_add(t, 300) is True


def test_limiter_boundary_inclusive():
    """If a window ends at t_ms exactly, that slot is free at t_ms."""
    lim = SlotLimiter(max_concurrent=1)
    lim.can_add(0, 300)   # window [0, 300)
    assert lim.can_add(300, 300) is True
