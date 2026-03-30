"""
Auto-generate YouTube thumbnails for true crime videos.

Style: dark cinematic — deep black gradient, blood-red accent bar,
large bold Chinese title, subtle vignette. 1280×720 (YouTube standard).
"""

import os
import random
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


def _add_city_lights(img: Image.Image, seed: int) -> Image.Image:
    """Add blurred bokeh dots in upper half for city-at-night atmosphere."""
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    colors = [(180, 60, 60), (200, 80, 30), (220, 160, 60), (80, 80, 180)]
    for _ in range(60):
        x = rng.randint(0, THUMB_W)
        y = rng.randint(0, THUMB_H // 2)
        r = rng.randint(4, 18)
        color = rng.choice(colors)
        alpha = rng.randint(30, 90)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(*color, alpha))
    blurred = overlay.filter(ImageFilter.GaussianBlur(radius=8))
    result = img.convert("RGBA")
    result = Image.alpha_composite(result, blurred)
    return result.convert("RGB")


def _add_fog(img: Image.Image) -> Image.Image:
    """Add a subtle horizontal fog band across the middle."""
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    fog = np.zeros((h, w), dtype=np.float32)
    center_y = h * 0.55
    band_h = h * 0.35
    for y in range(h):
        dist = abs(y - center_y) / band_h
        fog[y] = max(0.0, 1.0 - dist) * 0.12
    arr += fog[:, :, np.newaxis] * 255
    return Image.fromarray(arr.clip(0, 255).astype(np.uint8))


def _add_blood_splatter(img: Image.Image, seed: int) -> Image.Image:
    """Add subtle dark crimson droplets in corners."""
    rng = random.Random(seed)
    draw = ImageDraw.Draw(img)
    for _ in range(12):
        corner_x = rng.choice([rng.randint(0, 120), rng.randint(THUMB_W - 120, THUMB_W)])
        corner_y = rng.choice([rng.randint(0, 80), rng.randint(THUMB_H - 80, THUMB_H)])
        r = rng.randint(2, 8)
        alpha_val = rng.randint(60, 140)
        color = (rng.randint(100, 160), 0, 0)
        draw.ellipse([corner_x - r, corner_y - r, corner_x + r, corner_y + r], fill=color)
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


def _draw_text_with_stroke(draw, pos, text, font, fill, stroke_fill, stroke_width=4):
    """Draw text with a thick stroke outline for maximum readability."""
    x, y = pos
    for ox in range(-stroke_width, stroke_width + 1):
        for oy in range(-stroke_width, stroke_width + 1):
            if ox != 0 or oy != 0:
                draw.text((x + ox, y + oy), text, font=font, fill=stroke_fill)
    draw.text((x, y), text, font=font, fill=fill)


def _draw_title(img: Image.Image, title: str, fmt: str = "short",
                duration_hint: str = "") -> Image.Image:
    """Draw large Chinese title with stroke outline, background panel, and accent bars."""
    draw = ImageDraw.Draw(img)

    # Top red accent bar
    bar_h = 10
    draw.rectangle([(0, 0), (THUMB_W, bar_h)], fill=(200, 10, 10))

    # Split title into lines: prefer punctuation breaks, force-break at MAX_CHARS
    MAX_CHARS = 10
    lines = []
    line = ""
    for ch in list(title):
        line += ch
        if ch in "，。！？、 ｜…" and len(line) >= 4:
            lines.append(line)
            line = ""
        elif len(line) >= MAX_CHARS:
            lines.append(line)
            line = ""
    if line:
        lines.append(line)
    lines = lines[:3]

    FONT_SIZE = 108 if len(lines) == 1 else (94 if len(lines) == 2 else 78)
    try:
        font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
        label_font = ImageFont.truetype(FONT_PATH, 36)
        badge_font = ImageFont.truetype(FONT_PATH, 28)
    except Exception:
        font = ImageFont.load_default()
        label_font = font
        badge_font = font

    line_gap = FONT_SIZE + 18
    total_h = len(lines) * line_gap
    start_y = (THUMB_H - total_h) // 2 - 30

    # Semi-transparent dark panel behind text for contrast
    pad_x, pad_y = 40, 20
    panel_top = start_y - pad_y
    panel_bot = start_y + total_h + pad_y
    panel = Image.new("RGBA", img.size, (0, 0, 0, 0))
    panel_draw = ImageDraw.Draw(panel)
    panel_draw.rectangle([(0, panel_top), (THUMB_W, panel_bot)], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), panel).convert("RGB")
    draw = ImageDraw.Draw(img)

    for i, line_text in enumerate(lines):
        bbox = draw.textbbox((0, 0), line_text, font=font)
        w = bbox[2] - bbox[0]
        x = (THUMB_W - w) // 2
        y = start_y + i * line_gap
        # White text with black stroke
        _draw_text_with_stroke(draw, (x, y), line_text, font,
                               fill=(255, 252, 220), stroke_fill=(0, 0, 0), stroke_width=5)

    # Bottom red accent bar
    draw.rectangle([(0, THUMB_H - bar_h), (THUMB_W, THUMB_H)], fill=(200, 10, 10))

    # "真實犯罪" badge — top-left with red background pill
    badge_text = "真實犯罪"
    bb = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bb[2] - bb[0], bb[3] - bb[1]
    bx, by = 20, 18
    draw.rounded_rectangle([bx - 8, by - 4, bx + bw + 8, by + bh + 4],
                            radius=6, fill=(180, 10, 10))
    draw.text((bx, by), badge_text, font=badge_font, fill=(255, 255, 255))

    # Top-right badge — format-dependent
    if fmt == "long":
        # Duration badge for long-form (e.g. "15:00")
        dur_text = f"▶ {duration_hint}" if duration_hint else "▶ 深度解析"
        sb = draw.textbbox((0, 0), dur_text, font=badge_font)
        sw, sh = sb[2] - sb[0], sb[3] - sb[1]
        sx = THUMB_W - sw - 28
        draw.rounded_rectangle([sx - 8, 14, sx + sw + 8, 18 + sh + 4],
                                radius=6, fill=(0, 0, 0, 180))
        draw.text((sx, 18), dur_text, font=badge_font, fill=(255, 255, 255))
    else:
        shorts_text = "▶ Shorts"
        sb = draw.textbbox((0, 0), shorts_text, font=badge_font)
        sw = sb[2] - sb[0]
        sx = THUMB_W - sw - 28
        draw.text((sx, 18), shorts_text, font=badge_font, fill=(255, 80, 80))

    return img


def generate_thumbnail(title: str, output_path: str, fmt: str = "short",
                       duration_hint: str = "") -> str:
    """
    Generate a dark cinematic YouTube thumbnail.
    fmt='short' shows Shorts badge, fmt='long' shows duration badge.
    Returns path to saved 1280×720 JPEG.
    """
    seed = hash(title) & 0xFFFFFFFF
    img = _make_dark_background()
    img = _add_city_lights(img, seed)
    img = _add_fog(img)
    img = _add_vignette(img)
    img = _draw_title(img, title, fmt=fmt, duration_hint=duration_hint)
    img = _add_blood_splatter(img, seed + 1)

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
