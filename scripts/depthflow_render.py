"""DepthFlow batch renderer — runs inside the DepthFlow sidecar venv
(Python 3.13; see DEPTHFLOW_PYTHON), NOT the pipeline venv.

Usage: <sidecar-python> scripts/depthflow_render.py <jobs.json>

jobs.json: [{"image": ..., "output": ..., "duration": 6.0, "preset": "orbital"}, ...]

Renders every job in ONE process so torch/model load is paid once
(~8s/clip warm vs ~20s+ if spawned per clip). Prints one line per job:
  OK <output>      — rendered and file exists
  FAIL <output> <reason>
Exit code 0 if at least one job succeeded, 2 if all failed.

The caller (illustration_generator._depthflow_batch) treats any FAIL line
or missing file as "fall back to Ken Burns for that clip".
"""
import json
import sys
import time
from pathlib import Path

PRESETS = {}


def _load_presets():
    """Import lazily so a broken install produces FAIL lines, not a crash."""
    from depthflow.examples import presets as p
    PRESETS.update({
        "orbital": p.Orbital,
        "dolly": p.Dolly,
        "horizontal": p.Horizontal,
        "zoomin": getattr(p, "ZoomIn", p.Dolly),
        "circle": getattr(p, "Circle", p.Orbital),
    })


def main() -> int:
    jobs = json.loads(Path(sys.argv[1]).read_text())
    _load_presets()
    ok_count = 0
    for job in jobs:
        out = job["output"]
        try:
            t0 = time.time()
            cls = PRESETS.get(job.get("preset", "orbital"), PRESETS["orbital"])
            scene = cls()
            # Parallax strength: 0.15-0.25 keeps noir edges from smearing.
            try:
                scene.state.height = float(job.get("strength", 0.2))
            except Exception:
                pass
            scene.input(image=job["image"])
            scene.main(
                output=out,
                time=float(job.get("duration", 6.0)),
                fps=int(job.get("fps", 25)),
                width=int(job.get("width", 1920)),
                height=int(job.get("height", 1080)),
            )
            if Path(out).exists() and Path(out).stat().st_size > 0:
                ok_count += 1
                print(f"OK {out} ({time.time()-t0:.1f}s)", flush=True)
            else:
                print(f"FAIL {out} empty-output", flush=True)
        except Exception as e:
            print(f"FAIL {out} {type(e).__name__}: {e}", flush=True)
    return 0 if ok_count else 2


if __name__ == "__main__":
    sys.exit(main())
