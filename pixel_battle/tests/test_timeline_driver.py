# pixel_battle/tests/test_timeline_driver.py
from pixel_battle.script.timeline_format import Timeline, TimelineEvent
from pixel_battle.script.timeline_driver import TimelineDriver
from pixel_battle.engine.character import Character
from pixel_battle.engine.effects import StatusEffect, ROOT
from pixel_battle.engine.battle import Battle
from pixel_battle.engine.rng import BattleRNG


def _two_char_battle(left_events, right_events, duration_ms=10000):
    left = Character.load("garen")
    right = Character.load("lux")
    b = Battle(left, right, rng=BattleRNG(seed=0))
    tl = Timeline(name="t", left="garen", right="lux",
                  duration_ms=duration_ms,
                  left_events=left_events, right_events=right_events)
    d = TimelineDriver(tl)
    return b, d


def test_event_fires_at_scheduled_t():
    left = [TimelineEvent(t=500, action_int=2, raw_do="advance")]
    right = [TimelineEvent(t=0, action_int=0, raw_do="idle")]
    b, d = _two_char_battle(left, right)
    # Before scheduled time → both idle
    b.elapsed_ms = 0
    assert d.decide(b) == (0, 0)
    b.elapsed_ms = 499
    assert d.decide(b) == (0, 0)
    # At/after scheduled time AND actor can act → fires
    b.elapsed_ms = 500
    left_act, right_act = d.decide(b)
    assert left_act == 2     # advance
    assert right_act == 0    # idle (script exhausted on right)


def test_cursor_advances_only_once_per_event():
    left = [TimelineEvent(t=0, action_int=2, raw_do="advance"),
            TimelineEvent(t=1000, action_int=1, raw_do="retreat")]
    right = []
    b, d = _two_char_battle(left, right)
    b.elapsed_ms = 0
    assert d.decide(b)[0] == 2     # advance fires
    b.elapsed_ms = 16
    assert d.decide(b)[0] == 0     # cursor moved on; next event not due yet
    b.elapsed_ms = 1000
    assert d.decide(b)[0] == 1     # retreat fires


def test_event_delays_when_actor_in_attack_phase():
    # Left has an event at t=0; we mark left as mid-attack so it can't act.
    left = [TimelineEvent(t=0, action_int=2, raw_do="advance"),
            TimelineEvent(t=100, action_int=1, raw_do="retreat")]
    right = []
    b, d = _two_char_battle(left, right)
    b.left.action_state = "attacking"
    b.left.attack_phase = "windup"
    b.elapsed_ms = 0
    assert d.decide(b)[0] == 0     # can't act → idle emitted, delay accumulates
    b.elapsed_ms = 16
    assert d.decide(b)[0] == 0
    # Free the actor; the FIRST event should now fire, not be skipped
    b.left.action_state = "idle"
    b.left.attack_phase = "none"
    b.elapsed_ms = 32
    assert d.decide(b)[0] == 2     # advance finally fires
    # The second event was scheduled at t=100; with delay 32ms already
    # accumulated, it fires at t>=132 (NOT at t>=100).
    b.elapsed_ms = 100
    assert d.decide(b)[0] == 0     # not yet
    b.elapsed_ms = 132
    assert d.decide(b)[0] == 1     # retreat fires (shifted)


def test_root_blocks_movement_but_not_cast():
    # Movement (advance) is blocked under root; cast is NOT blocked.
    left = [TimelineEvent(t=0, action_int=2, raw_do="advance")]
    right = [TimelineEvent(t=0, action_int=5, raw_do="cast:light_binding",
                           skill_id="light_binding")]
    b, d = _two_char_battle(left, right)
    b.left.effects.append(StatusEffect(kind=ROOT, remaining_ms=2000, magnitude=1.0))
    # right is not rooted
    b.elapsed_ms = 0
    left_act, right_act = d.decide(b)
    assert left_act == 0     # movement blocked
    assert right_act == 5    # cast still fires


def test_cast_sets_pending_skill_id_on_character():
    left = [TimelineEvent(t=0, action_int=5, raw_do="cast:light_binding",
                          skill_id="light_binding")]
    right = []
    b, d = _two_char_battle([], left)   # put on right (lux) since light_binding is Lux's
    # (above: swap order so right has the cast event)
    b.elapsed_ms = 0
    d.decide(b)
    assert b.right.pending_cast_skill_id == "light_binding"


def test_per_character_independence():
    # Left delayed (mid-attack) but right's events fire on schedule.
    left = [TimelineEvent(t=0, action_int=2, raw_do="advance"),
            TimelineEvent(t=500, action_int=2, raw_do="advance")]
    right = [TimelineEvent(t=500, action_int=1, raw_do="retreat")]
    b, d = _two_char_battle(left, right)
    b.left.action_state = "attacking"
    b.left.attack_phase = "windup"
    b.elapsed_ms = 500
    left_act, right_act = d.decide(b)
    assert left_act == 0     # delayed
    assert right_act == 1    # fires on time — right's clock unaffected


def test_exhausted_cursor_emits_idle():
    left = [TimelineEvent(t=0, action_int=2, raw_do="advance")]
    right = []
    b, d = _two_char_battle(left, right)
    b.elapsed_ms = 0
    d.decide(b)
    b.elapsed_ms = 5000
    assert d.decide(b) == (0, 0)     # both exhausted → idle
