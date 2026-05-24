import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from pathlib import Path
import yaml

from pixel_battle.scripts.dump_timeline import dump_timeline_for


def test_dumps_a_parseable_timeline(tmp_path):
    legacy = Path("pixel_battle/data/scripts/legacy/01_lux_kite_garen.yaml")
    # Skip if the legacy file isn't there yet (Task 7 archives it later);
    # for this Task 6 test we point at any existing condition script.
    if not legacy.exists():
        legacy = Path("pixel_battle/data/scripts/01_lux_kite_garen.yaml")
    out = tmp_path / "trace.yaml"
    dump_timeline_for(legacy, out)
    assert out.exists()
    data = yaml.safe_load(out.read_text())
    assert "left_timeline" in data
    assert "right_timeline" in data
    # At least the LEFT or RIGHT timeline should have non-idle events emitted
    # during the legacy simulation
    total_events = len(data["left_timeline"]) + len(data["right_timeline"])
    assert total_events >= 4, (
        f"trace has too few events ({total_events}); "
        "the legacy run should emit at least basic+advance per side")
    # Monotonic t on each side
    for side in ("left_timeline", "right_timeline"):
        ts = [ev["t"] for ev in data[side]]
        assert ts == sorted(ts), f"{side} timestamps not monotonic: {ts}"
