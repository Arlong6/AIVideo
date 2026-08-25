"""hi-res verification helpers — event equality and structural similarity."""
import json
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_identical_events_report_no_differences(tmp_path):
    from tools.hires_verify import compare_events
    data = {"winner": "left", "n_frames": 10, "events": [{"t": 1, "kind": "hit"}],
            "event_video_ms": {"0": 16}}
    a = _write(tmp_path, "a.json", data)
    b = _write(tmp_path, "b.json", data)
    assert compare_events(a, b) == []


def test_changed_winner_is_reported(tmp_path):
    from tools.hires_verify import compare_events
    base = {"winner": "left", "n_frames": 10, "events": [], "event_video_ms": {}}
    cur = dict(base, winner="right")
    diffs = compare_events(_write(tmp_path, "a.json", base),
                           _write(tmp_path, "b.json", cur))
    assert any("winner" in d for d in diffs)


def test_changed_event_count_is_reported(tmp_path):
    from tools.hires_verify import compare_events
    base = {"winner": "left", "n_frames": 10,
            "events": [{"t": 1}], "event_video_ms": {}}
    cur = dict(base, events=[{"t": 1}, {"t": 2}])
    diffs = compare_events(_write(tmp_path, "a.json", base),
                           _write(tmp_path, "b.json", cur))
    assert any("event" in d.lower() for d in diffs)


def test_ssim_of_a_scaled_copy_is_high(tmp_path):
    """A faithful 2x render, downscaled back, must match the original."""
    import numpy as np
    from PIL import Image, ImageDraw
    from tools.hires_verify import frame_ssim

    base = Image.new("RGB", (120, 200), (20, 20, 30))
    d = ImageDraw.Draw(base)
    d.line((10, 10, 100, 180), fill=(240, 240, 240), width=3)
    d.ellipse((40, 60, 80, 100), fill=(200, 40, 40))
    bp = tmp_path / "base.png"; base.save(bp)

    big = base.resize((240, 400), Image.LANCZOS)
    cp = tmp_path / "cur.png"; big.save(cp)

    assert frame_ssim(bp, cp) > 0.90


def test_ssim_flags_missed_scale_below_faithful(tmp_path):
    """A frame where one element missed the *S multiply must score clearly
    below a faithful 2x render — this is the discrimination the whole
    second verification layer depends on."""
    from PIL import Image, ImageDraw
    from tools.hires_verify import frame_ssim

    base = Image.new("RGB", (120, 200), (20, 20, 30))
    d = ImageDraw.Draw(base)
    d.line((10, 10, 100, 180), fill=(240, 240, 240), width=3)
    d.ellipse((40, 60, 80, 100), fill=(200, 40, 40))
    bp = tmp_path / "base.png"; base.save(bp)

    faithful = base.resize((240, 400), Image.LANCZOS)
    fp = tmp_path / "faithful.png"; faithful.save(fp)

    # missed *S: line scaled correctly, ellipse left at unscaled coords
    bad = Image.new("RGB", (240, 400), (20, 20, 30))
    db = ImageDraw.Draw(bad)
    db.line((20, 20, 200, 360), fill=(240, 240, 240), width=6)
    db.ellipse((40, 60, 80, 100), fill=(200, 40, 40))  # forgot * S
    cp = tmp_path / "bad.png"; bad.save(cp)

    s_ok = frame_ssim(bp, fp)
    s_bad = frame_ssim(bp, cp)
    assert s_bad < s_ok - 0.03
    assert s_bad < 0.95
