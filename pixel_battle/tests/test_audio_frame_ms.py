"""P5: episode runner uses float FRAME_MS for real-time audio alignment.

Root cause of P4 drift: TICK_MS = 1000 // 60 = 16 (int truncation), but
real frame time at FPS=60 is 1000/60 = 16.6667ms. Over a 40s match,
that 4% truncation cost ~1.7s of audio drift. Fix: use float FRAME_MS
for audio-positioning math; keep integer TICK_MS for physics.
"""
import importlib


def test_frame_ms_is_float_and_matches_fps():
    """FRAME_MS = 1000.0 / FPS, computed as float (no int truncation)."""
    mod = importlib.import_module("pixel_battle.episodes.ep01_brick_vs_glass")
    assert hasattr(mod, "FRAME_MS"), "Episode runner must expose FRAME_MS constant"
    assert isinstance(mod.FRAME_MS, float), \
        f"FRAME_MS must be float, got {type(mod.FRAME_MS).__name__}"
    expected = 1000.0 / mod.FPS
    assert abs(mod.FRAME_MS - expected) < 1e-9, \
        f"FRAME_MS={mod.FRAME_MS}, expected {expected}"


def test_frame_ms_differs_from_tick_ms_at_60_fps():
    """Regression: don't collapse FRAME_MS and TICK_MS to the same value."""
    mod = importlib.import_module("pixel_battle.episodes.ep01_brick_vs_glass")
    assert mod.FPS == 60, "Test assumes FPS=60"
    assert mod.TICK_MS == 16, "Physics tick should still be integer 16ms"
    assert mod.FRAME_MS != mod.TICK_MS, \
        "FRAME_MS must be float (16.6667), distinct from int TICK_MS (16)"
