# pixel_battle/tests/test_timeline_library.py
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pathlib import Path

import pytest

from pixel_battle.rl.env import PixelBattleEnv
from pixel_battle.script.loader import load_fight_file
from pixel_battle.script.timeline_driver import TimelineDriver


_SCRIPTS = sorted(Path("pixel_battle/data/scripts").glob("*.yaml"))
TICK_MS = 16


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.stem)
def test_loads_as_timeline_driver(path):
    driver = load_fight_file(path)
    assert isinstance(driver, TimelineDriver), (
        f"{path.name} did not dispatch to TimelineDriver")


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.stem)
def test_reaches_decisive_ko(path):
    driver = load_fight_file(path)
    tl = driver.timeline
    env = PixelBattleEnv(left_id=tl.left, right_id=tl.right)
    env.reset()
    budget_ms = int(tl.duration_ms * 1.2)
    while env.battle.elapsed_ms < budget_ms:
        left_act, right_act = driver.decide(env.battle)
        env.step((left_act, right_act))
        if env.battle.state.name == "KO":
            break
    assert env.battle.state.name == "KO", (
        f"{path.name} did not KO within {budget_ms} ms "
        f"(elapsed={env.battle.elapsed_ms}, "
        f"left_hp={env.battle.left.hp}, right_hp={env.battle.right.hp})")
    loser = env.battle.left if env.battle.left.hp <= 0 else env.battle.right
    assert loser.hp <= 0


@pytest.mark.parametrize("path", _SCRIPTS, ids=lambda p: p.stem)
def test_no_idle_stretch_longer_than_1s(path):
    """Smoothness regression — directly tests the user's '卡卡' complaint.
    The legacy `INTENT_MAX_MS = 4000ms` stalls would fail this by 4×."""
    driver = load_fight_file(path)
    tl = driver.timeline
    env = PixelBattleEnv(left_id=tl.left, right_id=tl.right)
    env.reset()
    left_idle_run = 0
    right_idle_run = 0
    left_max_run = 0
    right_max_run = 0
    while env.battle.elapsed_ms < int(tl.duration_ms * 1.2):
        left_act, right_act = driver.decide(env.battle)
        if left_act == 0:
            left_idle_run += TICK_MS
            left_max_run = max(left_max_run, left_idle_run)
        else:
            left_idle_run = 0
        if right_act == 0:
            right_idle_run += TICK_MS
            right_max_run = max(right_max_run, right_idle_run)
        else:
            right_idle_run = 0
        env.step((left_act, right_act))
        if env.battle.state.name == "KO":
            break
    assert left_max_run < 1000, (
        f"{path.name}: left timeline had a {left_max_run} ms idle stretch")
    assert right_max_run < 1000, (
        f"{path.name}: right timeline had a {right_max_run} ms idle stretch")
