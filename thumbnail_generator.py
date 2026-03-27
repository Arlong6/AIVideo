"""
Auto-generate YouTube thumbnails for true crime videos.

Style: dark cinematic — deep black gradient, blood-red accent bar,
large bold Chinese title, subtle vignette. 1280×720 (YouTube standard).
"""

import os
import textwrap
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

THUMB_W, THUMB_H = 1280, 720

# Cross-platform Chinese font detection
def _find_font() -> str:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",           # macOS
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return ""  # fallback to PIL default

FONT_PATH = _find_font()


def _make_dark_background() -> Image.Image:
    """Deep black gradient with subtle dark-red glow at bottom."""
    img = Image.new("RGB", (THUMB_W, THUMB_H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Vertical gradient: near-black top → very dark navy bottom
    for y in range(THUMB_H):
        t = y / THUMB_H
        r = int(8 + 12 * t)
        g = int(4 + 6 * t)
        b = int(12 + 20 * t)
        draw.line([(0, y), (THUMB_W, y)], fill=(r, g, b))

    # Subtle red glow in bottom-left (crime atmosphere)
    for radius in range(300, 0, -20):
        alpha = int(18 * (1 - radius / 300))
        draw.ellipse(
            [(-radius // 2, THUMB_H - radius // 2),
             (radius, THUMB_H + radius // 2)],
            fill=(80 + alpha, 0, 0),
        )

    return img


def _add_vignette(img: Image.Image) -> Image.Image:
    """Darken edges to focus attention on center text."""
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X - w / 2) / (w / 2)) ** 2 + ((Y - h / 2) / (h / 2)) ** 2)
    vignette = np.clip(1.0 - dist * 0.55, 0.25, 1.0)
    arr *= vignette[:, :, np.newaxis]
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def _draw_title(img: Image.Image, title: str) -> Image.Image:
    """Draw large Chinese title with drop shadow and red accent bar."""
    draw = ImageDraw.Draw(img)

    # Red accent bar at top
    bar_h = 8
    draw.rectangle([(0, 0), (THUMB_W, bar_h)], fill=(180, 20, 20))

    # Split title into lines (~14 chars per line for readability)
    MAX_CHARS = 14
    words = list(title)
    lines = []
    line = ""
    for ch in words:
        if len(line) >= MAX_CHARS and ch in "，。！？：、 ｜":
            lines.append(line)
            line = ""
        line += ch
    if line:
        lines.append(line)
    # Max 3 lines
    lines = lines[:3]

    FONT_SIZE = 100 if len(lines) == 1 else (86 if len(lines) == 2 else 72)
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    line_gap = FONT_SIZE + 16
    total_h = len(lines) * line_gap
    start_y = (THUMB_H - total_h) // 2 - 20

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (THUMB_W - w) // 2
        y = start_y + i * line_gap

        # Shadow layer
        for ox, oy in [(-3, 3), (3, 3), (0, 4), (-4, 4), (4, 4)]:
            draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0, 200))

        # Main text (bright white)
        draw.text((x, y), line, font=font, fill=(255, 248, 235))

    # Bottom red accent bar
    draw.rectangle([(0, THUMB_H - bar_h), (THUMB_W, THUMB_H)], fill=(180, 20, 20))

    # "真實犯罪" label top-right
    try:
        label_font = ImageFont.truetype(FONT_PATH, 32)
    except Exception:
        label_font = ImageFont.load_default()
    label = "真實犯罪"
    lbbox = draw.textbbox((0, 0), label, font=label_font)
    lw = lbbox[2] - lbbox[0]
    draw.text((THUMB_W - lw - 24, 20), label, font=label_font, fill=(200, 60, 60))

    return img


def generate_thumbnail(title: str, output_path: str) -> str:
    """
    Generate a dark cinematic YouTube thumbnail.
    Returns path to saved 1280×720 JPEG.
    """
    img = _make_dark_background()
    img = _add_vignette(img)
    img = _draw_title(img, title)

    # Final slight blur on background (keeps text sharp, bg cinematic)
    img.save(output_path, "JPEG", quality=95)
    print(f"  Thumbnail saved: {os.path.basename(output_path)}")
    return output_path


def upload_thumbnail(youtube, video_id: str, thumb_path: str):
    """Upload thumbnail to YouTube video."""
    try:
        from googleapiclient.http import MediaFileUpload
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
        ).execute()
        print(f"  ✅ Thumbnail uploaded")
    except Exception as e:
        print(f"  [WARN] Thumbnail upload failed: {e}")
