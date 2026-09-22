"""Decide the meme beats of a fight, once, for both the picture and the sound.

Density is the whole design here. An effect on every hit — thirty-plus per video
— stops being information and becomes texture; the viewer tunes it out by the
third short and the moments that matter no longer stand out. So a beat is spent
only where the fight itself already changed: a crit, the whiff in the dead
middle, the wind-up to the finisher, the finisher landing. Five to eight a video.

Placement is spread across the retention checkpoints rather than evenly:
something lands near 3s, near 10s, near 20s, then the run-in to the ultimate. A
53-second video whose only payoff is at 45s has to keep giving reasons in
between.

ONE SELECTION, TWO OUTPUTS. `select()` chooses the moments; `visual_cues()` and
`audio_cues()` both read from that. A sticker without its sound is half an
effect, and the two computed separately would eventually drift apart — the kind
of bug nobody notices until a viewer sees a comic POW land a beat after the
clang. Their time bases differ (overlays are cued in SHORT seconds, the mixer
places audio in VIDEO ms) and that conversion lives in exactly one place.
"""
from __future__ import annotations

from pixel_battle.video.timeline import short_t

# A pop is three scales in quick succession, then the full-size hold.
POP_FRAMES = 2          # frames per scale step, at the output frame rate
POP_HOLD_S = 0.30       # how long the settled sticker stays after the pop

MIN_GAP_S = 3.5         # never two beats closer than this
MAX_POWS = 3            # crits are frequent; only the biggest few earn one

BRUH_WINDOW = (11.0, 22.0)   # the valley a 53s fight has to survive
FINAL_LEAD_S = 1.15          # how early the pre-ultimate band comes up
OPENING_MS = 900             # the announcer call, over the hook

# kind -> (sticker base name or None, sound name or None)
BEATS = {
    "opening": (None, "meme_1on1"),
    "crit": ("pow", "meme_pipe"),
    "whiff": ("bruh", "meme_denied"),
    "preult": ("final", "meme_domination"),
    "ko": ("boom", "meme_fragged"),
}


def select(timeline: list[dict], cut_start_ms: int = 1500) -> list[dict]:
    """The moments worth marking, as {kind, video_ms}, in order."""
    ev = [e for e in timeline if e["video_ms"] >= cut_start_ms]
    picked: list[dict] = []
    taken: list[float] = []

    def free(t: float) -> bool:
        return all(abs(t - u) >= MIN_GAP_S for u in taken)

    def take(kind: str, video_ms: int) -> None:
        picked.append({"kind": kind, "video_ms": int(video_ms)})
        taken.append(short_t(video_ms, cut_start_ms))

    take("opening", cut_start_ms + OPENING_MS)

    # The finisher and its lead-in go in first: they are the climax and must not
    # be crowded out by an earlier crit that happens to be nearby.
    ult = next((e for e in ev if e["type"] == "ultimate_start"), None)
    ko = next((e for e in ev if e["type"] == "ko"), None)
    if ult:
        take("preult", max(cut_start_ms,
                           ult["video_ms"] - int(FINAL_LEAD_S * 1000)))
    if ko:
        take("ko", ko["video_ms"])

    # Crits, biggest first, so a busy fight keeps its best ones.
    used = 0
    for e in sorted((x for x in ev if x["crit"] or x["type"] == "crit"),
                    key=lambda x: -x["amount"]):
        if used >= MAX_POWS:
            break
        t = short_t(e["video_ms"], cut_start_ms)
        if t < 1.5 or not free(t):
            continue
        take("crit", e["video_ms"])
        used += 1

    # One deadpan beat in the valley, where the fight is otherwise just trading.
    lo, hi = BRUH_WINDOW
    miss = next((e for e in ev if e["type"] == "miss"
                 and lo <= short_t(e["video_ms"], cut_start_ms) <= hi
                 and free(short_t(e["video_ms"], cut_start_ms))), None)
    if miss:
        take("whiff", miss["video_ms"])

    return sorted(picked, key=lambda p: p["video_ms"])


def _pop(name: str, t: float, fps: int, hold: float) -> list[dict]:
    """Three scale steps then a hold — a snap-in without ffmpeg's zoompan."""
    step = POP_FRAMES / fps
    return [
        {"asset": f"{name}_72", "start": t, "end": t + step},
        {"asset": f"{name}_112", "start": t + step, "end": t + 2 * step},
        {"asset": f"{name}_100", "start": t + 2 * step, "end": t + 2 * step + hold},
    ]


def visual_cues(picked: list[dict], cut_start_ms: int = 1500,
                fps: int = 30) -> list[dict]:
    """ffmpeg overlay cues, in SHORT seconds."""
    out: list[dict] = []
    for p in picked:
        sticker, _ = BEATS[p["kind"]]
        if not sticker:
            continue
        t = short_t(p["video_ms"], cut_start_ms)
        if p["kind"] == "preult":
            out.append({"asset": "final_100", "start": t,
                        "end": t + FINAL_LEAD_S + 0.25})
        else:
            out += _pop(sticker, t, fps,
                        hold=0.55 if p["kind"] == "ko" else
                        (0.45 if p["kind"] == "whiff" else POP_HOLD_S))
    return sorted(out, key=lambda c: c["start"])


def audio_cues(picked: list[dict]) -> list[dict]:
    """Mixer placements, in VIDEO ms — the same beats the stickers use.

    The pipe gets its wobble tail 240ms behind the clang. That settling rattle
    is most of why the sound reads as a dropped metal pipe rather than a generic
    impact, and the engine's own hit SFX already covers the strike itself.
    """
    out: list[dict] = []
    for p in picked:
        _, sound = BEATS[p["kind"]]
        if not sound:
            continue
        out.append({"asset": sound, "video_ms": p["video_ms"]})
        if p["kind"] == "crit":
            out.append({"asset": "meme_wobble", "video_ms": p["video_ms"] + 240})
    return sorted(out, key=lambda c: c["video_ms"])


def plan(timeline: list[dict], cut_start_ms: int = 1500,
         fps: int = 30) -> list[dict]:
    """Back-compat shim for callers that only want the overlays."""
    return visual_cues(select(timeline, cut_start_ms), cut_start_ms, fps)
