"""
Wikimedia Commons archival image fetcher for true crime videos.

- Searches Wikimedia Commons for case-related public domain / CC images
- Auto-flags potentially sensitive images (crime scene, victims) → applies mosaic
- Converts static images to Ken Burns video clips (slow zoom/pan)
- Saves attribution to sources.txt for YouTube description use
"""

import os
import json
import random
import requests
import numpy as np
from PIL import Image
from moviepy.editor import VideoClip

TARGET_W, TARGET_H = 1080, 1920

# Wikimedia categories / keywords that flag an image as sensitive
SENSITIVE_KEYWORDS = [
    "dead", "corpse", "body", "deceased", "murder victim",
    "crime scene photograph", "autopsy", "execution photograph",
    "killed", "slain",
]

# Only use these open licenses
ALLOWED_LICENSES = [
    "public domain", "pd", "cc0", "cc by", "cc-by", "cc by-sa", "cc-by-sa",
    "pd-us", "pd-old", "no restrictions",
]


# ── Wikimedia search ──────────────────────────────────────────────────────────

def _search_wikimedia(query: str, limit: int = 10) -> list[dict]:
    """Search Wikimedia Commons for images matching query. Returns list of image info dicts."""
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrnamespace": "6",          # File namespace only
                "gsrsearch": query,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata|size",
                "iiurlwidth": 1200,           # request 1200px thumbnail
                "format": "json",
            },
            headers={
                "User-Agent": "TrueCrimeVideoBot/1.0 (educational; https://github.com/truecrime-bot)"
            },
            timeout=15,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        return list(pages.values())
    except Exception as e:
        print(f"  [WARN] Wikimedia search failed: {e}")
        return []


def _is_image_file(title: str) -> bool:
    t = title.lower().split("?")[0]
    return any(t.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp"))


def _is_image_title(title: str) -> bool:
    """Check the Wikimedia file title (not URL) is an image, not a PDF/audio/video."""
    t = title.lower()
    return any(t.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"))


def _extract_meta(page: dict) -> dict | None:
    """Extract url, license, author, description from a Wikimedia page dict."""
    # Skip non-image files by title first (PDFs, audio, etc.)
    title = page.get("title", "")
    if not _is_image_title(title):
        return None

    ii = page.get("imageinfo", [{}])[0]
    if not ii:
        return None

    url = ii.get("thumburl") or ii.get("url", "")
    if not url or not _is_image_file(url.split("?")[0]):
        return None

    meta = ii.get("extmetadata", {})
    license_raw = (meta.get("LicenseShortName", {}).get("value", "") or
                   meta.get("License", {}).get("value", "")).lower()
    artist = meta.get("Artist", {}).get("value", "Unknown")
    # Strip HTML tags from artist field
    import re
    artist = re.sub(r"<[^>]+>", "", artist).strip() or "Unknown"
    description = meta.get("ImageDescription", {}).get("value", "")
    description = re.sub(r"<[^>]+>", "", description).strip()
    categories = meta.get("Categories", {}).get("value", "").lower()

    # License check
    license_ok = any(lic in license_raw for lic in ALLOWED_LICENSES)
    if not license_ok and license_raw:
        return None   # skip non-free images

    # Sensitivity check
    combined_text = f"{description} {categories}".lower()
    is_sensitive = any(kw in combined_text for kw in SENSITIVE_KEYWORDS)

    return {
        "title": page.get("title", ""),
        "url": url,
        "source_page": f"https://commons.wikimedia.org/wiki/{page.get('title','').replace(' ','_')}",
        "license": license_raw or "public domain",
        "artist": artist,
        "description": description[:120],
        "is_sensitive": is_sensitive,
    }


# ── Image processing ──────────────────────────────────────────────────────────

def _download_image(url: str) -> np.ndarray | None:
    """Download image and return as RGB numpy array."""
    try:
        resp = requests.get(url, timeout=20, headers={"User-Agent": "TrueCrimeBot/1.0"})
        resp.raise_for_status()
        from io import BytesIO
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return np.array(img)
    except Exception as e:
        print(f"  [WARN] Image download failed: {e}")
        return None


def _apply_mosaic(img: np.ndarray, block_size: int = 18) -> np.ndarray:
    """Pixelate entire image to create mosaic/blur effect for sensitive content."""
    pil = Image.fromarray(img)
    small = pil.resize(
        (max(1, pil.width // block_size), max(1, pil.height // block_size)),
        Image.BOX,
    )
    return np.array(small.resize(pil.size, Image.NEAREST))


def _fit_for_ken_burns(img: np.ndarray) -> np.ndarray:
    """
    Resize image so it's larger than TARGET (gives room to pan/zoom).
    Keeps aspect ratio; adds 18% extra on the longer side.
    """
    h, w = img.shape[:2]
    target_ratio = TARGET_W / TARGET_H   # 0.5625 (portrait)
    img_ratio = w / h

    # Scale so the image covers the target with ~18% movement room
    pad = 1.18
    if img_ratio > target_ratio:
        # Landscape → fit height, wide image to pan left-right
        new_h = int(TARGET_H * pad)
        new_w = int(new_h * img_ratio)
    else:
        # Portrait → fit width, tall image to pan up-down
        new_w = int(TARGET_W * pad)
        new_h = int(new_w / img_ratio)

    pil = Image.fromarray(img).resize((new_w, new_h), Image.LANCZOS)
    return np.array(pil)


def _make_ken_burns_clip(img: np.ndarray, duration: float = 4.0) -> VideoClip:
    """
    Create a Ken Burns video clip from a static image.
    Randomly picks one of: zoom_in, zoom_out, pan_right, pan_down.
    """
    base = _fit_for_ken_burns(img)
    bh, bw = base.shape[:2]
    tw, th = TARGET_W, TARGET_H

    effect = random.choice(["zoom_in", "zoom_out", "pan_right", "pan_left"])
    max_dx = bw - tw
    max_dy = bh - th

    def make_frame(t: float) -> np.ndarray:
        p = t / duration  # 0→1

        if effect == "zoom_in":
            # Start zoomed out (full image), end zoomed in (crop smaller area)
            scale = 1.0 - 0.12 * p          # 1.0 → 0.88
            cw = int(tw * (1 / scale))
            ch = int(th * (1 / scale))
            cw = min(cw, bw)
            ch = min(ch, bh)
            x0 = (bw - cw) // 2
            y0 = (bh - ch) // 2
        elif effect == "zoom_out":
            scale = 0.88 + 0.12 * p          # 0.88 → 1.0
            cw = int(tw * (1 / scale))
            ch = int(th * (1 / scale))
            cw = min(cw, bw)
            ch = min(ch, bh)
            x0 = (bw - cw) // 2
            y0 = (bh - ch) // 2
        elif effect == "pan_right":
            x0 = int(max_dx * p)
            y0 = max_dy // 2
            cw, ch = tw, th
        else:  # pan_left
            x0 = max_dx - int(max_dx * p)
            y0 = max_dy // 2
            cw, ch = tw, th

        x0 = max(0, min(x0, bw - cw))
        y0 = max(0, min(y0, bh - ch))
        crop = base[y0:y0 + ch, x0:x0 + cw]
        frame = np.array(Image.fromarray(crop).resize((tw, th), Image.LANCZOS))
        return frame

    return VideoClip(make_frame, duration=duration).set_fps(25)


# ── Public API ────────────────────────────────────────────────────────────────

def _generate_search_queries(topic: str) -> list[str]:
    """Generate diverse search queries to find more real case images."""
    import re
    queries = [topic]

    # Extract English names/terms from topic
    en_words = re.findall(r'[A-Za-z][A-Za-z\s\.]+', topic)
    for w in en_words:
        w = w.strip()
        if len(w) > 2:
            queries.append(w)
            queries.append(f"{w} murder")
            queries.append(f"{w} case")

    # Extract Chinese key terms
    zh_parts = re.findall(r'[\u4e00-\u9fff]+', topic)
    for p in zh_parts:
        if len(p) >= 2:
            queries.append(p)

    # Common modifiers
    base = en_words[0].strip() if en_words else topic[:20]
    queries.extend([
        f"{base} suspect", f"{base} victim", f"{base} crime scene",
        f"{base} court", f"{base} trial", f"{base} newspaper",
        f"{base} police", f"{base} arrest", f"{base} memorial",
    ])

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in queries:
        q_lower = q.strip().lower()
        if q_lower and q_lower not in seen:
            seen.add(q_lower)
            unique.append(q.strip())
    return unique[:20]


def get_wiki_clips(topic: str, output_dir: str, max_images: int = 5) -> list[str]:
    """
    Search Wikimedia Commons for archival images of the case.
    Downloads, reviews for sensitivity, applies Ken Burns, saves as MP4 clips.
    Writes attribution to sources.txt.
    Returns list of clip file paths (in story order).
    """
    wiki_dir = os.path.join(output_dir, "wiki_clips")
    os.makedirs(wiki_dir, exist_ok=True)

    # Generate diverse search queries for better coverage
    queries = _generate_search_queries(topic)

    print(f"  Searching Wikimedia Commons with {len(queries)} queries...")
    all_pages = []
    for q in queries:
        pages = _search_wikimedia(q, limit=10)
        all_pages.extend(pages)
        if len(all_pages) >= max_images * 4:
            break

    # Deduplicate by title
    seen_titles = set()
    unique_pages = []
    for p in all_pages:
        t = p.get("title", "")
        if t not in seen_titles:
            seen_titles.add(t)
            unique_pages.append(p)

    # Extract metadata and filter
    candidates = []
    for page in unique_pages:
        meta = _extract_meta(page)
        if meta:
            candidates.append(meta)

    if not candidates:
        print("  [SKIP] No usable Wikimedia images found")
        return []

    print(f"  Found {len(candidates)} usable images "
          f"({sum(1 for c in candidates if c['is_sensitive'])} sensitive)")

    # Take up to max_images
    selected = candidates[:max_images]
    clip_paths = []
    attribution = []

    for i, meta in enumerate(selected):
        print(f"  [{i+1}/{len(selected)}] {meta['title'][:50]}"
              f"{' [MOSAIC]' if meta['is_sensitive'] else ''}")

        img = _download_image(meta["url"])
        if img is None:
            continue

        # Apply mosaic if sensitive
        if meta["is_sensitive"]:
            img = _apply_mosaic(img)

        # Build Ken Burns clip
        try:
            clip = _make_ken_burns_clip(img, duration=4.0)
            clip_path = os.path.join(wiki_dir, f"wiki_{i:02d}.mp4")
            clip.write_videofile(clip_path, fps=25, codec="libx264",
                                 audio=False, logger=None)
            clip.close()
            clip_paths.append(clip_path)
            attribution.append(meta)
            print(f"    ✅ Saved wiki_{i:02d}.mp4")
        except Exception as e:
            print(f"  [WARN] Ken Burns failed: {e}")

    # Save attribution file
    if attribution:
        _save_attribution(attribution, output_dir)

    print(f"  {len(clip_paths)} wiki clips ready")
    return clip_paths


def _save_attribution(images: list[dict], output_dir: str):
    """Write sources.txt with attribution for YouTube description."""
    lines = [
        "═" * 50,
        "📸 素材來源 (Wikimedia Commons)",
        "═" * 50,
        "",
    ]
    for i, m in enumerate(images, 1):
        flag = " [馬賽克處理]" if m["is_sensitive"] else ""
        lines += [
            f"[{i}] {os.path.basename(m['title'])}{flag}",
            f"    作者: {m['artist']}",
            f"    授權: {m['license']}",
            f"    來源: {m['source_page']}",
            "",
        ]
    lines += [
        "使用 Wikimedia Commons 公開授權素材。",
        "Creative Commons / Public Domain。",
    ]
    path = os.path.join(output_dir, "sources.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Attribution saved: sources.txt")
