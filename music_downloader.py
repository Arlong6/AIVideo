"""
Background music downloader for true crime videos.

Sources (in priority order):
1. Pixabay Music API — explicitly YouTube-safe, no Content ID
2. Synthesized ambient drone — 100% original, zero copyright risk
"""

import os
import random
import struct
import math
import wave
import subprocess

import requests

MUSIC_CACHE_DIR = "music_cache"

# Pixabay music API key (free at pixabay.com/api/docs/)
try:
    from config import PIXABAY_API_KEY
except ImportError:
    PIXABAY_API_KEY = ""

# Dark ambient search terms for Pixabay music
PIXABAY_QUERIES = [
    "dark ambient",
    "crime documentary",
    "suspense thriller",
    "dark cinematic",
    "mystery ambient",
    "horror ambient",
    "dark tension",
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


def _download_pixabay_track(track: dict, cache_path: str) -> bool:
    """Download a Pixabay music track to cache."""
    audio_url = track.get("audio", "") or track.get("previewURL", "")
    if not audio_url:
        return False
    try:
        resp = requests.get(audio_url, timeout=30, headers={"User-Agent": "TrueCrimeBot/1.0"})
        if resp.status_code == 200 and len(resp.content) > 10000:
            with open(cache_path, "wb") as f:
                f.write(resp.content)
            return True
    except Exception as e:
        print(f"  [WARN] Track download failed: {e}")
    return False


def _get_pixabay_music(output_dir: str) -> str | None:
    """Fetch dark ambient music from Pixabay. Returns path or None."""
    if not PIXABAY_API_KEY:
        return None

    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    queries = PIXABAY_QUERIES.copy()
    random.shuffle(queries)

    for query in queries:
        tracks = _search_pixabay_music(query, PIXABAY_API_KEY)
        if not tracks:
            continue
        random.shuffle(tracks)
        for track in tracks[:3]:
            name = track.get("tags", query).replace(",", "").replace(" ", "_")[:30]
            cache_path = os.path.join(MUSIC_CACHE_DIR, f"pixabay_{name}.mp3")
            if os.path.exists(cache_path) and os.path.getsize(cache_path) > 10000:
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


# ── Synthesized ambient drone (fallback) ──────────────────────────────────────

def _synth_dark_ambient(duration_sec: int = 300) -> bytes:
    """
    Dark ambient white noise + eerie tones.
    Style: like rain on a window at night + distant unsettling sounds.
    Comfortable to listen to, no harsh bass. Zero copyright.
    """
    sample_rate = 44100
    n = sample_rate * duration_sec

    samples = [0.0] * n

    # Layer 1: Filtered white noise (dark rain / wind texture)
    import random as _rng
    _rng.seed(42)
    noise_buf = [_rng.gauss(0, 1) for _ in range(n)]
    # Simple low-pass filter (rolling average) for soft noise
    window = 12
    filtered = [0.0] * n
    running = 0.0
    for i in range(n):
        running += noise_buf[i]
        if i >= window:
            running -= noise_buf[i - window]
        filtered[i] = running / window
    # Slow volume modulation on the noise (breathing feel)
    for i in range(n):
        t = i / sample_rate
        breath = 0.6 + 0.4 * math.sin(2 * math.pi * t / 20)  # 20s cycle
        samples[i] += 0.12 * breath * filtered[i]

    # Layer 2: Very gentle pad (minor, eerie but not harsh)
    # E minor: E2=82.4, G2=98, B2=123.5
    for freq, amp, lfo in [(82.4, 0.04, 0.025), (98.0, 0.03, 0.035), (123.5, 0.025, 0.03)]:
        for i in range(n):
            t = i / sample_rate
            swell = 0.2 + 0.8 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 40))
            samples[i] += amp * swell * math.sin(2 * math.pi * freq * t)

    # Layer 3: Distant high-pitched tones (like wind through cracks)
    for freq, amp, lfo in [(660, 0.008, 0.015), (990, 0.005, 0.02), (1100, 0.003, 0.025)]:
        for i in range(n):
            t = i / sample_rate
            # Fades in and out slowly, only present ~30% of the time
            gate = max(0, math.sin(2 * math.pi * 0.012 * t + freq * 0.005)) ** 3
            samples[i] += amp * gate * math.sin(2 * math.pi * freq * t)

    # Layer 4: Occasional deep sigh (every ~60s, very soft)
    for i in range(n):
        t = i / sample_rate
        cycle = t % 60
        if 5 < cycle < 12:
            env = math.sin(math.pi * (cycle - 5) / 7)
            samples[i] += 0.03 * env * math.sin(2 * math.pi * 75 * t)

    # Fade in / out (5 seconds)
    fade = sample_rate * 5
    for i in range(fade):
        samples[i] *= i / fade
        samples[n - 1 - i] *= i / fade

    # Normalize
    peak = max(abs(s) for s in samples) or 1.0
    samples = [s * (0.70 / peak) for s in samples]

    # Convert to 16-bit PCM WAV
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for s in samples:
            w.writeframes(struct.pack("<h", int(s * 32767)))
    return buf.getvalue()


def _get_synth_music(output_dir: str) -> str | None:
    """Generate and save synthesized ambient music. Returns path."""
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    cache_wav = os.path.join(MUSIC_CACHE_DIR, "synth_dark_ambient.wav")
    cache_mp3 = os.path.join(MUSIC_CACHE_DIR, "synth_dark_ambient.mp3")

    if not os.path.exists(cache_mp3):
        print("  Generating ambient drone music...")
        wav_bytes = _synth_dark_ambient(duration_sec=300)
        with open(cache_wav, "wb") as f:
            f.write(wav_bytes)
        # Convert WAV → MP3 via ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", cache_wav, "-q:a", "4", cache_mp3],
            capture_output=True,
        )
        if result.returncode != 0 or not os.path.exists(cache_mp3):
            # Fallback: use WAV directly
            cache_mp3 = cache_wav
        else:
            os.remove(cache_wav)
        print("  Ambient drone ready")

    dest = os.path.join(output_dir, "background_music.mp3")
    with open(cache_mp3, "rb") as src, open(dest, "wb") as dst:
        dst.write(src.read())
    print("  Music ready (synthesized — 100% copyright-free)")
    return dest


# ── Public API ─────────────────────────────────────────────────────────────────

def get_background_music(output_dir: str) -> str | None:
    """
    Get background music for the video.
    Uses synthesized dark ambient drone — 100% original, zero copyright risk.
    """
    return _get_synth_music(output_dir)
