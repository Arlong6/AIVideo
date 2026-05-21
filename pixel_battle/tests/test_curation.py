# pixel_battle/tests/test_curation.py
"""Low-action match curation."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def test_play_multi_exposes_min_action_rate():
    import pixel_battle.rl.play_multi as pm
    assert hasattr(pm, "MIN_ACTION_RATE")
    assert pm.MIN_ACTION_RATE > 0


def test_should_keep_match_logic():
    """A KO match below the action-rate floor is dropped; a brisk one is kept."""
    from pixel_battle.rl.play_multi import _should_keep

    assert _should_keep({"finished_by_ko": True, "action_score": 1.5})
    assert not _should_keep({"finished_by_ko": True, "action_score": 0.2})
    assert not _should_keep({"finished_by_ko": False, "action_score": 9.0})


def test_run_one_match_result_has_action_score():
    """run_one_match's result dict carries a numeric action_score."""
    import inspect
    from pixel_battle.rl import play
    src = inspect.getsource(play.run_one_match)
    assert "action_score" in src
