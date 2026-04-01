"""
Extract 2-3 vertical Shorts (9:16, 45-60s) from a long-form 16:9 video.

Uses the shorts_candidates from script generation to identify the best
dramatic moments, then crops and re-formats for Shorts.
"""
import os
import subprocess
import json

from subtitle_generator import generate_srt
from tts_generator import generate_voiceover


def extract_shorts(long_video_path: str, script_data: dict,
                   output_dir: str) -> list[dict]:
    """
    Generate standalone Shorts from a long-form video's script.

    Instead of cutting from the long video (which is 16:9), we generate
    fresh 9:16 Shorts from the shorts_candidates scripts — each gets its
    own TTS, subtitles, and footage re-cut.

    Returns list of {"path": ..., "title": ..., "script": ...}
    """
    candidates = script_data.get("shorts_candidates", [])
    if not candidates:
        print("  No shorts candidates found in script data")
        return []

    shorts_dir = os.path.join(output_dir, "shorts")
    os.makedirs(shorts_dir, exist_ok=True)

    results = []
    for i, cand in enumerate(candidates[:3]):
        title = cand.get("title", f"Short {i+1}")
        script = cand.get("script", "")
        if not script or len(script) < 50:
            continue

        print(f"\n  Generating Short {i+1}: {title}")
        short_dir = os.path.join(shorts_dir, f"short_{i+1}")
        os.makedirs(short_dir, exist_ok=True)

        # 1. TTS for this short script
        vo_path = os.path.join(short_dir, "voiceover.mp3")
        generate_voiceover(script, "zh", vo_path)

        # 2. Get duration
        try:
            result = subprocess.run([
                "ffprobe", "-v", "quiet", "-show_entries",
                "format=duration", "-of", "csv=p=0", vo_path
            ], capture_output=True, text=True)
            duration = float(result.stdout.strip())
        except Exception:
            duration = len(script) * 0.25

        # 3. Generate subtitles
        srt_path = os.path.join(short_dir, "subtitles.srt")
        generate_srt(script, duration, srt_path)

        # 4. Extract random clips from the long video and crop to 9:16
        short_video_path = os.path.join(short_dir, "final.mp4")
        _assemble_short_from_long(long_video_path, vo_path, srt_path,
                                   short_video_path, duration)

        if os.path.exists(short_video_path):
            results.append({
                "path": short_video_path,
                "title": title,
                "script": script,
                "description": script[:80],
                "hashtags": ["#真實犯罪", "#Shorts", "#犯罪故事", "#深度解析"],
            })
            size_mb = os.path.getsize(short_video_path) / 1024 / 1024
            print(f"    ✅ Short {i+1}: {duration:.0f}s, {size_mb:.1f} MB")

    print(f"\n  Generated {len(results)} Shorts from long-form video")
    return results


def _assemble_short_from_long(long_video: str, voiceover: str, srt_path: str,
                               output: str, duration: float):
    """
    Create a 9:16 Short by:
    1. Taking segments from the long video
    2. Cropping center to 9:16
    3. Overlaying voiceover
    4. Burning subtitles via drawtext (no libass dependency)

    Two-pass approach to avoid the subtitles filter (requires libass which
    is often missing on macOS). Pass 1 crops and composites audio, Pass 2
    burns text via drawtext.
    """
    # Get long video duration
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-show_entries",
            "format=duration", "-of", "csv=p=0", long_video
        ], capture_output=True, text=True)
        long_dur = float(result.stdout.strip())
    except Exception:
        long_dur = 600.0

    # Pick a random starting point from the middle section (most dramatic)
    import random
    start = random.uniform(long_dur * 0.3, max(long_dur * 0.7, long_dur * 0.3 + duration))

    # ── Pass 1: crop 16:9 → 9:16, overlay voiceover ─────────────────────
    # The crop filter needs explicit width:height.
    # For center-crop from 16:9 to 9:16: width = ih*9/16, height = ih
    # Use the "in_h" variable to be explicit (avoids ambiguity).
    vf_crop = (
        "crop=in_h*9/16:in_h:(in_w-in_h*9/16)/2:0,"
        "scale=1080:1920:flags=lanczos,"
        "noise=alls=10:allf=t+u,"
        "vignette=PI/5,"
        "eq=brightness=-0.03:saturation=0.85:contrast=1.05"
    )

    # Intermediate file (no subtitles yet)
    intermediate = output.replace(".mp4", "_nosub.mp4")

    proc1 = subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration), "-i", long_video,
        "-i", voiceover,
        "-vf", vf_crop,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        intermediate,
    ], capture_output=True, text=True, timeout=180)

    if proc1.returncode != 0:
        print(f"    [ERROR] ffmpeg crop pass failed (rc={proc1.returncode})")
        print(f"    stderr: {proc1.stderr[-500:]}" if proc1.stderr else "")
        return

    if not os.path.exists(intermediate):
        print("    [ERROR] Intermediate file was not created")
        return

    # ── Pass 2: burn subtitles via drawtext (SRT parsing) ────────────────
    # Parse the SRT file and build drawtext filters for each subtitle cue.
    # This avoids the libass/subtitles filter dependency entirely.
    subtitle_filters = _srt_to_drawtext(srt_path)

    if subtitle_filters:
        vf_subs = ",".join(subtitle_filters)

        proc2 = subprocess.run([
            "ffmpeg", "-y",
            "-i", intermediate,
            "-vf", vf_subs,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "copy",
            output,
        ], capture_output=True, text=True, timeout=180)

        if proc2.returncode != 0:
            print(f"    [WARN] Subtitle burn failed, using video without subs")
            print(f"    stderr: {proc2.stderr[-300:]}" if proc2.stderr else "")
            os.rename(intermediate, output)
        else:
            # Clean up intermediate
            try:
                os.remove(intermediate)
            except OSError:
                pass
    else:
        # No subtitle cues parsed — just rename
        os.rename(intermediate, output)


def _srt_to_drawtext(srt_path: str, max_cues: int = 100) -> list[str]:
    """
    Parse an SRT file and return a list of ffmpeg drawtext filter strings.

    Each cue becomes a drawtext filter with enable='between(t,start,end)'.
    Uses a CJK-capable font available on macOS or Linux.
    """
    if not os.path.exists(srt_path):
        return []

    # Find a CJK font
    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    font_file = ""
    for fc in font_candidates:
        if os.path.exists(fc):
            font_file = fc
            break

    if not font_file:
        print("    [WARN] No CJK font found for subtitles")
        return []

    # Parse SRT
    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return []

    # SRT format: index\ntimestamp --> timestamp\ntext\n\n
    import re as _re
    pattern = _re.compile(
        r"(\d+)\s*\n"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n"
        r"((?:(?!\n\n|\d+\s*\n\d{2}:\d{2}).+\n?)+)",
        _re.MULTILINE
    )

    filters = []
    for i, match in enumerate(pattern.finditer(content)):
        if i >= max_cues:
            break

        h1, m1, s1, ms1 = int(match.group(2)), int(match.group(3)), int(match.group(4)), int(match.group(5))
        h2, m2, s2, ms2 = int(match.group(6)), int(match.group(7)), int(match.group(8)), int(match.group(9))
        text = match.group(10).strip().replace("\n", " ")

        start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
        end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0

        # Escape text for ffmpeg drawtext: ' → \\', : → \\:, \ → \\\\
        escaped = (text
                   .replace("\\", "\\\\\\\\")
                   .replace("'", "\u2019")  # replace with unicode right quote
                   .replace(":", "\\:")
                   .replace("%", "%%"))

        dt = (
            f"drawtext=fontfile='{font_file}'"
            f":text='{escaped}'"
            f":fontsize=42"
            f":fontcolor=white"
            f":borderw=3"
            f":bordercolor=black"
            f":x=(w-text_w)/2"
            f":y=h-h/6"
            f":enable='between(t,{start_sec:.3f},{end_sec:.3f})'"
        )
        filters.append(dt)

    return filters
