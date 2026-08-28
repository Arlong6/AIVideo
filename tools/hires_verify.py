"""Verify a hi-res render against a pre-change baseline.

Two independent checks:
  compare_events  — the fight itself must be untouched (same events, same
                    timings, same winner). Physics is not scaled, so any
                    difference here means the shim leaked into game logic.
  frame_ssim      — the new frame, downscaled back to baseline size, must
                    match the baseline. This is what catches an element
                    whose coordinates were never multiplied by S.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity


def _load(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def compare_events(baseline_json, current_json) -> list[str]:
    """Return human-readable differences. Empty list means identical."""
    a, b = _load(baseline_json), _load(current_json)
    diffs: list[str] = []

    for key in ("winner", "terminated", "n_frames"):
        if a.get(key) != b.get(key):
            diffs.append(f"{key}: baseline={a.get(key)!r} current={b.get(key)!r}")

    ea, eb = a.get("events", []), b.get("events", [])
    if len(ea) != len(eb):
        diffs.append(f"event count: baseline={len(ea)} current={len(eb)}")
    else:
        for i, (x, y) in enumerate(zip(ea, eb)):
            if x != y:
                diffs.append(f"event[{i}]: baseline={x!r} current={y!r}")

    # Keys are CPython id()s (memory addresses) — never portable across
    # process invocations, so comparing the dicts directly is a guaranteed
    # false positive between any two separate runs. Values in insertion
    # order (dict insertion order == events list order) carry the actual
    # timing data, so compare those instead.
    ma, mb = a.get("event_video_ms", {}), b.get("event_video_ms", {})
    if list(ma.values()) != list(mb.values()):
        diffs.append("event_video_ms differs")

    return diffs


def frame_ssim(baseline_png, current_png) -> float:
    """SSIM after downscaling `current` to the baseline's dimensions."""
    base = Image.open(baseline_png).convert("RGB")
    cur = Image.open(current_png).convert("RGB")
    if cur.size != base.size:
        cur = cur.resize(base.size, Image.LANCZOS)
    a = np.asarray(base, dtype=np.float64)
    b = np.asarray(cur, dtype=np.float64)
    return float(structural_similarity(a, b, channel_axis=2, data_range=255.0))


def report(baseline_dir, current_dir, ssim_floor: float = 0.92) -> int:
    """Print a full comparison. Returns the number of problems found.

    ssim_floor default 0.92 was calibrated on real b01/b12 baseline vs
    current frames — 0.90 passed frames that were visibly defective
    (HUD/banner mis-scaling clearly present to the eye). Re-calibrated
    2026-08-28 against the native hi-res re-sampling pipeline: every
    observed defect frame (double-scaled elements) scored <=0.9113, while
    every confirmed-clean but VFX-busy frame (native-vs-downscaled
    antialiasing noise only, no misplaced/mis-sized element) scored
    >=0.9238 — 0.92 sits in the gap and separates the two populations.
    """
    baseline_dir, current_dir = Path(baseline_dir), Path(current_dir)
    problems = 0

    diffs = compare_events(baseline_dir / "events.json",
                           current_dir / "events.json")
    if diffs:
        problems += len(diffs)
        print("FIGHT BEHAVIOUR CHANGED — the shim leaked into game logic:")
        for d in diffs:
            print("  -", d)
    else:
        print("fight behaviour: identical")

    print("\nframe structure (SSIM after downscale):")
    frames = sorted(baseline_dir.glob("frame_*.png"))
    if not frames:
        print(f"  NO BASELINE FRAMES FOUND in {baseline_dir}")
        problems += 1
    else:
        for bp in frames:
            cp = current_dir / bp.name
            if not cp.exists():
                print(f"  {bp.name}: MISSING in current")
                problems += 1
                continue
            s = frame_ssim(bp, cp)
            flag = "ok" if s >= ssim_floor else "LOW"
            if s < ssim_floor:
                problems += 1
            print(f"  {bp.name}: {s:.4f} {flag}")

    print(f"\nproblems: {problems}")
    return problems


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[1]
    b = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        root / "pixel_battle/output/hires_baseline/b01"
    c = Path(sys.argv[2]) if len(sys.argv) > 2 else \
        root / "pixel_battle/output/hires_current/b01"
    raise SystemExit(1 if report(b, c) else 0)
