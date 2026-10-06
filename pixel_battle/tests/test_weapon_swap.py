# pixel_battle/tests/test_weapon_swap.py
"""Mid-fight WEAPON SWAP: script verb -> engine event -> renderer lookup -> cue."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pytest

from pixel_battle.engine.battle import Battle, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.rl import weapons
from pixel_battle.script.timeline_driver import TimelineDriver
from pixel_battle.script.timeline_format import SWAP_VERB, Timeline, TimelineEvent
from pixel_battle.script.timeline_loader import load_timeline_text
from pixel_battle.video import cue_plan


@pytest.fixture(autouse=True)
def _clean_swap_state():
    weapons.reset_swaps()
    yield
    weapons.reset_swaps()


def test_loader_accepts_swap_verb_as_idle():
    tl = load_timeline_text("""
name: t
left: ashe
right: pantheon
duration_ms: 5000
left_timeline:
  - {t: 100, do: swap_weapon}
right_timeline:
  - {t: 0, do: idle}
""")
    ev = tl.left_events[0]
    assert ev.action_int == 0 and ev.raw_do == SWAP_VERB and ev.skill_id is None


def _battle(left_events):
    left, right = Character.load("ashe"), Character.load("pantheon")
    b = Battle(left, right, rng=BattleRNG(seed=0))
    d = TimelineDriver(Timeline(name="t", left="ashe", right="pantheon", duration_ms=5000,
                                left_events=left_events, right_events=[]))
    return b, d


def test_driver_flags_swap_and_engine_logs_it_in_the_tick():
    b, d = _battle([TimelineEvent(t=500, action_int=0, raw_do=SWAP_VERB)])
    b.elapsed_ms = 499
    assert d.decide(b) == (0, 0) and not b.left.pending_weapon_swap
    b.elapsed_ms = 500
    assert d.decide(b) == (0, 0)
    # decide() only flags: the renderer snapshots its event cursor between
    # decide and step, so the event must come from the tick itself.
    assert b.left.pending_weapon_swap and not b.events
    b.tick_ms(16, skip_ai=True)
    swaps = [e for e in b.events if e.type == EventType.WEAPON_SWAP]
    assert len(swaps) == 1 and swaps[0].actor == "ashe" and swaps[0].t_ms == 516
    assert not b.left.pending_weapon_swap
    d.decide(b); b.tick_ms(16, skip_ai=True)
    assert sum(1 for e in b.events if e.type == EventType.WEAPON_SWAP) == 1


def test_driver_waits_out_an_attack_before_swapping():
    b, d = _battle([TimelineEvent(t=0, action_int=0, raw_do=SWAP_VERB)])
    b.left.action_state = "attacking"
    assert d.decide(b) == (0, 0)
    assert not b.left.pending_weapon_swap and d._left.delay_ms > 0
    b.left.action_state = "idle"
    b.elapsed_ms = d._left.delay_ms
    d.decide(b)
    assert b.left.pending_weapon_swap


def test_registry_follows_live_state_and_explicit_flag():
    assert weapons.get_weapon("ashe").kind == "bow"
    assert weapons.get_weapon("ashe", swapped=True).kind == "daggers"
    weapons.apply_swap("ashe")
    assert weapons.get_weapon("ashe").kind == "daggers"
    assert weapons.get_weapon("ashe", swapped=False).kind == "bow"
    assert weapons.get_weapon("pantheon").kind == "spear"     # untouched
    weapons.reset_swaps()
    assert weapons.get_weapon("ashe").kind == "bow"


def test_every_secondary_is_a_kind_the_renderer_draws():
    import re
    from pathlib import Path
    src = Path(weapons.__file__).read_text(encoding="utf-8")
    drawn = set(re.findall(r'weapon\.kind == "([a-z_]+)"', src))
    for cid, w in weapons._SECONDARY.items():
        assert w.kind in drawn, (cid, w.kind)
        assert w.kind != weapons._WEAPONS[cid].kind, cid     # a swap must be visible


def test_cue_plan_marks_the_swap_after_the_toss():
    timeline = [
        {"type": "weapon_swap", "video_ms": 30000, "actor": "ashe", "crit": False, "amount": 0},
        {"type": "ultimate_start", "video_ms": 46000, "crit": False, "amount": 0},
        {"type": "ko", "video_ms": 48000, "crit": False, "amount": 0},
    ]
    picked = cue_plan.select(timeline)
    sw = [p for p in picked if p["kind"] == "swap"]
    assert sw and sw[0]["video_ms"] == 30000 + cue_plan.SWAP_CLANK_MS
    sounds = [a["asset"] for a in cue_plan.audio_cues(picked)]
    assert "meme_pipe" in sounds and "meme_wobble" in sounds
    assert not [v for v in cue_plan.visual_cues(picked) if v["asset"].startswith("swap")]
