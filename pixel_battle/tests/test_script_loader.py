# pixel_battle/tests/test_script_loader.py
"""YAML fight-script loader + validation."""
import textwrap
import pytest

from pixel_battle.script.loader import load_script_text, ScriptError, FightScript


_GOOD = textwrap.dedent("""
    name: "Test fight"
    left: garen
    right: lux
    left_script:
      - {do: advance, until: "dist<=110"}
      - {do: "attack:basic", until: skill_done}
    right_script:
      - {do: retreat, until: "dist>=230"}
      - {do: "attack:cd", until: skill_done}
""")


def test_loads_a_valid_script():
    s = load_script_text(_GOOD)
    assert isinstance(s, FightScript)
    assert s.left == "garen" and s.right == "lux"
    assert len(s.left_intents) == 2
    assert s.left_intents[0].do == "advance"
    assert s.right_intents[1].do == "attack:cd"
    # `until` is compiled to a callable predicate.
    assert callable(s.left_intents[0].until)


def test_rejects_unknown_character():
    bad = _GOOD.replace("left: garen", "left: nobody")
    with pytest.raises(ScriptError):
        load_script_text(bad)


def test_rejects_unknown_do_verb():
    bad = _GOOD.replace("do: advance", "do: teleport")
    with pytest.raises(ScriptError):
        load_script_text(bad)


def test_rejects_bad_condition():
    bad = _GOOD.replace('until: "dist<=110"', 'until: "garbage"')
    with pytest.raises(ScriptError):
        load_script_text(bad)


def test_rejects_missing_field():
    bad = _GOOD.replace("right: lux\n", "")
    with pytest.raises(ScriptError):
        load_script_text(bad)
