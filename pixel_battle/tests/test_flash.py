# pixel_battle/tests/test_flash.py
"""Flash mobility ability."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.engine.physics import FLASH_DISTANCE, FLASH_COOLDOWN_MS, clamp_x
from pixel_battle.script.loader import DO_VERBS


def test_flash_verbs_registered():
    assert DO_VERBS["flash:in"] == 9
    assert DO_VERBS["flash:back"] == 10


def test_flash_back_moves_away_from_opponent():
    env = PixelBattleEnv(seed=1)
    me, opp = env.left, env.right
    me.pos_x, opp.pos_x = 240.0, 360.0       # opponent is to the right
    me.flash_ready_at_ms = 0
    env._apply_action(me, opp, 10)            # flash:back
    assert me.pos_x == clamp_x(240.0 - FLASH_DISTANCE)   # blinked left, away


def test_flash_in_moves_toward_opponent():
    env = PixelBattleEnv(seed=1)
    me, opp = env.left, env.right
    me.pos_x, opp.pos_x = 240.0, 360.0
    me.flash_ready_at_ms = 0
    env._apply_action(me, opp, 9)             # flash:in
    assert me.pos_x == clamp_x(240.0 + FLASH_DISTANCE)   # blinked right, toward


def test_flash_respects_cooldown():
    env = PixelBattleEnv(seed=1)
    me, opp = env.left, env.right
    me.pos_x, opp.pos_x = 240.0, 360.0
    me.flash_ready_at_ms = 0
    env._apply_action(me, opp, 10)            # first flash — fires
    after_first = me.pos_x
    env._apply_action(me, opp, 10)            # immediately again — on cooldown, no-op
    assert me.pos_x == after_first
    assert me.flash_ready_at_ms > env.battle.elapsed_ms
