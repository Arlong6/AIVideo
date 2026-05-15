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
    # 2026-05-15 (C upgrade): prefer Bold/Black weights for thumbnail punch.
    # Stroke width is already 4 so weight matters less than people think,
    # but Bold gives a slight visual upgrade for free. Falls back to
    # Regular/Medium when Bold isn't installed (no breakage).
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",   # Ubuntu (preferred)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",                # macOS (only Medium variant)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Ubuntu fallback
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


def _apply_brand_lut(img: Image.Image) -> Image.Image:
    """Lock thumbnails to a consistent crime-noir colour grade so the
    channel front-page looks like a coherent series instead of 15 random
    Imagen renders.

    Recipe (deterministic, no randomness):
      1. Desaturate 25%  — kills any stray bright colors
      2. Contrast +15%   — punch
      3. Cool shadow tint (dark teal, low opacity) — Hollywood teal/orange
      4. Warm highlight tint (amber, lower opacity) — same look
    Applied AFTER Imagen returns, BEFORE vignette + text overlay so the
    grade affects the AI background but not the title text.
    """
    from PIL import ImageEnhance
    img = ImageEnhance.Color(img).enhance(0.75)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    # Cool shadow overlay (dark teal at ~12% alpha)
    teal = Image.new("RGBA", img.size, (10, 30, 50, 32))
    img = Image.alpha_composite(img, teal)
    # Warm highlight overlay (amber at ~5% alpha)
    amber = Image.new("RGBA", img.size, (50, 25, 0, 14))
    img = Image.alpha_composite(img, amber)
    return img.convert("RGB")


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


def _extract_punch(title: str) -> tuple[str, str]:
    """從 25-字標題抽出 4-8 字 punch text (long-form thumbnail 主視覺).
    @mystery2018 style: 縮圖只有大字 hook, 不放完整標題.

    Returns (punch_text, accent_keyword) — accent_keyword 用紅色強調.
    """
    # Priority hook keywords — 找到就以此為核心建構 punch
    HOOK_KEYS = [
        ("99%", "99%"), ("為什麼", "為什麼"), ("水有多深", "水有多深"),
        ("竟", "竟"), ("活活", "活活"), ("惡魔", "惡魔"),
        ("人間蒸發", "人間蒸發"), ("真兇", "真兇"), ("封殺", "封殺"),
        ("沒人敢說", "沒人敢說"), ("顛覆", "顛覆"), ("驚天", "驚天"),
        ("為了", "為了"), ("就剛剛", "就剛剛"), ("崩潰", "崩潰"),
    ]
    for kw, accent in HOOK_KEYS:
        if kw in title:
            # 找到 keyword 的位置, 抽前後共 4-8 字
            idx = title.find(kw)
            start = max(0, idx - 2)
            end = min(len(title), idx + len(kw) + 4)
            punch = title[start:end].strip("，。、！？：:｜| ")
            # 限制長度
            if len(punch) > 8:
                punch = title[idx:idx + min(len(kw) + 4, len(title) - idx)]
            return punch, accent
    # Fallback: 取冒號前段、再取前 6 字
    import re as _re
    head = _re.split(r"[：:｜|（(]", title, 1)[0].strip("，。、！？ ")
    return head[:6] or title[:6], ""


def _draw_title(img: Image.Image, title: str, fmt: str = "short",
                duration_hint: str = "") -> Image.Image:
    """Draw large Chinese title with stroke outline, background panel, and accent bars."""
    draw = ImageDraw.Draw(img)

    # 2026-05-07: Long-form 用 4-8 字 punch text 而非完整標題
    # (短小才能放大, @mystery2018 367k median 的關鍵)
    accent_kw = ""
    if fmt == "long":
        punch, accent_kw = _extract_punch(title)
        title = punch

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

    # Long-form punch text 用更大字
    if fmt == "long" and len(lines) == 1:
        FONT_SIZE = 180  # ⭐ 大字 punch
    elif fmt == "long" and len(lines) == 2:
        FONT_SIZE = 130
    else:
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
        # 2026-05-07: 紅字強調 accent keyword (long-form punch text)
        if fmt == "long" and accent_kw and accent_kw in line_text:
            # Split line around accent keyword and render in red
            idx = line_text.find(accent_kw)
            before = line_text[:idx]
            after = line_text[idx + len(accent_kw):]
            cur_x = x
            if before:
                _draw_text_with_stroke(draw, (cur_x, y), before, font,
                                       fill=(255, 252, 220), stroke_fill=(0, 0, 0), stroke_width=6)
                cur_x += draw.textbbox((0, 0), before, font=font)[2]
            # Red accent
            _draw_text_with_stroke(draw, (cur_x, y), accent_kw, font,
                                   fill=(255, 50, 50), stroke_fill=(0, 0, 0), stroke_width=6)
            cur_x += draw.textbbox((0, 0), accent_kw, font=font)[2]
            if after:
                _draw_text_with_stroke(draw, (cur_x, y), after, font,
                                       fill=(255, 252, 220), stroke_fill=(0, 0, 0), stroke_width=6)
        else:
            # White text with black stroke
            _draw_text_with_stroke(draw, (x, y), line_text, font,
                                   fill=(255, 252, 220), stroke_fill=(0, 0, 0), stroke_width=5)

    # (red bars removed for clean look)

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


AI_STYLE_ANCHOR = (
    # 2026-05-07 v2 — 強化 hero subject 戲劇感（@mystery2018 風格）
    "cinematic true crime documentary thumbnail, "
    "ONE strong focal subject dominating left or center "
    "(silhouette of person from behind, hooded figure in shadow, "
    "key object like weapon/badge/evidence bag, single empty chair, "
    "broken window, empty interrogation room), "
    "DRAMATIC chiaroscuro: 70% deep shadow + 30% hard rim light from upper side, "
    "dark teal and amber color grade, ultra high contrast, "
    "shallow depth of field with strong bokeh, 35mm film grain, "
    "right-side area kept relatively dark/clean for text overlay, "
    "no text, no watermark, no recognizable real people's faces"
)


def _generate_ai_background(title: str, visual_hint: str = "",
                             fmt: str = "long") -> Image.Image | None:
    """Generate a 1280×720 AI background via Pollinations (free) → Imagen (backup).

    Only called for long-form. Shorts stay on PIL.
    Returns PIL Image or None on failure.
    """
    if fmt != "long":
        return None

    import requests
    from urllib.parse import quote

    # Build prompt: style anchor + case-specific hint
    hint = visual_hint.strip() if visual_hint else title[:30]
    prompt = f"{hint}, {AI_STYLE_ANCHOR}"

    # --- Imagen Ultra (primary, 2026-05-07) ---
    # Phase 1 strategy: thumbnail 是最大短板,值得 1 Ultra 配額/部 ($0.06).
    # Pollinations Flux 質感不夠 cinematic, 影響 CTR.
    try:
        from config import GEMINI_API_KEY
        if GEMINI_API_KEY:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            print(f"  [thumb] Imagen Ultra (primary): generating...")
            result = client.models.generate_images(
                model="imagen-4.0-ultra-generate-001",
                prompt=prompt,
                config={"number_of_images": 1, "aspect_ratio": "16:9"},
            )
            if result.generated_images:
                img_bytes = result.generated_images[0].image.image_bytes
                from io import BytesIO
                img = Image.open(BytesIO(img_bytes)).convert("RGB")
                img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
                print(f"  [thumb] ✓ Imagen Ultra (cinematic)")
                return img
    except Exception as e:
        print(f"  [thumb] Imagen Ultra failed: {e}, falling back to Pollinations")

    # --- Pollinations.ai (free fallback) ---
    try:
        encoded = quote(prompt)
        url = (f"https://image.pollinations.ai/prompt/{encoded}"
               f"?width={THUMB_W}&height={THUMB_H}&model=flux&nologo=true")
        print(f"  [thumb] Pollinations fallback...")
        resp = requests.get(url, timeout=90)
        if resp.status_code == 200 and len(resp.content) > 10000:
            from io import BytesIO
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            img = img.resize((THUMB_W, THUMB_H), Image.LANCZOS)
            print(f"  [thumb] ✓ Pollinations AI background ({len(resp.content)//1024} KB)")
            return img
        print(f"  [thumb] Pollinations returned {resp.status_code}")
    except Exception as e:
        print(f"  [thumb] Pollinations failed: {e}")

    print(f"  [thumb] All AI providers failed, falling back to PIL")
    return None


def _fetch_real_photo(search_term: str) -> Image.Image | None:
    """Try Wikimedia first, then Pexels, for a real photo. Returns PIL Image
    cropped/resized to THUMB_W x THUMB_H, or None if both fail.

    Real photos let us escape the 'AI slop' visual category that YouTube's
    2026 viewer rejection signal targets.
    """
    if not search_term or len(search_term.strip()) < 2:
        return None

    # ── Wikimedia path ──────────────────────────────────────────────
    try:
        from wiki_footage import _search_wikimedia, _download_image, _extract_meta
        pages = _search_wikimedia(search_term, limit=8)
        for p in pages:
            meta = _extract_meta(p)
            if not meta:
                continue
            arr = _download_image(meta.get("url", ""))
            if arr is None:
                continue
            img = Image.fromarray(arr)
            return _fit_thumbnail(img)
    except Exception as e:
        print(f"  [thumb] Wikimedia fetch failed: {e}")

    # ── Pexels fallback ────────────────────────────────────────────
    try:
        from config import PEXELS_API_KEY
        import requests as _r
        if PEXELS_API_KEY:
            r = _r.get(
                "https://api.pexels.com/v1/search",
                headers={"Authorization": PEXELS_API_KEY},
                params={"query": search_term, "per_page": 5, "orientation": "landscape"},
                timeout=10,
            )
            if r.ok:
                photos = r.json().get("photos", [])
                for ph in photos:
                    src = ph.get("src", {}).get("large", "")
                    if not src:
                        continue
                    pr = _r.get(src, timeout=10)
                    if pr.ok:
                        from io import BytesIO
                        img = Image.open(BytesIO(pr.content)).convert("RGB")
                        return _fit_thumbnail(img)
    except Exception as e:
        print(f"  [thumb] Pexels fallback failed: {e}")

    return None


def _fit_thumbnail(img: Image.Image) -> Image.Image:
    """Center-crop and resize to exactly THUMB_W × THUMB_H."""
    img = img.convert("RGB")
    w, h = img.size
    target_ratio = THUMB_W / THUMB_H
    src_ratio = w / h
    if src_ratio > target_ratio:
        # source wider — crop sides
        new_w = int(h * target_ratio)
        x = (w - new_w) // 2
        img = img.crop((x, 0, x + new_w, h))
    else:
        # source taller — crop top/bottom
        new_h = int(w / target_ratio)
        y = (h - new_h) // 2
        img = img.crop((0, y, w, y + new_h))
    return img.resize((THUMB_W, THUMB_H), Image.LANCZOS)


def _darken_for_text(img: Image.Image, strength: float = 0.55) -> Image.Image:
    """Apply gradient darkening over bottom half so text is legible."""
    overlay = Image.new("RGBA", (THUMB_W, THUMB_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for y in range(THUMB_H):
        t = y / THUMB_H
        # Stronger darkening on bottom 60%
        if t < 0.4:
            alpha = int(60 * t / 0.4)
        else:
            alpha = int(60 + (255 * strength - 60) * (t - 0.4) / 0.6)
        draw.line([(0, y), (THUMB_W, y)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_red_circle(img: Image.Image, cx: int, cy: int, radius: int = 90) -> Image.Image:
    """Draw a thick red circle annotation at (cx, cy) — the 'mystery point' marker."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Outer glow (subtle)
    for r in range(radius + 18, radius + 4, -2):
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            outline=(220, 30, 30, 50),
            width=2,
        )
    # Main circle — bright red, thick stroke
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        outline=(230, 40, 40, 240),
        width=12,
    )
    # Inner secondary stroke for emphasis
    draw.ellipse(
        [(cx - radius + 14, cy - radius + 14), (cx + radius - 14, cy + radius - 14)],
        outline=(255, 80, 80, 180),
        width=4,
    )
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_punch_text(img: Image.Image, text: str) -> Image.Image:
    """Draw 4-8 char punchline at bottom-center, very large, with red shadow."""
    if not text:
        return img
    text = text[:8]
    draw = ImageDraw.Draw(img)
    # Pick font size so text fits ~80% of width
    font_size = 220 if len(text) <= 4 else (180 if len(text) <= 6 else 150)
    font = ImageFont.truetype(FONT_PATH, font_size) if FONT_PATH else ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (THUMB_W - tw) // 2
    y = THUMB_H - th - 60
    # Red shadow
    for dx, dy in ((6, 6), (4, 4), (2, 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(180, 20, 20))
    # Black outline
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    # Main white text
    draw.text((x, y), text, font=font, fill=(255, 245, 230))
    return img


def _make_real_photo_thumbnail(search_term: str, punch_text: str) -> Image.Image | None:
    """Build a thumbnail from a real photo + red circle + Chinese punch text.
    Returns None if no usable photo could be fetched."""
    base = _fetch_real_photo(search_term)
    if base is None:
        return None
    img = _darken_for_text(base)
    # Red circle marker — top-right rule-of-thirds focal area
    img = _draw_red_circle(img, cx=int(THUMB_W * 0.72), cy=int(THUMB_H * 0.32), radius=110)
    img = _draw_punch_text(img, punch_text)
    return img


def generate_thumbnail(title: str, output_path: str, fmt: str = "short",
                       duration_hint: str = "",
                       visual_hint: str = "",
                       case_data: dict | None = None) -> str:
    """
    Generate a dark cinematic YouTube thumbnail.

    fmt='short': pure PIL (unchanged — Shorts use Remotion's own style).
    fmt='long': AI-generated background (Pollinations/Imagen) + PIL text overlay.
                Falls back to PIL if AI fails.

    visual_hint: case-specific scene description from script_generator
                 (e.g. "模糊老婦人背影 + 紅色電話聽筒特寫").

    Returns path to saved 1280×720 JPEG.
    """
    seed = hash(title) & 0xFFFFFFFF

    # ── Shorts: try real-photo thumbnail (escape AI-slop visual category) ──
    if fmt == "short" and case_data:
        search_term = (
            case_data.get("wiki_search_term", "").strip()
            or case_data.get("title", "").strip()
        )
        # opening_card is ≤8 字 punch text — perfect for thumbnail
        punch = case_data.get("opening_card", "").strip() or title[:6]
        real_thumb = _make_real_photo_thumbnail(search_term, punch)
        if real_thumb is not None:
            real_thumb.save(output_path, "JPEG", quality=95)
            print(f"  [thumb] ✓ Real-photo thumbnail (search={search_term!r})")
            return output_path
        # else fall through to existing logic

    # Long-form: try AI background
    ai_bg = _generate_ai_background(title, visual_hint, fmt) if fmt == "long" else None

    if ai_bg:
        # AI background: brand LUT for series consistency + vignette + title.
        # LUT applied before vignette so vignette compounds on top of the
        # graded image; text comes last so titles stay readable.
        img = _apply_brand_lut(ai_bg)
        img = _add_vignette(img)
        img = _draw_title(img, title, fmt=fmt, duration_hint=duration_hint)
    else:
        # PIL fallback (also the only path for Shorts when real-photo failed)
        img = _make_dark_background()
        img = _add_city_lights(img, seed)
        img = _add_fog(img)
        img = _add_vignette(img)
        img = _draw_title(img, title, fmt=fmt, duration_hint=duration_hint)
        img = _add_blood_splatter(img, seed + 1)

    img.save(output_path, "JPEG", quality=95)
    print(f"  Thumbnail saved: {os.path.basename(output_path)}")

    # Long-form: also save PIL version for A/B comparison
    if fmt == "long" and ai_bg:
        pil_path = output_path.replace(".jpg", "_pil.jpg")
        pil_img = _make_dark_background()
        pil_img = _add_city_lights(pil_img, seed)
        pil_img = _add_fog(pil_img)
        pil_img = _add_vignette(pil_img)
        pil_img = _draw_title(pil_img, title, fmt=fmt, duration_hint=duration_hint)
        pil_img = _add_blood_splatter(pil_img, seed + 1)
        pil_img.save(pil_path, "JPEG", quality=95)
        print(f"  Thumbnail saved (PIL backup): {os.path.basename(pil_path)}")

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
