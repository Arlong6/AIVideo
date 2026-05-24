from pixel_battle.script.timeline_format import TimelineEvent, Timeline


def test_event_holds_fields():
    ev = TimelineEvent(t=3500, action_int=5, raw_do="cast:light_binding",
                       skill_id="light_binding")
    assert ev.t == 3500
    assert ev.action_int == 5
    assert ev.raw_do == "cast:light_binding"
    assert ev.skill_id == "light_binding"


def test_event_skill_id_defaults_to_none():
    ev = TimelineEvent(t=500, action_int=2, raw_do="advance")
    assert ev.skill_id is None


def test_timeline_holds_two_lists():
    left = [TimelineEvent(t=0, action_int=0, raw_do="idle")]
    right = [TimelineEvent(t=500, action_int=1, raw_do="retreat")]
    tl = Timeline(name="x", left="garen", right="lux",
                  duration_ms=10000, left_events=left, right_events=right)
    assert tl.name == "x"
    assert tl.left == "garen"
    assert tl.right == "lux"
    assert tl.duration_ms == 10000
    assert tl.left_events == left
    assert tl.right_events == right
