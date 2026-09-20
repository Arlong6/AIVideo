"""Report each fight's hit distribution by simulation — no video encoding.

A fight can pick a correct winner and still be unwatchable. b12_shade_deadeye
lands ten hits in its first 6.5 seconds and then nothing at all until the KO at
~44s: two ranged fighters holding distance, neither closing. That is 38 seconds
of dead air, and no amount of overlay work in post rescues it — the fix belongs
in the fight script.

check_winners.py already proves the simulation alone answers questions that
would otherwise cost a 3.5-minute render. This asks the pacing question the same
way, so a whole batch can be audited in seconds before committing to a re-render.

Stepping goes through tools/sim_render.py, which advances the battle the way the
renderer does rather than at a constant dt — a constant-dt loop measures a
different fight, badly enough to name the wrong winner on a thin HP margin.

Times here are ENGINE ms, not video ms: slow-mo and hitstop stretch the recorded
video (b01's KO is at engine 45404 but video 47850). That divergence is small
next to the gaps this tool is looking for. Do not reuse these numbers to cue
overlays — use the renderer's own event_video_ms for that.

Usage:
  python3 tools/check_pacing.py                      # every b*.yaml
  python3 tools/check_pacing.py b12 b18              # prefix match
  python3 tools/check_pacing.py --max-gap 5.0        # stricter threshold
  python3 tools/check_pacing.py --json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

# A viewer forgives a couple of seconds between blows; six is a stall. Chosen
# against the measured spread: b01 (healthy) peaks at 3.2s, b12 (broken) at 37.8s.
DEFAULT_MAX_GAP = 6.0

# Events that read on screen as "something landed".
IMPACT_TYPES = {"hit", "crit", "ko"}


def simulate(path: Path) -> dict:
    """Run the fight the way the RENDERER advances it and return its impacts.

    This used to be a plain env.step() loop. That is not how the fight plays on
    screen: the render loop ticks the engine at a fraction of ENGINE_MS whenever
    slow-mo is active, which hands the choreography many more decisions per
    engine-millisecond. The difference is not academic — on a thin HP margin the
    pure loop predicted the wrong winner outright. See tools/sim_render.py.
    """
    from sim_render import simulate as _sim
    r = _sim(path)
    return {"impacts": r["impacts"],
            "end_s": (r["events"][-1].t_ms / 1000.0) if r["events"] else 0.0}


def analyse(sim: dict, max_gap: float) -> dict:
    """Turn a timeline into the numbers that decide whether it is watchable."""
    hits, end_s = sim["impacts"], sim["end_s"]
    if not hits:
        return {"n": 0, "max_gap": end_s, "gap_at": 0.0, "end_s": end_s,
                "ok": False, "why": "no impacts at all"}

    # The lead-in and the tail count: silence before the first blow and after
    # the last one is just as dead as silence in the middle.
    marks = [0.0] + hits + [end_s]
    gaps = [(marks[i + 1] - marks[i], marks[i]) for i in range(len(marks) - 1)]
    worst, at = max(gaps, key=lambda g: g[0])
    ok = worst <= max_gap
    return {"n": len(hits), "max_gap": round(worst, 1), "gap_at": round(at, 1),
            "end_s": round(end_s, 1), "ok": ok,
            "why": "" if ok else f"{worst:.1f}s with nothing landing, from {at:.1f}s"}


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    max_gap = DEFAULT_MAX_GAP
    if "--max-gap" in sys.argv:
        max_gap = float(sys.argv[sys.argv.index("--max-gap") + 1])

    scripts = sorted((ROOT / "pixel_battle/data/scripts").glob("b*.yaml"))
    if args:
        scripts = [p for p in scripts if any(p.name.startswith(a) for a in args)]
    if not scripts:
        print("no matching fight scripts", file=sys.stderr)
        return 2

    rows, bad = [], 0
    for p in scripts:
        try:
            r = analyse(simulate(p), max_gap)
        except Exception as e:              # one bad file must not hide the rest
            print(f"{p.stem:26} ERROR {type(e).__name__}: {e}")
            rows.append({"stem": p.stem, "error": f"{type(e).__name__}: {e}"})
            bad += 1
            continue
        r["stem"] = p.stem
        rows.append(r)
        if not r["ok"]:
            bad += 1
        if not as_json:
            flag = "  OK  " if r["ok"] else " STALL"
            print(f"{flag} {p.stem:26} impacts={r['n']:3}  "
                  f"max_gap={r['max_gap']:5.1f}s @ {r['gap_at']:5.1f}s  "
                  f"len={r['end_s']:5.1f}s  {r['why']}")

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"\n{len(rows) - bad}/{len(rows)} within {max_gap:.0f}s max gap")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
