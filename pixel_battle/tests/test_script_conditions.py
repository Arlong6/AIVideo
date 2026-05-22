# pixel_battle/tests/test_script_conditions.py
"""Script `until` condition compiler."""
import pytest

from pixel_battle.engine.character import Character
from pixel_battle.engine.effects import StatusEffect, ROOT
from pixel_battle.script.conditions import (
    compile_condition, ConditionContext, ConditionError,
)


def _ctx(dist=150.0, elapsed=0, attacked=False, hp=100, opp_hp=100,
         opp_effects=None):
    char = Character.load("garen"); char.hp = hp; char.action_state = "idle"
    opp = Character.load("lux"); opp.hp = opp_hp
    opp.effects = list(opp_effects or [])
    return ConditionContext(dist=dist, intent_elapsed_ms=elapsed,
                            char=char, opponent=opp, attacked_this_intent=attacked)


def test_dist_conditions():
    assert compile_condition("dist>=200")(_ctx(dist=250)) is True
    assert compile_condition("dist>=200")(_ctx(dist=150)) is False
    assert compile_condition("dist<=110")(_ctx(dist=90)) is True


def test_time_condition():
    assert compile_condition("time>=600")(_ctx(elapsed=700)) is True
    assert compile_condition("time>=600")(_ctx(elapsed=500)) is False


def test_skill_done_condition():
    cond = compile_condition("skill_done")
    c_attacking = _ctx(attacked=True); c_attacking.char.action_state = "attacking"
    assert cond(c_attacking) is False                  # still attacking
    assert cond(_ctx(attacked=True)) is True            # attacked + now idle
    assert cond(_ctx(attacked=False)) is False          # never attacked


def test_hp_conditions():
    assert compile_condition("hp<=40")(_ctx(hp=30)) is True
    assert compile_condition("target_hp<=40")(_ctx(opp_hp=20)) is True


def test_target_has_condition():
    rooted = [StatusEffect(kind=ROOT, remaining_ms=500)]
    assert compile_condition("target_has:root")(_ctx(opp_effects=rooted)) is True
    assert compile_condition("target_has:root")(_ctx()) is False


def test_bad_conditions_raise():
    with pytest.raises(ConditionError):
        compile_condition("garbage")
    with pytest.raises(ConditionError):
        compile_condition("dist>=notanumber")
    with pytest.raises(ConditionError):
        compile_condition("target_has:nonsense")
    with pytest.raises(ConditionError):
        compile_condition("unknownfield>=100")
