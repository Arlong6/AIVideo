import pytest
from pixel_battle.script.loader import load_fight_file, ScriptError
from pixel_battle.script.driver import ScriptDriver
from pixel_battle.script.timeline_driver import TimelineDriver


_TIMELINE_YAML = """
name: tl
left: garen
right: lux
duration_ms: 5000
left_timeline:
  - {t: 0, do: idle}
right_timeline:
  - {t: 0, do: idle}
"""

_LEGACY_YAML = """
name: legacy
left: garen
right: lux
left_script:
  - {do: idle, until: "time>=5000"}
right_script:
  - {do: idle, until: "time>=5000"}
"""

_AMBIGUOUS_YAML = """
name: bad
left: garen
right: lux
left_timeline:
  - {t: 0, do: idle}
right_script:
  - {do: idle, until: "time>=5000"}
"""


def test_dispatches_timeline(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(_TIMELINE_YAML)
    driver = load_fight_file(p)
    assert isinstance(driver, TimelineDriver)


def test_dispatches_legacy(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(_LEGACY_YAML)
    driver = load_fight_file(p)
    assert isinstance(driver, ScriptDriver)


def test_ambiguous_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text(_AMBIGUOUS_YAML)
    with pytest.raises(ScriptError, match="ambiguous"):
        load_fight_file(p)


def test_unknown_format_rejected(tmp_path):
    p = tmp_path / "x.yaml"
    p.write_text("name: x\nleft: garen\nright: lux\n")
    with pytest.raises(ScriptError, match="neither"):
        load_fight_file(p)
