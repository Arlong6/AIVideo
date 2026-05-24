# pixel_battle/tests/test_timeline_loader.py
import pytest
from pixel_battle.script.timeline_loader import (
    load_timeline_text, TimelineLoadError,
)


_GOOD = """
name: "test fight"
left: garen
right: lux
duration_ms: 10000
left_timeline:
  - {t: 0, do: idle}
  - {t: 500, do: advance}
  - {t: 3000, do: "attack:basic"}
right_timeline:
  - {t: 0, do: idle}
  - {t: 800, do: retreat}
  - {t: 3000, do: "cast:light_binding"}
"""


def test_parses_valid_yaml():
    tl = load_timeline_text(_GOOD)
    assert tl.name == "test fight"
    assert tl.left == "garen"
    assert tl.right == "lux"
    assert tl.duration_ms == 10000
    assert len(tl.left_events) == 3
    assert len(tl.right_events) == 3
    # `do: advance` → action_int 2, no skill_id
    assert tl.left_events[1].action_int == 2
    assert tl.left_events[1].skill_id is None
    # `do: cast:light_binding` → action_int 5 (cooldown), skill_id set
    assert tl.right_events[2].action_int == 5
    assert tl.right_events[2].skill_id == "light_binding"


def test_unknown_do_verb_rejected():
    bad = _GOOD.replace("do: advance", "do: wiggle")
    with pytest.raises(TimelineLoadError, match="unknown do verb"):
        load_timeline_text(bad)


def test_unknown_skill_id_rejected():
    bad = _GOOD.replace("cast:light_binding", "cast:no_such_skill")
    with pytest.raises(TimelineLoadError, match="unknown skill id"):
        load_timeline_text(bad)


def test_skill_not_on_character_rejected():
    # Garen does not have light_binding (it's a Lux skill). If we put a Lux-only
    # skill on Garen's LEFT timeline, the loader must reject it with "not a skill of".
    # Keep right_timeline valid; replace attack:basic on Garen's side with a Lux skill.
    bad = _GOOD.replace("do: \"attack:basic\"", "do: \"cast:light_binding\"")
    with pytest.raises(TimelineLoadError, match="not a skill of"):
        load_timeline_text(bad)


def test_nonmonotonic_t_rejected():
    bad = _GOOD.replace("t: 3000, do: \"attack:basic\"",
                        "t: 100, do: \"attack:basic\"")
    with pytest.raises(TimelineLoadError, match="non-monotonic"):
        load_timeline_text(bad)


def test_duplicate_t_rejected():
    # Spec §6: timestamps must be STRICTLY increasing. Two events at the
    # same t on the same side is a likely author copy-paste mistake.
    bad = _GOOD.replace("t: 3000, do: \"attack:basic\"",
                        "t: 500, do: \"attack:basic\"")
    with pytest.raises(TimelineLoadError, match="non-monotonic"):
        load_timeline_text(bad)


def test_missing_required_key():
    with pytest.raises(TimelineLoadError, match="missing required key"):
        load_timeline_text("name: x\nleft: garen\nright: lux\n")


def test_unknown_character_rejected():
    bad = _GOOD.replace("left: garen", "left: nobody_here")
    with pytest.raises(TimelineLoadError, match="unknown character"):
        load_timeline_text(bad)


def test_negative_t_rejected():
    bad = _GOOD.replace("t: 500, do: advance",
                        "t: -100, do: advance")
    with pytest.raises(TimelineLoadError, match="negative"):
        load_timeline_text(bad)
