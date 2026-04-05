"""
Gecko narrator overlay — adds channel mascot to bottom-right of video.

Simple approach: overlay static gecko PNG using ffmpeg.
Alternates between open/closed mouth every ~0.5s during speech.
"""
import os
import subprocess
from PIL import Image

GECKO_DIR = os.path.dirname(os.path.abspath(__file__))
GECKO_OPEN = os.path.join(GECKO_DIR, "Geko_nobg.png")
GECKO_CLOSED = os.path.join(GECKO_DIR, "Geko2_nobg.png")


def overlay_gecko_on_video(video_path: str, audio_path: str,
                           output_path: str) -> str:
    """
    Overlay gecko narrator on video using ffmpeg.
    Simple: static closed-mouth gecko in bottom-right corner.
    """
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

    # Resize gecko to 30% of video height
    gecko_h = int(height * 0.28)
    img = Image.open(GECKO_CLOSED).convert("RGBA")
    ratio = gecko_h / img.height
    gecko_w = int(img.width * ratio)
    resized = img.resize((gecko_w, gecko_h), Image.LANCZOS)

    tmp_gecko = "/tmp/_gecko_overlay.png"
    resized.save(tmp_gecko)

    # Position: bottom-right with padding
    x_pos = width - gecko_w - 20
    y_pos = height - gecko_h - 10

    # ffmpeg overlay — simple and reliable
    result = subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", tmp_gecko,
        "-filter_complex",
        f"[1:v]format=rgba[gecko];[0:v][gecko]overlay={x_pos}:{y_pos}[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "copy",
        output_path,
    ], capture_output=True, timeout=1200)

    os.remove(tmp_gecko)

    if result.returncode == 0 and os.path.exists(output_path):
        print(f"  [Gecko] 🦎 Narrator overlaid ✅")
        return output_path
    else:
        err = result.stderr[-300:].decode("utf-8", "ignore") if result.stderr else ""
        print(f"  [Gecko] Overlay failed: {err}")
        return video_path
