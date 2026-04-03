"""
Visual Agent — footage sourcing and content-matching.

Priority order:
1. Wikimedia real photos (with Pixabay image backup if rate limited)
2. Crime location maps
3. Info cards (case file, timeline, breaking news)
4. Pexels video (transitions only, ASIA-focused keywords)
"""
import os
import time


# Force Asia-focused Pexels searches
ASIA_MODIFIERS = [
    "taiwan", "taipei", "asia", "tokyo", "seoul", "asian city",
    "night asia", "rain asia street",
]


def source_visuals(case_data: dict, script_data: dict,
                   visual_plan: dict, output_dir: str) -> dict:
    """
    Source all visual materials based on Design Agent's plan.
    Returns paths to all generated/downloaded materials.
    """
    print("  [Visual] Sourcing materials...")

    results = {
        "wiki_clips": [],
        "pexels_clips_dir": "",
        "info_cards": {},
        "maps": {},
    }

    # 1. Wikimedia real photos
    wiki_queries = []
    for section in visual_plan.get("sections", []):
        wiki_queries.extend(section.get("wiki_search_queries", []))
    wiki_queries.extend(case_data.get("search_keywords_en", []))
    wiki_queries.extend(case_data.get("search_keywords_zh", []))

    seen = set()
    unique_queries = [q for q in wiki_queries if q.lower() not in seen and not seen.add(q.lower())]

    print(f"  [Visual] Wikimedia: {len(unique_queries)} search queries")
    from wiki_footage import get_wiki_clips
    results["wiki_clips"] = get_wiki_clips(
        " ".join(unique_queries[:5]),
        output_dir, max_images=25
    )

    # If Wikimedia returned too few (rate limited), try Pixabay images as backup
    if len(results["wiki_clips"]) < 5:
        print(f"  [Visual] Wiki only got {len(results['wiki_clips'])}, trying Pixabay images...")
        pixabay_clips = _fetch_pixabay_images(case_data, output_dir, count=15)
        results["wiki_clips"].extend(pixabay_clips)

    # 2. Pexels video — ASIA-focused transition footage
    pexels_queries = []
    for section in visual_plan.get("sections", []):
        raw_queries = section.get("pexels_queries", [])
        for q in raw_queries:
            # Add Asia modifier to non-specific queries
            if not any(kw in q.lower() for kw in ["taiwan", "asia", "japan", "korea", "taipei", "tokyo"]):
                modifier = ASIA_MODIFIERS[len(pexels_queries) % len(ASIA_MODIFIERS)]
                q = f"{q} {modifier}"
            pexels_queries.append(q)

    # Also add script's visual_scenes with Asia modifiers
    for q in script_data.get("visual_scenes", []):
        if not any(kw in q.lower() for kw in ["taiwan", "asia", "japan", "korea"]):
            modifier = ASIA_MODIFIERS[len(pexels_queries) % len(ASIA_MODIFIERS)]
            q = f"{q} {modifier}"
        pexels_queries.append(q)

    # Deduplicate
    seen = set()
    unique_pexels = [q for q in pexels_queries if q.lower() not in seen and not seen.add(q.lower())]

    print(f"  [Visual] Pexels: {len(unique_pexels)} Asia-focused queries")
    from footage_downloader import download_footage
    download_footage(unique_pexels[:50], output_dir, fmt="long")
    results["pexels_clips_dir"] = os.path.join(output_dir, "clips")

    # 3. Info cards (uses case_data directly, no LLM call)
    print("  [Visual] Generating info cards...")
    from info_cards import generate_info_cards
    results["info_cards"] = generate_info_cards(script_data, output_dir, case_data=case_data)

    # 4. Crime location maps
    print("  [Visual] Generating crime location maps...")
    from map_generator import generate_case_maps
    try:
        results["maps"] = generate_case_maps(case_data, output_dir)
    except Exception as e:
        print(f"  [Visual] Map generation failed (non-fatal): {e}")
        results["maps"] = {}

    wiki_count = len(results["wiki_clips"])
    pexels_count = len(os.listdir(results["pexels_clips_dir"])) if os.path.exists(results["pexels_clips_dir"]) else 0
    card_count = len(results["info_cards"])
    map_count = sum(1 for v in results["maps"].values() if v)
    print(f"  [Visual] Complete: {wiki_count} wiki/pixabay, {pexels_count} Pexels, "
          f"{card_count} info cards, {map_count} maps")

    return results


def _fetch_pixabay_images(case_data: dict, output_dir: str, count: int = 15) -> list[str]:
    """
    Fetch still images from Pixabay as backup when Wikimedia is rate-limited.
    Converts to Ken Burns video clips.
    """
    try:
        from config import PIXABAY_API_KEY
    except ImportError:
        return []
    if not PIXABAY_API_KEY:
        return []

    import requests
    import numpy as np
    from PIL import Image
    from io import BytesIO

    queries = case_data.get("search_keywords_en", [])[:5]
    # Add Asia-specific queries
    country = case_data.get("country", "")
    city = case_data.get("city", "")
    if country:
        queries.append(f"{city} {country} city")
    queries.extend(["crime scene dark", "police asia", "court justice"])

    clips_dir = os.path.join(output_dir, "wiki_clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips = []
    existing = len([f for f in os.listdir(clips_dir) if f.endswith(".mp4")])

    for qi, query in enumerate(queries):
        if len(clips) >= count:
            break
        try:
            resp = requests.get("https://pixabay.com/api/", params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": 5,
                "safesearch": "true",
                "orientation": "horizontal",
            }, timeout=15)
            if resp.status_code != 200:
                continue

            hits = resp.json().get("hits", [])
            for hit in hits[:3]:
                if len(clips) >= count:
                    break
                img_url = hit.get("webformatURL", "")
                if not img_url:
                    continue
                try:
                    img_resp = requests.get(img_url, timeout=15)
                    img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    img_arr = np.array(img)

                    # Use Ken Burns from wiki_footage
                    from wiki_footage import _make_ken_burns_clip
                    idx = existing + len(clips)
                    clip_path = os.path.join(clips_dir, f"pixabay_{idx:02d}.mp4")
                    clip = _make_ken_burns_clip(img_arr, duration=4.0)
                    clip.write_videofile(clip_path, fps=25, codec="libx264",
                                        audio=False, logger=None)
                    clip.close()
                    clips.append(clip_path)
                    time.sleep(0.5)
                except Exception:
                    continue
        except Exception:
            continue

    print(f"  [Visual] Pixabay backup: {len(clips)} images converted to clips")
    return clips
