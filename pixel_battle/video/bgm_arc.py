"""Shape the BGM so the music itself carries the fight's tension.

The loop used to play flat from first frame to last. That is a lot of音樂 asked
to do nothing: the most tense moment in every video is the second or so before
the finisher lands, and the cheapest way to make a viewer feel it is to take the
music away. Silence right before an impact is louder than any effect layered on
top of one.

Two shapes, both applied to the BGM samples before they reach the mixer bus,
because the bus holds a single placement and editing the samples is simpler than
adding gain automation to the export graph:

  pre-ult dip   a fade down to near-silence over ~1.2s ending exactly on the
                ultimate, then a fast return. The hit lands in the gap.
  tail lift     the last stretch after the KO comes back up, so the video does
                not end on a hole.

Everything is expressed in VIDEO milliseconds, which is what the mixer places
samples in — engine time diverges from it whenever slow-mo is active.
"""
from __future__ import annotations

import numpy as np

PRE_ULT_DIP_MS = 1200.0     # how long the fade down runs
PRE_ULT_FLOOR = 0.12        # gain at the bottom of the dip (not zero: a hard cut clicks)
POST_ULT_RETURN_MS = 450.0  # how fast it comes back after the ultimate fires


def apply_pre_ult_dip(samples: np.ndarray, sample_rate: int,
                      ult_video_ms: int | None) -> np.ndarray:
    """Fade the music out into the ultimate and bring it back after.

    Returns the samples unchanged when there is no ultimate to aim at, so a
    fight that ends by timeout still gets a normal music bed.
    """
    if ult_video_ms is None or len(samples) == 0:
        return samples

    out = samples.astype(np.float32, copy=True)
    n = len(out)
    hit = int(ult_video_ms / 1000.0 * sample_rate)
    if hit <= 0 or hit >= n:
        return samples

    dip_start = max(0, hit - int(PRE_ULT_DIP_MS / 1000.0 * sample_rate))
    if hit > dip_start:
        # Cosine ease rather than linear: a straight ramp is audible as a
        # mechanical slide, an ease reads as the music backing off.
        t = np.linspace(0.0, 1.0, hit - dip_start, dtype=np.float32)
        ease = 0.5 * (1.0 + np.cos(np.pi * t))          # 1 -> 0
        out[dip_start:hit] *= PRE_ULT_FLOOR + (1.0 - PRE_ULT_FLOOR) * ease

    ret_end = min(n, hit + int(POST_ULT_RETURN_MS / 1000.0 * sample_rate))
    if ret_end > hit:
        t = np.linspace(0.0, 1.0, ret_end - hit, dtype=np.float32)
        out[hit:ret_end] *= PRE_ULT_FLOOR + (1.0 - PRE_ULT_FLOOR) * t
    return out


def ult_video_ms_from(events, event_video_ms) -> int | None:
    """Video-ms of the ultimate, or None if the fight never got there.

    `event_video_ms` is keyed by `id(ev)` — Python object addresses, valid only
    while the same objects are alive in this process. That is fine here, where
    both come straight out of the same _render_fight call, and is exactly why
    this must not be handed a deserialized event list.
    """
    for ev in events:
        if ev.type.value == "ultimate_start":
            pos = event_video_ms.get(id(ev))
            if pos is not None:
                return int(pos)
    return None
