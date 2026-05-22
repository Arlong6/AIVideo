"""Effect lifecycle + root/slow enforcement in the engine."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.engine.effects import StatusEffect, ROOT, SLOW


def test_update_effects_decrements_and_expires():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    c = env.left
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=30))
    b._update_effects(c, 16)
    assert c.effect_of(ROOT).remaining_ms == 14
    b._update_effects(c, 16)                 # 14 - 16 = expired
    assert c.has_effect(ROOT) is False        # expired effect removed


def test_root_forces_zero_velocity():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    c = env.left
    c.vel_x = 5.0
    c.effects.append(StatusEffect(kind=ROOT, remaining_ms=1000))
    start_x = c.pos_x
    b._update_physics(c, 16)
    assert c.pos_x == start_x                  # rooted: did not move


def test_slow_scales_velocity():
    env = PixelBattleEnv(seed=1)
    b = env.battle
    fast, slow = env.left, env.right
    fast.pos_x = slow.pos_x = 240.0
    fast.vel_x = slow.vel_x = 6.0
    slow.effects.append(StatusEffect(kind=SLOW, remaining_ms=1000, magnitude=0.5))
    b._update_physics(fast, 16)
    b._update_physics(slow, 16)
    fast_moved = abs(fast.pos_x - 240.0)
    slow_moved = abs(slow.pos_x - 240.0)
    assert slow_moved < fast_moved             # slowed character moved less
