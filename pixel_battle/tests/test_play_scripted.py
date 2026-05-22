# pixel_battle/tests/test_play_scripted.py
"""Scripted render path — action-source abstraction + ScriptDriver wiring."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def test_rl_action_source_returns_int_pair():
    import numpy as np
    from pixel_battle.rl.play import _rl_action_source

    class _FakeModel:
        def predict(self, obs, deterministic=False):
            return np.array(3), None

    src = _rl_action_source(_FakeModel())
    left, right = src(None, (np.zeros(10), np.zeros(10)))
    assert isinstance(left, int) and isinstance(right, int)
    assert 0 <= left <= 8 and 0 <= right <= 8


def test_script_action_source_drives_from_a_script():
    from pixel_battle.rl.env import PixelBattleEnv
    from pixel_battle.rl.play_scripted import _script_action_source
    from pixel_battle.script.driver import ScriptDriver
    from pixel_battle.script.loader import load_script_text

    script = """
name: "src test"
left: garen
right: lux
left_script:
  - {do: advance, until: "time>=100000"}
right_script:
  - {do: retreat, until: "time>=100000"}
"""
    env = PixelBattleEnv(seed=1)
    env.reset()
    env.left.pos_x, env.right.pos_x = 240.0, 400.0
    src = _script_action_source(ScriptDriver(load_script_text(script)))
    left_act, right_act = src(env, None)
    assert left_act == 2 and right_act == 1     # advance / retreat
