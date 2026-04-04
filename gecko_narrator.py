"""
Gecko narrator overlay — adds the channel mascot to video.

Uses two pre-generated images (mouth open + closed) with audio
volume detection for lip sync. Overlays in bottom-right corner.
"""
import os
import subprocess
import numpy as np
from PIL import Image
from moviepy.editor import VideoClip, AudioFileClip, CompositeVideoClip, ImageClip

GECKO_DIR = os.path.dirname(os.path.abspath(__file__))
GECKO_OPEN = os.path.join(GECKO_DIR, "Geko_nobg.png")
GECKO_CLOSED = os.path.join(GECKO_DIR, "Geko2_nobg.png")


def _get_volumes(audio_path: str) -> list[float]:
    """Extract per-frame volume from audio using ffmpeg."""
    subprocess.run([
        "ffmpeg", "-y", "-i", audio_path, "-af",
        f"astats=metadata=1:reset={int(1/25*44100)},"
        "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=/tmp/_gecko_vol.txt",
        "-f", "null", "-"
    ], capture_output=True, timeout=60)

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
    return volumes


def create_narrator_video(audio_path: str, output_path: str,
                          width: int = 1920, height: int = 1080,
                          gecko_height_pct: float = 0.30):
    """
    Create a transparent gecko narrator video synced to audio.
    Returns path to the narrator video clip.
    """
    if not os.path.exists(GECKO_OPEN) or not os.path.exists(GECKO_CLOSED):
        print("  [Gecko] Character images not found, skipping narrator")
        return None

    # Load and resize
    gecko_h = int(height * gecko_height_pct)
    def resize(img_path):
        img = Image.open(img_path).convert("RGBA")
        ratio = gecko_h / img.height
        return img.resize((int(img.width * ratio), gecko_h), Image.LANCZOS)

    g_open = resize(GECKO_OPEN)
    g_closed = resize(GECKO_CLOSED)

    # Position: bottom-right
    gx = width - g_open.width - 20
    gy = height - g_open.height - 10

    # Create RGBA frames
    def make_overlay(gecko):
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        frame.paste(gecko, (gx, gy), gecko)
        return np.array(frame)

    overlay_open = make_overlay(g_open)
    overlay_closed = make_overlay(g_closed)

    # Get audio volumes
    volumes = _get_volumes(audio_path)

    # Get duration
    result = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                             "format=duration", "-of", "csv=p=0", audio_path],
                            capture_output=True, text=True)
    duration = float(result.stdout.strip())

    def make_frame(t):
        idx = int(t * 25)
        vol = volumes[idx] if idx < len(volumes) else 0
        return overlay_open if vol > 0.3 else overlay_closed

    video = VideoClip(make_frame, duration=duration).set_fps(25)
    video.write_videofile(output_path, fps=25, codec="png", audio=False,
                          logger=None)
    video.close()
    print(f"  [Gecko] Narrator overlay created: {duration:.0f}s")
    return output_path


def overlay_gecko_on_video(video_path: str, audio_path: str,
                           output_path: str) -> str:
    """
    Overlay gecko narrator on an existing video using ffmpeg.
    Much faster than MoviePy compositing.
    """
    if not os.path.exists(GECKO_OPEN) or not os.path.exists(GECKO_CLOSED):
        print("  [Gecko] Character images not found, skipping")
        return video_path

    # Get video info
    result = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                             "stream=width,height", "-of", "csv=p=0:s=x",
                             video_path], capture_output=True, text=True)
    try:
        w, h = result.stdout.strip().split("\n")[0].split("x")
        width, height = int(w), int(h)
    except:
        width, height = 1920, 1080

    # Resize gecko images
    gecko_h = int(height * 0.30)
    def resize(img_path, out_path):
        img = Image.open(img_path).convert("RGBA")
        ratio = gecko_h / img.height
        resized = img.resize((int(img.width * ratio), gecko_h), Image.LANCZOS)
        resized.save(out_path)
        return resized.width, resized.height

    gw, gh = resize(GECKO_OPEN, "/tmp/_gecko_open.png")
    resize(GECKO_CLOSED, "/tmp/_gecko_closed.png")

    # Get volumes for switching
    volumes = _get_volumes(audio_path)

    # Generate a text file with frame-by-frame gecko selection
    # Use ffmpeg's overlay with enable expressions based on volume
    # Simpler approach: pre-render gecko frames as video, then overlay

    # Create gecko-only video (transparent background)
    gx = width - gw - 20
    gy = height - gh - 10

    def make_overlay(gecko_path):
        gecko = Image.open(gecko_path).convert("RGBA")
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        frame.paste(gecko, (gx, gy), gecko)
        return np.array(frame)

    overlay_open = make_overlay("/tmp/_gecko_open.png")
    overlay_closed = make_overlay("/tmp/_gecko_closed.png")

    result2 = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries",
                              "format=duration", "-of", "csv=p=0", video_path],
                             capture_output=True, text=True)
    duration = float(result2.stdout.strip())

    def make_frame(t):
        idx = int(t * 25)
        vol = volumes[idx] if idx < len(volumes) else 0
        return overlay_open if vol > 0.3 else overlay_closed

    # Write gecko overlay as separate video
    gecko_vid = output_path.replace(".mp4", "_gecko.mov")
    from moviepy.editor import VideoClip as VC
    gv = VC(make_frame, duration=duration).set_fps(25)
    gv.write_videofile(gecko_vid, fps=25, codec="png", audio=False, logger=None)
    gv.close()

    # Overlay using ffmpeg (fast)
    subprocess.run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", gecko_vid,
        "-filter_complex", "[0:v][1:v]overlay=0:0[v]",
        "-map", "[v]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "copy",
        output_path,
    ], capture_output=True, timeout=600)

    # Cleanup
    try:
        os.remove(gecko_vid)
    except:
        pass

    if os.path.exists(output_path):
        print(f"  [Gecko] Narrator overlaid on video ✅")
        return output_path
    else:
        print(f"  [Gecko] Overlay failed, returning original")
        return video_path
