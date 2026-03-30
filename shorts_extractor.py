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
    4. Burning subtitles
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

    # Escape srt path for ffmpeg
    srt_escaped = srt_path.replace("\\", "\\\\").replace(":", "\\:")

    # Find CJK font for subtitles
    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    font_name = "STHeiti"
    for fc in font_candidates:
        if os.path.exists(fc):
            if "Noto" in fc:
                font_name = "Noto Sans CJK TC"
            break

    style = (
        f"FontName={font_name},FontSize=20,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=80"
    )

    # ffmpeg: extract segment → crop 9:16 → overlay audio → burn subtitles
    vf = (
        f"crop=ih*9/16:ih,"
        f"scale=1080:1920,"
        f"noise=alls=10:allf=t+u,"
        f"vignette=PI/5,"
        f"eq=brightness=-0.03:saturation=0.85:contrast=1.05,"
        f"subtitles='{srt_escaped}':force_style='{style}'"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-ss", str(start), "-t", str(duration), "-i", long_video,
        "-i", voiceover,
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        output,
    ], capture_output=True, timeout=120)
