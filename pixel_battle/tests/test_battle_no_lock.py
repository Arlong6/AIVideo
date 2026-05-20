"""Regression test: a 60s simulated battle should not have 5+ second event-free gaps
(excluding cinematic playback windows).
"""
from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def _longest_event_gap_excluding_cinematics(events, total_ms):
    """Return the longest gap (ms) between consecutive HIT/MISS events,
    skipping the ULTIMATE_START → ULTIMATE_END windows.
    """
    # Build "active" timeline by clipping out cinematic windows
    cinematic_intervals = []
    starts = [e for e in events if e.type is EventType.ULTIMATE_START]
    ends = [e for e in events if e.type is EventType.ULTIMATE_END]
    for s, e in zip(starts, ends):
        cinematic_intervals.append((s.t_ms, e.t_ms))
    # A trailing ultimate can start near the window end and never emit its
    # ULTIMATE_END before the 60s cutoff — treat it as cinematic to the end.
    if len(starts) > len(ends):
        cinematic_intervals.append((starts[len(ends)].t_ms, total_ms))

    def in_cinematic(t):
        return any(start <= t <= end for start, end in cinematic_intervals)

    action_events = [e for e in events
                     if e.type in (EventType.HIT, EventType.MISS)
                     and not in_cinematic(e.t_ms)]

    if not action_events:
        return total_ms  # no events at all = max gap
    timestamps = [0] + [e.t_ms for e in action_events] + [total_ms]
    # Drop any pair where a cinematic spans between them — subtract cinematic duration
    max_gap = 0
    for i in range(len(timestamps) - 1):
        a, b = timestamps[i], timestamps[i + 1]
        gap = b - a
        # Subtract any cinematic time inside this gap
        for cs, ce in cinematic_intervals:
            if cs >= a and ce <= b:
                gap -= (ce - cs)
        max_gap = max(max_gap, gap)
    return max_gap


def test_60s_battle_no_long_gaps():
    """Run a 60-second battle and assert max event-free gap < 5s (excluding cinematics)."""
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(1))
    while bat.elapsed_ms < 60_000 and bat.state is not BattleState.KO:
        bat.tick_ms(16)
    gap = _longest_event_gap_excluding_cinematics(bat.events, bat.elapsed_ms)
    assert gap < 5000, f"AI lock detected: longest event-free gap = {gap}ms"
