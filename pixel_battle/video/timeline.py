"""Export a fight's event timeline in VIDEO time, for post-production to cue on.

Post-production has been blind to what happens inside a fight. build_shorts_batch
already intercepts the full return of `_render_fight` — which carries `events` and
`event_video_ms` — and then reads only the winner out of it, discarding the rest.
So the timing has always been there; nothing consumed it.

Three time bases have to be kept straight, and getting them confused puts every
overlay in the wrong place:

  ev.t_ms          ENGINE time. Diverges from the video whenever slow-mo is
                   active — b01's KO is at engine 45404 but video 47850, a
                   2.4-second error if used directly.
  video_ms         time in the RAW render. This is what the mixer places audio
                   at, and what overlays must key on.
  short seconds    video_ms minus build_short's CUT_START, which trims the spawn
                   intro off the front.

`event_video_ms` is keyed by `id(ev)` — Python object addresses, meaningless once
anything is serialized. This module re-keys by event index while both are still
in memory, which is the only place that mapping is valid.
"""
from __future__ import annotations

import json
from pathlib import Path


def build(events, event_video_ms: dict) -> list[dict]:
    """Flat, JSON-safe records in video time, in order."""
    out = []
    for i, ev in enumerate(events):
        pos = event_video_ms.get(id(ev))
        if pos is None:
            continue                      # the pre-loop INTRO carries no frame
        extra = ev.extra or {}
        out.append({
            "i": i,
            "type": ev.type.value,
            "t_ms": int(ev.t_ms),
            "video_ms": int(pos),
            "actor": ev.actor,
            "target": ev.target,
            "amount": int(getattr(ev, "amount", 0) or 0),
            "crit": bool(extra.get("crit", False)),
            "skill_id": extra.get("skill_id"),
            "skill_type": extra.get("skill_type"),
        })
    return out


def write(path: Path, stem: str, fight: dict, cut_start_ms: int = 1500) -> Path:
    """Write the sidecar next to the raw render."""
    timeline = build(fight["events"], fight["event_video_ms"])
    payload = {
        "schema": 1,
        "stem": stem,
        "fps": 60,
        "n_frames": int(fight.get("n_frames") or 0),
        "winner": fight.get("winner"),
        "cut_start_ms": int(cut_start_ms),
        "timeline": timeline,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def short_t(video_ms: int, cut_start_ms: int = 1500) -> float:
    """video_ms -> seconds in the FINAL short. The only place this sum happens."""
    return max(0.0, (video_ms - cut_start_ms) / 1000.0)
