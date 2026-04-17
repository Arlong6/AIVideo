"""
Crime Reel Adapter — bridges AIvideo's Case-shaped script dict to the
external Remotion renderer at /Users/arlong/Projects/japanese-learner/
nihongo-reels/.

Flow:
  1. Validate case shape
  2. Build assets dir: per-section TTS mp3 (Yunjian voice) + one static image per section
  3. ffprobe each mp3 for exact duration → populate case.timings
  4. Write case.json (Remotion schema)
  5. Invoke render-crime.sh → final_zh.mp4

Failure mode: any step failure raises RuntimeError / ValueError. The top-level
try/except in generate.py will catch it and call notify_failure() + exit(1).
No silent fallback to MoviePy — per the migration plan, Remotion errors should
be visible, not papered over.
"""
import json
import os
import re
import subprocess
from io import BytesIO

import requests
from PIL import Image

from config import PEXELS_API_KEY
from script_generator import _validate_case_shape
from tts_generator import generate_voiceover

REMOTION_PROJECT_DIR = os.getenv(
    "REMOTION_PROJECT_DIR",
    "/Users/arlong/Projects/japanese-learner/nihongo-reels",
)
REMOTION_SCRIPT = os.path.join(REMOTION_PROJECT_DIR, "scripts", "render-crime.sh")
PEXELS_PHOTOS_ENDPOINT = "https://api.pexels.com/v1/search"

# Section order defines both file naming and playback order in the Remotion
# renderer. Must match the Case schema in CRIME_REEL_CONTRACT.md.
# (events are handled specially — one mp3/image per event)
SIMPLE_SECTIONS = ["hook", "setup", "twist", "aftermath", "cta"]


# ── ffprobe (copied from nihongo-reels/scripts/gen_crime_audio.py) ────────────

def _probe_duration(path: str) -> float:
    """Return mp3 duration in seconds. Must match the pattern used by the
    Remotion project so scene timings align."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


# ── ID slugification ──────────────────────────────────────────────────────────

def _slugify_id(raw: str) -> str:
    """Enforce [a-z0-9-]+ and ≤40 chars for the Remotion case folder name."""
    s = raw.lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "case"
    return s[:40].rstrip("-") or "case"


# ── TTS per section ───────────────────────────────────────────────────────────

def _synth_section(text: str, output_path: str, label: str) -> None:
    """Synthesize one section's audio via edge-tts (Yunjian male voice)."""
    if not text or not text.strip():
        raise RuntimeError(f"Empty text for section {label!r}")

    generate_voiceover(text, "zh", output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
        raise RuntimeError(
            f"TTS produced empty/tiny file for section {label!r}: "
            f"{os.path.getsize(output_path) if os.path.exists(output_path) else 'missing'} bytes"
        )


# ── Image acquisition ─────────────────────────────────────────────────────────

def _pexels_photo(query: str, dest_path: str, seen_ids: set) -> bool:
    """Fetch one portrait photo from Pexels /v1/search. Saves to dest_path.
    Uses seen_ids to avoid repeating the same photo across sections/runs.
    Returns True on success, False if no usable photo found."""
    if not PEXELS_API_KEY:
        return False

    try:
        resp = requests.get(
            PEXELS_PHOTOS_ENDPOINT,
            headers={"Authorization": PEXELS_API_KEY},
            params={
                "query": query,
                "per_page": 12,
                "orientation": "portrait",
                "size": "large",
            },
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
    except Exception as e:
        print(f"  [WARN] Pexels photo search failed ({query!r}): {e}")
        return False

    for photo in photos:
        pid = photo.get("id")
        if not pid or pid in seen_ids:
            continue
        # Prefer large2x > large > original
        src = photo.get("src", {})
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        try:
            img_resp = requests.get(url, timeout=20)
            img_resp.raise_for_status()
            img = Image.open(BytesIO(img_resp.content)).convert("RGB")
            img.save(dest_path, "JPEG", quality=90)
            seen_ids.add(pid)
            return True
        except Exception as e:
            print(f"  [WARN] Pexels photo download failed (id={pid}): {e}")
            continue

    return False


def _wiki_fallback(search_term: str, dest_path: str) -> bool:
    """Fallback to Wikimedia Commons archival images. Uses the same
    wiki_footage helpers as the long-form pipeline."""
    from wiki_footage import _search_wikimedia, _extract_meta, _download_image
    try:
        pages = _search_wikimedia(search_term, limit=8)
    except Exception as e:
        print(f"  [WARN] Wikimedia search failed ({search_term!r}): {e}")
        return False

    for page in pages:
        meta = _extract_meta(page)
        if not meta or meta.get("is_sensitive"):
            continue
        arr = _download_image(meta["url"])
        if arr is None:
            continue
        try:
            Image.fromarray(arr).save(dest_path, "JPEG", quality=90)
            return True
        except Exception as e:
            print(f"  [WARN] Wiki image save failed: {e}")
            continue

    return False


GENERIC_CRIME_QUERIES = [
    "dark city alley night",
    "police crime scene tape",
    "detective investigation board",
    "dark courtroom interior",
    "newspaper headline crime",
    "prison cell bars shadow",
    "surveillance camera footage",
    "dark window rain night",
]

def _acquire_image(label: str, query: str, wiki_search_term: str,
                   dest_path: str, seen_ids: set) -> None:
    """Get one image for a section. Try Pexels → Wikimedia → generic fallback."""
    if _pexels_photo(query, dest_path, seen_ids):
        return
    print(f"  [INFO] Pexels miss for {label!r}, trying Wikimedia ({wiki_search_term!r})...")
    if _wiki_fallback(wiki_search_term, dest_path):
        return
    if _wiki_fallback(query, dest_path):
        return
    # Last resort: generic crime-themed stock photo
    import random
    for fallback_q in random.sample(GENERIC_CRIME_QUERIES, min(4, len(GENERIC_CRIME_QUERIES))):
        print(f"  [INFO] Trying generic fallback: {fallback_q!r}")
        if _pexels_photo(fallback_q, dest_path, seen_ids):
            return
    raise RuntimeError(
        f"No image found for section {label!r} after all fallbacks"
    )


# ── Main entry ────────────────────────────────────────────────────────────────

def build_crime_reel(case: dict, output_dir: str) -> str:
    """Build a Remotion crime reel from a Case-shaped script dict.

    Args:
      case: zh dict matching PROMPT_ZH_REMOTION output.
      output_dir: AIvideo per-run folder (assets + case.json + mp4 go here).

    Returns:
      Absolute path to final_zh.mp4.

    Raises:
      ValueError: malformed case.
      RuntimeError: TTS / image / render failure.
    """
    _validate_case_shape(case)

    case["id"] = _slugify_id(case["id"])
    print(f"  Case ID: {case['id']}")

    assets_dir = os.path.join(output_dir, "remotion_assets")
    images_dir = os.path.join(assets_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    # ── Step 1: TTS per section (9 files total) ────────────────────────────
    print("  [1/4] Generating per-section TTS (Yunjian)...")
    tts_map = {
        "hook": case["hook"],
        "setup": case["setup"],
        "twist": case["twist"],
        "aftermath": case["aftermath"],
        "cta": case["cta"],
    }
    for label, text in tts_map.items():
        path = os.path.join(assets_dir, f"{label}.mp3")
        _synth_section(text, path, label)
    for i, ev in enumerate(case["events"], start=1):
        path = os.path.join(assets_dir, f"event-{i}.mp3")
        _synth_section(ev["text"], path, f"event-{i}")

    # ── Step 2: Per-section images (9 files total) ────────────────────────
    print("  [2/4] Acquiring images (Pexels → Wikimedia fallback)...")
    from footage_downloader import _load_seen_ids, _save_seen_ids
    seen_ids = _load_seen_ids()

    wiki_term = case["wiki_search_term"]

    image_requests = [
        ("hook",      case["hook_image_query"],      "hook.jpg"),
        ("setup",     case["setup_image_query"],     "setup.jpg"),
        ("twist",     case["twist_image_query"],     "twist.jpg"),
        ("aftermath", case["aftermath_image_query"], "aftermath.jpg"),
    ]
    for i, ev in enumerate(case["events"], start=1):
        image_requests.append((f"event-{i}", ev["image_query"], f"event-{i}.jpg"))

    for label, query, filename in image_requests:
        dest = os.path.join(images_dir, filename)
        _acquire_image(label, query, wiki_term, dest, seen_ids)
        print(f"    ✓ {filename}")

    # CTA reuses hook image (per plan — short + same closing vibe)
    cta_src = os.path.join(images_dir, "hook.jpg")
    cta_dst = os.path.join(images_dir, "cta.jpg")
    if os.path.exists(cta_src):
        import shutil
        shutil.copy(cta_src, cta_dst)
        print(f"    ✓ cta.jpg (reused hook image)")
    else:
        raise RuntimeError("hook.jpg unexpectedly missing — cannot derive cta image")

    _save_seen_ids(seen_ids)

    # ── Step 3: ffprobe durations + build renderer Case JSON ──────────────
    print("  [3/4] Probing audio durations...")
    def _dur(name: str) -> float:
        d = _probe_duration(os.path.join(assets_dir, name))
        print(f"    {name}: {d:.3f}s")
        return d

    timings = {
        "hook":      _dur("hook.mp3"),
        "setup":     _dur("setup.mp3"),
        "events":    [_dur(f"event-{i}.mp3") for i in range(1, 5)],
        "twist":     _dur("twist.mp3"),
        "aftermath": _dur("aftermath.mp3"),
        "cta":       _dur("cta.mp3"),
    }

    renderer_case = {
        "id": case["id"],
        "title": case["title"],
        "titleZh": case.get("titleZh") or case["title"],
        "date": case["date"],
        "location": case["location"],
        "status": case["status"],
        "statusLabel": case["statusLabel"],
        "hook": case["hook"],
        "hookImage": "images/hook.jpg",
        "setup": case["setup"],
        "setupImage": "images/setup.jpg",
        "events": [
            {"text": ev["text"], "image": f"images/event-{i+1}.jpg"}
            for i, ev in enumerate(case["events"])
        ],
        "twist": case["twist"],
        "twistImage": "images/twist.jpg",
        "aftermath": case["aftermath"],
        "aftermathImage": "images/aftermath.jpg",
        "cta": case["cta"],
        "credits": "照片來源：Pexels / Wikimedia Commons",
        "timings": timings,
    }

    case_json_path = os.path.join(output_dir, "case.json")
    with open(case_json_path, "w", encoding="utf-8") as f:
        json.dump(renderer_case, f, ensure_ascii=False, indent=2)
    print(f"    ✓ case.json written")

    # ── Step 4: Render via Remotion ──────────────────────────────────────
    print("  [4/4] Invoking Remotion renderer...")
    # IMPORTANT: render-crime.sh does `cd $PROJECT_DIR` internally, so all
    # paths passed as arguments MUST be absolute, not relative.
    out_mp4 = os.path.abspath(os.path.join(output_dir, "final_zh.mp4"))

    if not os.path.exists(REMOTION_SCRIPT):
        raise RuntimeError(f"Remotion render script not found: {REMOTION_SCRIPT}")

    result = subprocess.run(
        [REMOTION_SCRIPT,
         "--case", os.path.abspath(case_json_path),
         "--assets", os.path.abspath(assets_dir),
         "--out", out_mp4],
        capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-2000:]
        raise RuntimeError(
            f"Remotion render failed (exit={result.returncode}):\n{tail}"
        )

    if not os.path.exists(out_mp4) or os.path.getsize(out_mp4) < 100_000:
        raise RuntimeError(
            f"Remotion output mp4 missing or suspiciously small: "
            f"{out_mp4} "
            f"({os.path.getsize(out_mp4) if os.path.exists(out_mp4) else 'missing'} bytes)"
        )

    size_mb = os.path.getsize(out_mp4) / 1024 / 1024
    total_dur = (timings["hook"] + timings["setup"] + sum(timings["events"])
                 + timings["twist"] + timings["aftermath"] + timings["cta"])
    print(f"  ✅ Remotion render complete: {out_mp4} "
          f"({size_mb:.1f} MB, {total_dur:.1f}s of audio)")

    return out_mp4
