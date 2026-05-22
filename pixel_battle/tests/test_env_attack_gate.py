"""Per-skill attack-range gate — attacks no-op when out of the skill's range."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.engine.physics import MELEE_RANGE, SPECIAL_RANGE


def _env_at(distance):
    env = PixelBattleEnv(seed=1)
    env.left.pos_x = 240.0
    env.right.pos_x = 240.0 + distance
    env.left.mp = 80                  # enough MP for any special
    return env


_MID_BAND = (MELEE_RANGE + SPECIAL_RANGE) // 2     # ~120: past melee, within special


def test_basic_attack_gated_out_past_melee_range():
    env = _env_at(_MID_BAND)
    env._apply_action(env.left, env.right, 4)       # basic
    assert env.left.action_state != "attacking"


def test_basic_attack_fires_within_melee_range():
    env = _env_at(MELEE_RANGE - 30)
    env._apply_action(env.left, env.right, 4)       # basic
    assert env.left.action_state == "attacking"


def test_special_fires_in_the_mid_band_where_basic_was_gated():
    env = _env_at(_MID_BAND)
    env._apply_action(env.left, env.right, 7)       # special
    assert env.left.action_state == "attacking"


def test_special_gated_out_past_special_range():
    env = _env_at(SPECIAL_RANGE + 30)
    env._apply_action(env.left, env.right, 7)       # special
    assert env.left.action_state != "attacking"
