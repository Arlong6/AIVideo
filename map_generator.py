"""
Generate crime location maps for documentary videos.

Two outputs:
A) Crime Map — map with red pin marker and location label
B) Location Card — split layout with map + case info overlay

Uses OpenStreetMap tiles with Stamen Toner style for a dark,
documentary-appropriate aesthetic.
"""

import io
import math
import os
import hashlib
import time
import urllib.request
import urllib.parse
import json
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1920, 1080
TILE_SIZE = 256
MAP_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_cache")

USER_AGENT = "AIvideo-DocuMapGen/1.0 (crime documentary map generator; non-commercial research)"

TILE_URLS = [
    "https://tile.openstreetmap.org/{z}/{x}/{y}.png",  # free, no API key
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Font helpers (same as info_cards.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _find_font() -> str:
    for p in [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(p):
            return p
    return ""


FONT_PATH = _find_font()


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Geo / tile math
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _deg2tile(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Convert lat/lon to fractional tile coordinates at given zoom."""
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _geocode(city: str, country: str) -> tuple[float, float] | None:
    """Geocode city/country via Nominatim. Returns (lat, lon) or None."""
    query = f"{city}, {country}"
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode({"q": query, "format": "json", "limit": "1"})
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  [MapGen] Geocoding failed for '{query}': {e}")
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tile download with caching
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _download_tile(z: int, x: int, y: int) -> Image.Image | None:
    """Download a single map tile, using cache if available."""
    os.makedirs(MAP_CACHE_DIR, exist_ok=True)
    cache_key = f"{z}_{x}_{y}"
    cache_path = os.path.join(MAP_CACHE_DIR, f"{cache_key}.png")

    if os.path.exists(cache_path):
        try:
            return Image.open(cache_path).convert("RGB")
        except Exception:
            os.remove(cache_path)

    for tile_url_template in TILE_URLS:
        url = tile_url_template.format(z=z, x=x, y=y)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                tile_data = resp.read()
            tile_img = Image.open(io.BytesIO(tile_data)).convert("RGB")
            # Cache it
            tile_img.save(cache_path, "PNG")
            # Be polite — small delay between tile requests
            time.sleep(0.15)
            return tile_img
        except Exception as e:
            print(f"  [MapGen] Tile {z}/{x}/{y} failed from {tile_url_template.split('/')[2]}: {e}")
            continue

    return None


def _build_map_image(lat: float, lon: float, zoom: int,
                     width: int, height: int, use_fallback_style: bool = False) -> Image.Image:
    """
    Compose a map image centered on lat/lon at the given zoom level.
    Downloads and stitches map tiles to fill width x height pixels.
    """
    cx, cy = _deg2tile(lat, lon, zoom)

    # How many tiles we need in each direction
    tiles_x = math.ceil(width / TILE_SIZE) + 2
    tiles_y = math.ceil(height / TILE_SIZE) + 2

    # Tile range
    start_tx = int(cx) - tiles_x // 2
    start_ty = int(cy) - tiles_y // 2

    # Build large canvas from tiles
    canvas_w = tiles_x * TILE_SIZE
    canvas_h = tiles_y * TILE_SIZE
    canvas = Image.new("RGB", (canvas_w, canvas_h), (20, 20, 25))

    for tx in range(tiles_x):
        for ty in range(tiles_y):
            tile = _download_tile(zoom, start_tx + tx, start_ty + ty)
            if tile:
                tile = tile.resize((TILE_SIZE, TILE_SIZE), Image.LANCZOS)
                canvas.paste(tile, (tx * TILE_SIZE, ty * TILE_SIZE))

    # Calculate pixel offset to center on lat/lon
    frac_x = cx - int(cx)
    frac_y = cy - int(cy)
    offset_x = int((tiles_x // 2 + frac_x) * TILE_SIZE - width / 2)
    offset_y = int((tiles_y // 2 + frac_y) * TILE_SIZE - height / 2)

    # Crop to desired size
    result = canvas.crop((offset_x, offset_y, offset_x + width, offset_y + height))

    # If using fallback OSM tiles (colorful), apply dark desaturation filter
    if use_fallback_style:
        result = result.convert("L").convert("RGB")  # grayscale
        # Darken
        from PIL import ImageEnhance
        result = ImageEnhance.Brightness(result).enhance(0.5)

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Draw map pin
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _draw_pin(draw: ImageDraw.Draw, x: int, y: int, size: int = 24):
    """Draw a red location pin marker at (x, y)."""
    # Pin body (teardrop shape via circle + triangle)
    pin_color = (220, 35, 35)
    pin_outline = (180, 20, 20)

    # Circle (top of pin)
    r = size
    draw.ellipse([x - r, y - r * 2, x + r, y], fill=pin_color, outline=pin_outline, width=2)

    # Point (bottom triangle)
    draw.polygon([
        (x - r // 2, y - 4),
        (x, y + r),
        (x + r // 2, y - 4),
    ], fill=pin_color)

    # Inner white circle
    ir = size // 3
    cy_inner = y - r
    draw.ellipse([x - ir, cy_inner - ir, x + ir, cy_inner + ir], fill=(255, 255, 255))

    # Red glow ring
    glow_r = size + 12
    for i in range(3):
        alpha_r = glow_r + i * 4
        draw.ellipse(
            [x - alpha_r, y - size - alpha_r + size, x + alpha_r, y - size + alpha_r - size],
            outline=(220, 35, 35, 80),
            width=1,
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API: generate_crime_map
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_crime_map(city: str, country: str, label: str,
                       output_path: str, zoom: int = 13) -> str:
    """
    Generate a 1920x1080 crime location map image.

    Args:
        city: City name (e.g. "Taipei" or "台北")
        country: Country name (e.g. "Taiwan" or "台灣")
        label: Location label text (e.g. "案發地點：台北市")
        output_path: Where to save the JPEG
        zoom: Map zoom level (13-14 recommended for city view)

    Returns:
        output_path on success, empty string on failure.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Geocode
    coords = _geocode(city, country)
    if not coords:
        print(f"  [MapGen] Could not geocode '{city}, {country}', generating fallback card")
        return _generate_fallback_map(city, country, label, output_path)

    lat, lon = coords
    print(f"  [MapGen] {city}, {country} -> ({lat:.4f}, {lon:.4f})")

    # Check if Stamen Toner tiles work by testing one tile
    test_tx, test_ty = int(_deg2tile(lat, lon, zoom)[0]), int(_deg2tile(lat, lon, zoom)[1])
    test_tile = _download_tile(zoom, test_tx, test_ty)
    use_fallback_style = False
    if test_tile:
        # Check if tile came from fallback URL (heuristic: colorful = fallback)
        pixels = list(test_tile.getdata())[:20]
        # Stamen Toner is mostly B&W; if we see lots of color, it's the OSM fallback
        color_variance = sum(abs(r - g) + abs(g - b) for r, g, b in pixels) / len(pixels)
        if color_variance > 30:
            use_fallback_style = True

    # Build the map
    map_img = _build_map_image(lat, lon, zoom, W, H, use_fallback_style)

    # Dark overlay for documentary aesthetic
    overlay = Image.new("RGB", (W, H), (0, 0, 0))
    map_img = Image.blend(map_img, overlay, alpha=0.35)

    draw = ImageDraw.Draw(map_img)

    # Red accent bars (top and bottom)
    draw.rectangle([(0, 0), (W, 6)], fill=(180, 20, 20))
    draw.rectangle([(0, H - 6), (W, H)], fill=(180, 20, 20))

    # Pin at center
    pin_x, pin_y = W // 2, H // 2 - 30
    _draw_pin(draw, pin_x, pin_y, size=28)

    # Label background (semi-transparent bar)
    label_y = H - 140
    draw.rectangle([(0, label_y), (W, label_y + 80)], fill=(0, 0, 0))
    draw.rectangle([(0, label_y), (8, label_y + 80)], fill=(200, 30, 30))

    # Label text
    label_text = label if label else f"案發地點：{city}"
    if len(label_text) > 30:
        label_text = label_text[:28] + "..."
    f_label = _font(38)
    draw.text((30, label_y + 18), label_text, font=f_label, fill=(255, 255, 255))

    # Coordinate text (small, bottom-right)
    coord_text = f"{lat:.4f}°N, {lon:.4f}°E"
    f_small = _font(20)
    bbox = draw.textbbox((0, 0), coord_text, font=f_small)
    tw = bbox[2] - bbox[0]
    draw.text((W - tw - 30, label_y + 28), coord_text, font=f_small, fill=(120, 120, 140))

    # Subtle vignette effect
    map_img = _apply_vignette(map_img)

    map_img.save(output_path, "JPEG", quality=95)
    print(f"  [MapGen] Saved crime map: {output_path}")
    return output_path


def _generate_fallback_map(city: str, country: str, label: str,
                           output_path: str) -> str:
    """Generate a text-only location card when geocoding fails."""
    img = Image.new("RGB", (W, H), (15, 15, 20))
    draw = ImageDraw.Draw(img)

    # Dark gradient background
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(10 + 10 * t), int(10 + 8 * t), int(15 + 15 * t)))

    # Red accent bars
    draw.rectangle([(0, 0), (W, 6)], fill=(180, 20, 20))
    draw.rectangle([(0, H - 6), (W, H)], fill=(180, 20, 20))

    # Large crosshair in center
    cx, cy = W // 2, H // 2 - 40
    draw.line([(cx - 60, cy), (cx + 60, cy)], fill=(200, 40, 40), width=2)
    draw.line([(cx, cy - 60), (cx, cy + 60)], fill=(200, 40, 40), width=2)
    draw.ellipse([cx - 40, cy - 40, cx + 40, cy + 40], outline=(200, 40, 40), width=2)
    draw.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], outline=(200, 40, 40), width=2)

    # Location name
    loc_text = f"{city}, {country}"
    f_big = _font(56)
    bbox = draw.textbbox((0, 0), loc_text, font=f_big)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, cy + 80), loc_text, font=f_big, fill=(220, 220, 230))

    # Label
    label_text = label if label else f"案發地點：{city}"
    f_label = _font(34)
    bbox = draw.textbbox((0, 0), label_text, font=f_label)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, cy + 150), label_text, font=f_label, fill=(180, 180, 190))

    img.save(output_path, "JPEG", quality=95)
    print(f"  [MapGen] Saved fallback map card: {output_path}")
    return output_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Public API: generate_location_card
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_location_card(city: str, country: str, date: str,
                           case_name: str, output_path: str) -> str:
    """
    Generate a styled location info card: map on left, case info on right.

    Args:
        city: City name
        country: Country name
        date: Case date (e.g. "1997-04-14")
        case_name: Case title
        output_path: Where to save the JPEG

    Returns:
        output_path on success, empty string on failure.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    img = Image.new("RGB", (W, H), (15, 15, 20))
    draw = ImageDraw.Draw(img)

    # Dark textured background
    import random
    rng = random.Random(hash(case_name) % 2**31)
    for y in range(0, H, 3):
        for x in range(0, W, 5):
            v = rng.randint(14, 24)
            draw.rectangle([x, y, x + 5, y + 3], fill=(v, v - 1, v - 3))

    # Left side: map (960 x 1080)
    map_w = 960
    coords = _geocode(city, country)
    if coords:
        lat, lon = coords
        map_section = _build_map_image(lat, lon, 14, map_w, H)
        # Darken the map
        dark = Image.new("RGB", (map_w, H), (0, 0, 0))
        map_section = Image.blend(map_section, dark, alpha=0.4)
        # Draw pin at center
        map_draw = ImageDraw.Draw(map_section)
        _draw_pin(map_draw, map_w // 2, H // 2 - 30, size=24)
        img.paste(map_section, (0, 0))
    else:
        # Fallback: dark panel with crosshair
        cx, cy = map_w // 2, H // 2
        draw.line([(cx - 50, cy), (cx + 50, cy)], fill=(180, 40, 40), width=2)
        draw.line([(cx, cy - 50), (cx, cy + 50)], fill=(180, 40, 40), width=2)
        draw.ellipse([cx - 35, cy - 35, cx + 35, cy + 35], outline=(180, 40, 40), width=2)

    # Divider line between map and info
    draw.rectangle([(map_w - 2, 0), (map_w + 2, H)], fill=(180, 20, 20))

    # Right side: case info panel
    rx = map_w + 60  # right panel x start

    # Red accent bar on left edge of info panel
    draw.rectangle([(map_w + 4, 0), (map_w + 8, H)], fill=(120, 15, 15))

    # "案發地點" header
    draw.text((rx, 80), "案發地點", font=_font(28), fill=(180, 60, 60))

    # City name (large)
    city_display = city if len(city) <= 12 else city[:10] + "..."
    draw.text((rx, 125), city_display, font=_font(52), fill=(240, 235, 220))

    # Country
    draw.text((rx, 195), country, font=_font(30), fill=(160, 155, 145))

    # Separator
    draw.line([(rx, 260), (W - 60, 260)], fill=(60, 55, 50), width=1)

    # Case info fields
    fields = [
        ("案件名稱", case_name[:20] if len(case_name) > 20 else case_name),
        ("案發日期", date),
        ("案發城市", f"{city}, {country}"),
    ]

    if coords:
        lat, lon = coords
        fields.append(("座標", f"{lat:.4f}°N, {lon:.4f}°E"))

    for i, (label, value) in enumerate(fields):
        fy = 290 + i * 85
        draw.text((rx, fy), f"{label}：", font=_font(26), fill=(130, 120, 105))
        draw.text((rx, fy + 35), value, font=_font(30), fill=(220, 215, 200))
        draw.line([(rx, fy + 75), (W - 60, fy + 75)], fill=(45, 42, 38), width=1)

    # Status badge at bottom-right
    status_text = "調查中"
    f_status = _font(28)
    sb = draw.textbbox((0, 0), status_text, font=f_status)
    sw = sb[2] - sb[0]
    badge_x = W - sw - 100
    badge_y = H - 120
    draw.rounded_rectangle(
        [badge_x - 15, badge_y, badge_x + sw + 15, badge_y + 50],
        radius=6, outline=(180, 140, 30), width=2,
    )
    draw.text((badge_x, badge_y + 6), status_text, font=f_status, fill=(180, 140, 30))

    # Red accent bars (top and bottom)
    draw.rectangle([(0, 0), (W, 5)], fill=(180, 20, 20))
    draw.rectangle([(0, H - 5), (W, H)], fill=(180, 20, 20))

    img.save(output_path, "JPEG", quality=95)
    print(f"  [MapGen] Saved location card: {output_path}")
    return output_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _apply_vignette(img: Image.Image) -> Image.Image:
    """Apply a subtle dark vignette around the edges."""
    w, h = img.size
    vignette = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(vignette)
    # Draw concentric dark ellipses from edge inward
    for i in range(40):
        opacity = int(255 - (i * 6))
        if opacity < 0:
            break
        margin = i * max(w, h) // 120
        x1, y1 = w - margin, h - margin
        if x1 <= margin or y1 <= margin:
            break
        draw.ellipse(
            [margin, margin, x1, y1],
            fill=min(255, 180 + i * 3),
        )
    # Use vignette as brightness mask
    img_rgb = img.convert("RGB")
    r, g, b = img_rgb.split()
    from PIL import ImageChops
    r = ImageChops.multiply(r, vignette)
    g = ImageChops.multiply(g, vignette)
    b = ImageChops.multiply(b, vignette)
    return Image.merge("RGB", (r, g, b))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Convenience: generate both map outputs for a case
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_case_maps(case_data: dict, output_dir: str) -> dict:
    """
    Generate all map assets for a case.

    Args:
        case_data: Research agent output with city, country, date, case_name, etc.
        output_dir: Base output directory for the video project.

    Returns:
        {"crime_map": path, "location_card": path} — empty strings on failure.
    """
    maps_dir = os.path.join(output_dir, "maps")
    os.makedirs(maps_dir, exist_ok=True)

    city = case_data.get("city", "")
    country = case_data.get("country", "")
    date = case_data.get("date", case_data.get("year", ""))
    case_name = case_data.get("case_name", "")

    results = {"crime_map": "", "location_card": ""}

    if not city or not country:
        print("  [MapGen] No city/country in case_data, skipping map generation")
        return results

    label = f"案發地點：{city}"

    # 1. Crime map
    crime_map_path = os.path.join(maps_dir, "crime_map.jpg")
    results["crime_map"] = generate_crime_map(
        city, country, label, crime_map_path
    )

    # 2. Location card
    loc_card_path = os.path.join(maps_dir, "location_card.jpg")
    results["location_card"] = generate_location_card(
        city, country, date, case_name, loc_card_path
    )

    generated = sum(1 for v in results.values() if v)
    print(f"  [MapGen] Generated {generated} map assets")
    return results
