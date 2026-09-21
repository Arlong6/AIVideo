"""Decide when each meme sticker appears, from what actually happened in the fight.

Density is the whole design here. An effect on every hit — thirty-plus per video —
stops being information and becomes texture; the viewer tunes it out by the third
short and the moments that matter no longer stand out. So a cue is spent only
where the fight itself already changed: a crit, the whiff in the dead middle, the
wind-up to the finisher, the finisher landing. Five to eight per video.

Placement is deliberately spread across the retention checkpoints rather than
evenly: something lands near 3s, near 10s, near 20s, and then the run-in to the
ultimate. A 53-second video whose only payoff is at 45s has to keep giving the
viewer reasons in between.

All times here are SHORT seconds — video_ms with build_short's CUT_START already
subtracted. `timeline.short_t` is the only place that conversion happens.
"""
from __future__ import annotations

from pixel_battle.video.timeline import short_t

# A pop is three scales in quick succession, then the full-size hold.
POP_FRAMES = 2          # frames per scale step, at the output frame rate
POP_HOLD_S = 0.30       # how long the settled sticker stays after the pop

MIN_GAP_S = 3.5         # never two cues closer than this
MAX_POWS = 3            # crits are frequent; only the biggest few earn a sticker

BRUH_WINDOW = (11.0, 22.0)   # the valley a 53s fight has to survive
FINAL_LEAD_S = 1.15          # how early the pre-ultimate band comes up


def _pop(name: str, t: float, fps: int = 30, hold: float = POP_HOLD_S) -> list[dict]:
    """Three scale steps then a hold — a snap-in without ffmpeg's zoompan."""
    step = POP_FRAMES / fps
    return [
        {"asset": f"{name}_72", "start": t, "end": t + step},
        {"asset": f"{name}_112", "start": t + step, "end": t + 2 * step},
        {"asset": f"{name}_100", "start": t + 2 * step, "end": t + 2 * step + hold},
    ]


def plan(timeline: list[dict], cut_start_ms: int = 1500,
         fps: int = 30) -> list[dict]:
    """Return ffmpeg overlay cues, ordered, non-overlapping."""
    ev = [e for e in timeline if e["video_ms"] >= cut_start_ms]
    cues: list[dict] = []
    taken: list[float] = []

    def free(t: float) -> bool:
        return all(abs(t - u) >= MIN_GAP_S for u in taken)

    # The finisher, and the band that leads into it. Placed first because they
    # are the climax and must not be crowded out by an earlier crit.
    ult = next((e for e in ev if e["type"] == "ultimate_start"), None)
    ko = next((e for e in ev if e["type"] == "ko"), None)

    if ult:
        t = max(0.0, short_t(ult["video_ms"], cut_start_ms) - FINAL_LEAD_S)
        cues += [{"asset": "final_100", "start": t, "end": t + FINAL_LEAD_S + 0.25}]
        taken.append(t)
    if ko:
        t = short_t(ko["video_ms"], cut_start_ms)
        cues += _pop("boom", t, fps, hold=0.55)
        taken.append(t)

    # Crits, biggest first, so a video with many of them keeps the best ones.
    crits = sorted((e for e in ev if e["crit"] or e["type"] == "crit"),
                   key=lambda e: -e["amount"])
    used = 0
    for e in crits:
        if used >= MAX_POWS:
            break
        t = short_t(e["video_ms"], cut_start_ms)
        if t < 1.5 or not free(t):
            continue
        cues += _pop("pow", t, fps)
        taken.append(t)
        used += 1

    # One deadpan beat in the valley, where the fight is otherwise just trading.
    lo, hi = BRUH_WINDOW
    miss = next((e for e in ev if e["type"] == "miss"
                 and lo <= short_t(e["video_ms"], cut_start_ms) <= hi
                 and free(short_t(e["video_ms"], cut_start_ms))), None)
    if miss:
        t = short_t(miss["video_ms"], cut_start_ms)
        cues += _pop("bruh", t, fps, hold=0.45)
        taken.append(t)

    return sorted(cues, key=lambda c: c["start"])
