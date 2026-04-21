"""
Scene-aware footage downloader.
Downloads Pexels clips in story order — each visual scene gets its own search query,
so clips are thematically matched to the narration arc.
Files named s{scene_idx:02d}_clip{n}.mp4 so assembler can preserve scene order.
"""

import requests
import os
import json
from config import PEXELS_API_KEY

# Fallback queries if a scene-specific search returns no results
# Ordered dark → atmospheric, crime-specific first
FALLBACK_QUERIES = [
    # Crime scene atmosphere
    "crime scene police tape night",
    "forensic gloves evidence bag",
    "detective pinning photos board",
    "handcuffs close-up shadow",
    "dark interrogation room single light",
    "police car lights night city",
    "ambulance emergency night street",
    "surveillance camera cctv footage",
    "police officer walking street night",
    "courtroom judge gavel",
    # Asia/Taiwan location specific
    "taipei city street night neon",
    "taiwan city crowd busy street",
    "tokyo japan street night",
    "subway metro station crowd",
    "asian city night lights rainy",
    "hong kong city night crowded",
    "japan alley night dark",
    # Thriller atmosphere
    "dark foggy alley night",
    "rain on window night dark",
    "shadow hand wall thriller",
    "silhouette person dark hallway",
    "old newspaper headlines close-up",
    "blood drops dark floor close-up",
    "abandoned building dark interior",
    "storm lightning dark sky",
    "clock ticking midnight close-up",
]

SEEN_IDS_FILE = "pexels_seen_ids.json"
CLIPS_PER_SCENE = 2   # default clips per scene (Shorts)
CLIPS_PER_SCENE_LONG = 1  # long-form uses fewer Pexels (wiki is primary)


def _load_seen_ids() -> set:
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()


def _save_seen_ids(seen: set):
    with open(SEEN_IDS_FILE, "w") as f:
        json.dump(sorted(seen), f)


def _search_pexels(query: str, page: int, headers: dict,
                    orientation: str = "portrait") -> list:
    """Search Pexels with retry/backoff. Returns list of video objects."""
    import time as _time
    for attempt in range(3):
        try:
            resp = requests.get(
                "https://api.pexels.com/videos/search",
                headers=headers,
                params={"query": query, "per_page": 8, "page": page,
                        "orientation": orientation},
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("videos", [])
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    [WARN] Pexels rate limited, waiting {wait}s...")
                _time.sleep(wait)
                continue
        except Exception as e:
            if attempt < 2:
                print(f"    [WARN] Pexels request failed (retry {attempt+1}): {e}")
                _time.sleep(5 * (attempt + 1))
            else:
                print(f"    [WARN] Pexels request failed after 3 retries: {e}")
    return []


def _download_clip(video: dict, filepath: str) -> bool:
    files = sorted(
        [f for f in video["video_files"] if f["quality"] in ("hd", "sd")],
        key=lambda x: x.get("width", 0),
        reverse=True,
    )
    if not files:
        return False
    try:
        with requests.get(files[0]["link"], stream=True, timeout=30) as r:
            r.raise_for_status()
            with open(filepath, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    fh.write(chunk)
        return True
    except Exception as e:
        print(f"    [WARN] Download failed: {e}")
        return False


def download_footage(visual_scenes: list, output_dir: str, fmt: str = "short"):
    """
    Download stock footage matched to the story's visual scenes.

    visual_scenes: list of English Pexels search queries in story order.
    fmt='short': 2 clips/scene (primary visual). fmt='long': 1 clip/scene (transition only).
    """
    if not PEXELS_API_KEY:
        print("  [SKIP] No Pexels API key — add PEXELS_API_KEY to .env")
        return

    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips_per = CLIPS_PER_SCENE_LONG if fmt == "long" else CLIPS_PER_SCENE
    orientation = "landscape" if fmt == "long" else "portrait"
    headers = {"Authorization": PEXELS_API_KEY}
    seen_ids = _load_seen_ids()
    total_downloaded = 0
    fallback_idx = 0
    pexels_credits = []

    seen_creators = set()  # Avoid same-looking clips from same creator

    for scene_idx, query in enumerate(visual_scenes):
        print(f"  Scene {scene_idx+1:02d}/{len(visual_scenes)}: '{query}'")
        clips_saved = 0

        # Try page 1 then page 2 for this query
        for page in (1, 2, 3):
            if clips_saved >= clips_per:
                break
            videos = _search_pexels(query, page, headers, orientation)
            for video in videos:
                if clips_saved >= clips_per:
                    break
                if video["id"] in seen_ids:
                    continue
                # Skip if same creator already used (prevents similar-looking clips)
                creator = video.get("user", {}).get("name", "Unknown")
                if creator in seen_creators and creator != "Unknown":
                    continue
                filename = f"s{scene_idx:02d}_clip{clips_saved+1}.mp4"
                filepath = os.path.join(clips_dir, filename)
                if _download_clip(video, filepath):
                    seen_ids.add(video["id"])
                    seen_creators.add(creator)
                    clips_saved += 1
                    total_downloaded += 1
                    pexels_credits.append(f"{creator} (Pexels ID: {video['id']})")
                    print(f"    ✅ {filename}")

        # Fallback: if scene query returned nothing, use a generic dark query
        while clips_saved < clips_per:
            fb_query = FALLBACK_QUERIES[fallback_idx % len(FALLBACK_QUERIES)]
            fallback_idx += 1
            print(f"    [FALLBACK] '{fb_query}'")
            videos = _search_pexels(fb_query, 1, headers, orientation)
            for video in videos:
                if clips_saved >= clips_per:
                    break
                if video["id"] in seen_ids:
                    continue
                filename = f"s{scene_idx:02d}_clip{clips_saved+1}.mp4"
                filepath = os.path.join(clips_dir, filename)
                if _download_clip(video, filepath):
                    seen_ids.add(video["id"])
                    clips_saved += 1
                    total_downloaded += 1
                    creator = video.get("user", {}).get("name", "Unknown")
                    pexels_credits.append(f"{creator} (Pexels ID: {video['id']})")
                    print(f"    ✅ {filename} (fallback)")
            if clips_saved == 0:
                break  # give up on this scene

    _save_seen_ids(seen_ids)
    print(f"  Downloaded {total_downloaded} clips ({len(visual_scenes)} scenes × {clips_per})")

    # Save Pexels attribution file
    if pexels_credits:
        credits_path = os.path.join(output_dir, "pexels_credits.txt")
        with open(credits_path, "w", encoding="utf-8") as f:
            f.write("Pexels footage credits:\n")
            for c in sorted(set(pexels_credits)):
                f.write(f"  - {c}\n")
        print(f"  Pexels credits saved: {len(set(pexels_credits))} creators")
