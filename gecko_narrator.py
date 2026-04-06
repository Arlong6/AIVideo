"""
Gecko narrator overlay — channel mascot with lip sync.

Uses audio volume detection to switch between open/closed mouth.
Creates gecko-only video via ffmpeg concat, then overlays on main video.
"""
import os
import subprocess
from PIL import Image

GECKO_DIR = os.path.dirname(os.path.abspath(__file__))
GECKO_OPEN = os.path.join(GECKO_DIR, "Geko_nobg.png")
GECKO_CLOSED = os.path.join(GECKO_DIR, "Geko2_nobg.png")


def _get_speech_segments(audio_path: str, threshold: float = 0.3,
                         min_duration: float = 0.2) -> list[tuple[bool, float]]:
    """
    Analyze audio volume → list of (is_speaking, duration) segments.
    Merges short segments to prevent flickering.
    """
    # Extract volume every 0.1 seconds
    subprocess.run([
        "ffmpeg", "-y", "-i", audio_path, "-af",
        f"astats=metadata=1:reset={int(0.1*44100)},"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=/tmp/_gecko_vol.txt",
        "-f", "null", "-"
    ], capture_output=True, timeout=120)

    volumes = []
    try:
        with open("/tmp/_gecko_vol.txt") as f:
            for line in f:
                if "RMS_level" in line:
                    try:
                        db = float(line.split("=")[-1].strip())
                        volumes.append(max(0, (db + 60) / 60))
                    except:
                        volumes.append(0)
    except:
        pass

    if not volumes:
        return [(False, 10.0)]

    # Convert to speaking/silent states (0.1s per sample)
    raw_states = [v > threshold for v in volumes]

    # Merge into segments with minimum duration
    segments = []
    current_state = raw_states[0]
    current_dur = 0.1

    for i in range(1, len(raw_states)):
        if raw_states[i] == current_state:
            current_dur += 0.1
        else:
            if current_dur >= min_duration:
                segments.append((current_state, round(current_dur, 2)))
                current_state = raw_states[i]
                current_dur = 0.1
            else:
                # Too short, merge with current
                current_dur += 0.1

    if current_dur > 0:
        segments.append((current_state, round(current_dur, 2)))

    return segments


def overlay_gecko_on_video(video_path: str, audio_path: str,
                           output_path: str) -> str:
    """Overlay gecko with lip sync on video."""
    if not os.path.exists(GECKO_OPEN) or not os.path.exists(GECKO_CLOSED):
        print("  [Gecko] Character images not found, skipping")
        return video_path

    # Get video dimensions
    result = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                             "stream=width,height", "-of", "csv=p=0:s=x",
                             video_path], capture_output=True, text=True)
    try:
        w, h = result.stdout.strip().split("\n")[0].split("x")
        width, height = int(w), int(h)
    except:
        width, height = 1920, 1080

    # Resize both gecko images
    gecko_h = int(height * 0.28)
    tmp_open = "/tmp/_gecko_open.png"
    tmp_closed = "/tmp/_gecko_closed.png"

    for src, dst in [(GECKO_OPEN, tmp_open), (GECKO_CLOSED, tmp_closed)]:
        img = Image.open(src).convert("RGBA")
        ratio = gecko_h / img.height
        resized = img.resize((int(img.width * ratio), gecko_h), Image.LANCZOS)
        resized.save(dst)
    gecko_w = int(Image.open(GECKO_OPEN).width * (gecko_h / Image.open(GECKO_OPEN).height))

    # Analyze audio for lip sync
    print("  [Gecko] Analyzing audio for lip sync...")
    segments = _get_speech_segments(audio_path)
    speaking_time = sum(d for s, d in segments if s)
    total_time = sum(d for _, d in segments)
    print(f"  [Gecko] {len(segments)} segments, speaking {speaking_time:.0f}s / {total_time:.0f}s")

    # Create ffmpeg concat list (alternating open/closed mouth images)
    concat_file = "/tmp/_gecko_concat.txt"
    with open(concat_file, "w") as f:
        for is_speaking, duration in segments:
            img = tmp_open if is_speaking else tmp_closed
            f.write(f"file '{img}'\n")
            f.write(f"duration {duration}\n")
        # ffmpeg concat needs last file repeated
        last_img = tmp_open if segments[-1][0] else tmp_closed
        f.write(f"file '{last_img}'\n")

    # Create gecko-only video from concat (force 25fps)
    gecko_vid = "/tmp/_gecko_lipsync.mov"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-vf", f"scale={gecko_w}:{gecko_h},format=rgba,fps=25",
        "-c:v", "png",
        gecko_vid,
    ], capture_output=True, timeout=300)

    if not os.path.exists(gecko_vid):
        print("  [Gecko] Lip sync video failed, using static overlay")
        return _static_overlay(video_path, tmp_closed, width, height,
                               gecko_w, gecko_h, output_path)

    # Overlay gecko video on main video
    x_pos = width - gecko_w - 20
    y_pos = height - gecko_h - 10

    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", gecko_vid,
        "-filter_complex",
        f"[1:v]format=rgba[g];[0:v][g]overlay={x_pos}:{y_pos}:shortest=1[v]",
        "-map", "[v]", "-map", "0:a",
        "-r", "25",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        output_path,
    ], capture_output=True, timeout=1200)

    # Cleanup
    for f in [gecko_vid, concat_file, tmp_open, tmp_closed]:
        try:
            os.remove(f)
        except:
            pass

    if result.returncode == 0 and os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"  [Gecko] 🦎 Narrator with lip sync ✅ ({size_mb:.0f} MB)")
        return output_path
    else:
        err = result.stderr[-200:].decode("utf-8", "ignore") if result.stderr else ""
        print(f"  [Gecko] Overlay failed: {err}")
        return video_path


def _static_overlay(video_path, gecko_png, width, height,
                    gecko_w, gecko_h, output_path):
    """Fallback: static gecko overlay without lip sync."""
    x_pos = width - gecko_w - 20
    y_pos = height - gecko_h - 10
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path, "-i", gecko_png,
        "-filter_complex",
        f"[1:v]format=rgba[g];[0:v][g]overlay={x_pos}:{y_pos}[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "copy",
        output_path,
    ], capture_output=True, timeout=1200)
    if result.returncode == 0 and os.path.exists(output_path):
        print(f"  [Gecko] 🦎 Static overlay ✅")
        return output_path
    return video_path
