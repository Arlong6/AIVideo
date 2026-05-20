"""Smoke test — play_multi.py imports and run_one_match exists."""

def test_run_one_match_importable():
    from pixel_battle.rl.play import run_one_match
    assert callable(run_one_match)

def test_play_multi_importable():
    from pixel_battle.rl import play_multi
    assert hasattr(play_multi, "main")
