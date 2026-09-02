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


def test_event_video_ms_id_keys_equal_values_no_diff(tmp_path):
    """id()-style keys differ across runs; equal ordered values must pass."""
    from tools.hires_verify import compare_events
    base = {"winner": "left", "n_frames": 10, "events": [],
            "event_video_ms": {"4478509120": 100, "4478509456": 250,
                               "4478510128": 900}}
    cur = {"winner": "left", "n_frames": 10, "events": [],
           "event_video_ms": {"4581230080": 100, "4581230416": 250,
                              "4581231088": 900}}
    diffs = compare_events(_write(tmp_path, "a.json", base),
                           _write(tmp_path, "b.json", cur))
    assert diffs == []


def test_event_video_ms_changed_value_is_reported(tmp_path):
    """Same id()-style key churn, but one timestamp changed — must diff."""
    from tools.hires_verify import compare_events
    base = {"winner": "left", "n_frames": 10, "events": [],
            "event_video_ms": {"4478509120": 100, "4478509456": 250}}
    cur = {"winner": "left", "n_frames": 10, "events": [],
           "event_video_ms": {"4581230080": 100, "4581230416": 317}}
    diffs = compare_events(_write(tmp_path, "a.json", base),
                           _write(tmp_path, "b.json", cur))
    assert any("event_video_ms" in d for d in diffs)


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


def test_ssim_drops_when_an_element_moves(tmp_path):
    from PIL import Image, ImageDraw
    from tools.hires_verify import frame_ssim

    base = Image.new("RGB", (120, 200), (20, 20, 30))
    ImageDraw.Draw(base).ellipse((40, 60, 80, 100), fill=(200, 40, 40))
    bp = tmp_path / "base.png"; base.save(bp)

    moved = Image.new("RGB", (240, 400), (20, 20, 30))
    # same circle but shifted — this is what a missed *S looks like
    ImageDraw.Draw(moved).ellipse((80, 260, 160, 340), fill=(200, 40, 40))
    cp = tmp_path / "cur.png"; moved.save(cp)

    assert frame_ssim(bp, cp) < 0.90


def test_ssim_drop_for_moved_element_is_below_operative_floor(tmp_path):
    """Pin report()'s operative ssim_floor (0.50): the moved-element case
    (measured 0.1981) must trip it by a wide margin, since floor=0.50 is a
    coarse gross-misplacement tripwire, not a discriminator against the
    overlapping Task-8 defective-frame population (see hires_verify.py
    report() comment)."""
    from PIL import Image, ImageDraw
    from tools.hires_verify import frame_ssim

    base = Image.new("RGB", (120, 200), (20, 20, 30))
    ImageDraw.Draw(base).ellipse((40, 60, 80, 100), fill=(200, 40, 40))
    bp = tmp_path / "base.png"; base.save(bp)

    moved = Image.new("RGB", (240, 400), (20, 20, 30))
    # same circle but shifted — this is what a missed *S looks like
    ImageDraw.Draw(moved).ellipse((80, 260, 160, 340), fill=(200, 40, 40))
    cp = tmp_path / "cur.png"; moved.save(cp)

    assert frame_ssim(bp, cp) < 0.50


def test_ssim_identical_file_is_perfect(tmp_path):
    """An identical file compared to itself must have perfect SSIM."""
    from PIL import Image, ImageDraw
    from tools.hires_verify import frame_ssim

    base = Image.new("RGB", (120, 200), (20, 20, 30))
    d = ImageDraw.Draw(base)
    d.line((10, 10, 100, 180), fill=(240, 240, 240), width=3)
    d.ellipse((40, 60, 80, 100), fill=(200, 40, 40))
    bp = tmp_path / "base.png"; base.save(bp)

    assert frame_ssim(bp, bp) >= 0.999
