"""
Background music downloader for true crime videos.

Sources (in priority order):
1. Pixabay Music API — explicitly YouTube-safe, no Content ID
2. Synthesized ambient drone — 100% original, zero copyright risk
"""

import os
import random
import subprocess

import requests

MUSIC_CACHE_DIR = "music_cache"

# Pixabay music API key (free at pixabay.com/api/docs/)
try:
    from config import PIXABAY_API_KEY
except ImportError:
    PIXABAY_API_KEY = ""

# Dark ambient search terms for Pixabay music (crime channel default)
PIXABAY_QUERIES = [
    "dark ambient",
    "crime documentary",
    "suspense thriller",
    "dark cinematic",
    "mystery ambient",
    "horror ambient",
    "dark tension",
]

# Contemplative / reflective search terms for books channel (B3 choice)
PIXABAY_QUERIES_CONTEMPLATIVE = [
    "ambient acoustic",
    "gentle strings",
    "contemplative piano",
    "reflective documentary",
    "peaceful cinematic",
    "acoustic emotional",
    "warm ambient",
]


# ── Pixabay Music ──────────────────────────────────────────────────────────────

def _search_pixabay_music(query: str, api_key: str) -> list[dict]:
    """Search Pixabay for music tracks matching query."""
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": api_key,
                "q": query,
                "media_type": "music",
                "per_page": 10,
                "safesearch": "true",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("hits", [])
    except Exception as e:
        print(f"  [WARN] Pixabay music search failed: {e}")
        return []


def _has_audio_stream(path: str) -> bool:
    """True if the file actually contains an audio stream — guards against a
    non-audio response (HTML error page / image) being saved as .mp3, which later
    crashes the ffmpeg music mix. (Seen: an 11KB mjpeg cached as pixabay_*.mp3.)"""
    try:
        import subprocess
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=15).stdout.strip()
        return "audio" in out
    except Exception:
        return False


def _download_pixabay_track(track: dict, cache_path: str) -> bool:
    """Download a Pixabay music track to cache (only if it's genuinely audio)."""
    audio_url = track.get("audio", "") or track.get("previewURL", "")
    if not audio_url:
        return False
    try:
        resp = requests.get(audio_url, timeout=30, headers={"User-Agent": "TrueCrimeBot/1.0"})
        if resp.status_code == 200 and len(resp.content) > 10000:
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            if _has_audio_stream(cache_path):
                return True
            print(f"  [WARN] Pixabay payload has no audio stream — discarding junk")
            try:
                os.remove(cache_path)
            except OSError:
                pass
    except Exception as e:
        print(f"  [WARN] Track download failed: {e}")
    return False


def _get_pixabay_music(output_dir: str, queries: list[str] | None = None) -> str | None:
    """Fetch ambient music from Pixabay. Returns path or None.

    queries: optional override list of search terms. Defaults to the
    dark-ambient list used by the crime channel.
    """
    if not PIXABAY_API_KEY:
        return None

    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    queries = (queries or PIXABAY_QUERIES).copy()
    random.shuffle(queries)

    for query in queries:
        tracks = _search_pixabay_music(query, PIXABAY_API_KEY)
        if not tracks:
            continue
        random.shuffle(tracks)
        for track in tracks[:3]:
            name = track.get("tags", query).replace(",", "").replace(" ", "_")[:30]
            cache_path = os.path.join(MUSIC_CACHE_DIR, f"pixabay_{name}.mp3")
            if (os.path.exists(cache_path) and os.path.getsize(cache_path) > 10000
                    and _has_audio_stream(cache_path)):
                print(f"  Using cached Pixabay track: {name}")
            elif _download_pixabay_track(track, cache_path):
                print(f"  Downloaded Pixabay track: {name}")
            else:
                continue
            dest = os.path.join(output_dir, "background_music.mp3")
            with open(cache_path, "rb") as src, open(dest, "wb") as dst:
                dst.write(src.read())
            print(f"  Music ready (Pixabay): {name}")
            return dest

    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_background_music(output_dir: str, sections: list[dict] = None,
                         total_duration: float = 300,
                         style: str = "dark") -> str | None:
    """
    Get background music for the video.

    style:
      - "dark" (default): crime channel — section-based real music when
        `sections` is given; otherwise NO background music (just voiceover)
      - "contemplative": books channel — picks a random track from
        music_cache/books_library/ (user-managed local MP3 library)

    Synthesized music is NO LONGER used anywhere (it caused ear-ringing — see
    memory/feedback_no_synth_music.md). The section/longform path uses real
    YouTube-safe audio (Pixabay or bundled crime BGM); the non-section path
    returns None (voiceover only) when no real track is available.

    Returns the destination path, or None if no music is available (the
    video assembler handles None as "no background music, just voiceover").
    """
    if sections:
        return _get_section_music(output_dir, sections, total_duration)

    if style == "contemplative":
        return _get_books_library_music(output_dir)

    # No sections + no library track → no music (NOT synth — it causes ear-ringing).
    return None


def _get_books_library_music(output_dir: str) -> str | None:
    """Pick a random MP3 from music_cache/books_library/.

    The folder is user-managed: drop any .mp3 you like and it'll be used.
    Empty folder → returns None → video plays with no background music.
    """
    library_dir = os.path.join(MUSIC_CACHE_DIR, "books_library")
    os.makedirs(library_dir, exist_ok=True)

    tracks = [f for f in os.listdir(library_dir)
              if f.lower().endswith((".mp3", ".m4a", ".wav"))]

    if not tracks:
        print(f"  [INFO] No tracks in {library_dir}/ — books video will play")
        print(f"         without background music. Drop any .mp3 into that")
        print(f"         folder and the next render will pick it up.")
        return None

    track = random.choice(tracks)
    src_path = os.path.join(library_dir, track)
    dest = os.path.join(output_dir, "background_music.mp3")
    with open(src_path, "rb") as src, open(dest, "wb") as dst:
        dst.write(src.read())
    print(f"  Music ready (books library): {track}")
    return dest


_BUNDLED_CRIME_BGM = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "remotion-crime", "public", "music", "crime-bgm.mp3",
)


def _get_section_music(output_dir: str, sections: list[dict],
                       total_duration: float) -> str | None:
    """Background music for the long-form crime video — REAL recorded audio.

    Root-fixed away from synthesis: sustained pure-sine synth pads caused an
    ear-ringing sensation (memory/feedback_no_synth_music.md). We now use a real,
    YouTube-safe track — Pixabay (varied) if an API key is set, otherwise the
    bundled crime BGM committed in the repo — looped/trimmed to total_duration.
    (`sections` is no longer used for per-mood synthesis; one cohesive bed plays
    under the whole video.)
    """
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    dest = os.path.join(output_dir, "background_music.mp3")

    # 1) pick a real source track (Pixabay first for variety, else bundled).
    tmp_src = None
    pix = _get_pixabay_music(output_dir, PIXABAY_QUERIES)
    if pix and os.path.exists(pix):
        # _get_pixabay_music wrote to dest; move it aside so we can loop into dest.
        tmp_src = os.path.join(output_dir, "_bgm_src.mp3")
        os.replace(pix, tmp_src)
        source, label = tmp_src, "Pixabay"
    elif os.path.exists(_BUNDLED_CRIME_BGM):
        source, label = _BUNDLED_CRIME_BGM, "bundled crime BGM"
    else:
        print("  [WARN] no real music source available → voiceover only")
        return None

    # 2) loop/trim the real track to the exact video length.
    result = subprocess.run(
        ["ffmpeg", "-y", "-stream_loop", "-1", "-i", source,
         "-t", str(int(total_duration)), "-q:a", "4", dest],
        capture_output=True,
    )
    if tmp_src and os.path.exists(tmp_src):
        os.remove(tmp_src)

    if result.returncode != 0:
        print("  [WARN] music loop/trim failed → voiceover only")
        return None

    print(f"  Music ready (real {label}, looped to {int(total_duration)}s)")
    return dest
