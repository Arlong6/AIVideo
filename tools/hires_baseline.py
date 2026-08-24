"""Capture a render baseline: fight events + sampled frames.

Used to prove the native hi-res work changes nothing about the fight and
nothing about frame composition. Run BEFORE touching render code.

This reuses play_scripted.render_script rather than reassembling the render
itself — that function owns arena selection, timeline seeding and start
HP/MP overrides, and a hand-rolled copy would drift from the real pipeline.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame  # noqa: E402

# Frames sampled across the fight arc: open, melee, ranged standoff,
# special cast, ultimate, KO aftermath. Frame numbers at 60fps.
DEFAULT_FRAMES = (60, 600, 1200, 1800, 2400, 2900, 3200)


def capture(script_path: Path, out_dir: Path,
            frame_indices=DEFAULT_FRAMES) -> dict:
    """Render `script_path` via the real pipeline, recording events + frames."""
    import pixel_battle.rl.play_scripted as ps
    from pixel_battle.video.recorder import FrameRecorder

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = set(frame_indices)
    grabbed: dict[int, object] = {}
    captured: dict = {}

    class _TapRecorder(FrameRecorder):
        """Writes frames as usual, and snapshots the sampled indices."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._n = 0

        def write_frame(self, surface):
            if self._n in wanted:
                grabbed[self._n] = surface.copy()
            self._n += 1
            return super().write_frame(surface)

    orig_recorder = ps.FrameRecorder
    orig_render_fight = ps._render_fight

    def _tap_render_fight(*a, **k):
        result = orig_render_fight(*a, **k)
        captured.update(result)
        return result

    ps.FrameRecorder = _TapRecorder
    ps._render_fight = _tap_render_fight
    try:
        ps.render_script(Path(script_path), out_dir)
    finally:
        ps.FrameRecorder = orig_recorder
        ps._render_fight = orig_render_fight

    for idx, surf in grabbed.items():
        pygame.image.save(surf, str(out_dir / f"frame_{idx:05d}.png"))

    sample = next(iter(grabbed.values()), None)
    payload = {
        "n_frames": captured.get("n_frames"),
        "winner": captured.get("winner"),
        "terminated": captured.get("terminated"),
        "events": captured.get("events", []),
        "event_video_ms": captured.get("event_video_ms", {}),
        "canvas": list(sample.get_size()) if sample is not None else None,
        "frames_captured": sorted(grabbed),
    }
    (out_dir / "events.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    return payload


if __name__ == "__main__":
    script = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        ROOT / "pixel_battle/data/scripts/b01_lumen_jugg.yaml"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        ROOT / "pixel_battle/output/hires_baseline"
    p = capture(script, out)
    print(f"baseline: {p['n_frames']} frames, winner={p['winner']}, "
          f"{len(p['events'])} events, canvas={p['canvas']}, "
          f"frames={p['frames_captured']}")
