# pixel_battle/tests/test_script_driver.py
"""ScriptDriver — per-tick intent tracking + action emission."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.script.loader import load_script_text
from pixel_battle.script.driver import ScriptDriver, INTENT_MAX_MS


_SCRIPT = """
name: "Driver test"
left: garen
right: lux
left_script:
  - {do: advance, until: "dist<=110"}
  - {do: idle, until: "time>=100000"}
right_script:
  - {do: retreat, until: "dist>=100000"}
  - {do: idle, until: "time>=100000"}
"""


def _env_driver():
    env = PixelBattleEnv(seed=1)
    driver = ScriptDriver(load_script_text(_SCRIPT))
    return env, driver


def test_driver_emits_intent_actions():
    env, driver = _env_driver()
    env.left.pos_x, env.right.pos_x = 240.0, 460.0   # far apart
    left_act, right_act = driver.decide(env.battle)
    assert left_act == 2     # advance
    assert right_act == 1    # retreat


def test_driver_advances_intent_when_condition_met():
    env, driver = _env_driver()
    env.left.pos_x, env.right.pos_x = 240.0, 300.0    # dist 60 <= 110
    driver.decide(env.battle)                          # left's intent-0 until met
    left_act, _ = driver.decide(env.battle)
    assert left_act == 0     # advanced to intent-1 (idle)


def test_driver_timeout_advances_a_stuck_intent():
    env, driver = _env_driver()
    env.left.pos_x, env.right.pos_x = 240.0, 460.0    # dist never <= 110
    # Pump more than INTENT_MAX_MS of ticks; the stuck intent must advance.
    ticks = INTENT_MAX_MS // 16 + 5
    for _ in range(ticks):
        driver.decide(env.battle)
        env.battle.elapsed_ms += 16
    left_act, _ = driver.decide(env.battle)
    assert left_act == 0     # timed out of advance → now on intent-1 (idle)


def test_exhausted_script_idles():
    script = """
name: "short"
left: garen
right: lux
left_script:
  - {do: advance, until: "time>=0"}
right_script:
  - {do: idle, until: "time>=0"}
"""
    env = PixelBattleEnv(seed=1)
    driver = ScriptDriver(load_script_text(script))
    for _ in range(5):
        left_act, _ = driver.decide(env.battle)
        env.battle.elapsed_ms += 16
    assert left_act == 0     # ran out of intents → idle
