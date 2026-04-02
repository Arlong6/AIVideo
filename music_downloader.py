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
    Generate a cinematic dark ambient track as WAV bytes.
    Multiple layers: deep drone + tension pad + subtle pulse + high shimmer.
    Evolves over time with slow crossfades. Zero copyright.
    """
    sample_rate = 44100
    n = sample_rate * duration_sec

    samples = [0.0] * n

    # Layer 1: Deep sub-bass drone (foundation)
    for freq, amp, lfo in [(36.7, 0.20, 0.04), (55.0, 0.18, 0.06), (73.4, 0.10, 0.08)]:
        for i in range(n):
            t = i / sample_rate
            mod = 1.0 - 0.3 + 0.3 * math.sin(2 * math.pi * lfo * t)
            samples[i] += amp * mod * math.sin(2 * math.pi * freq * t)

    # Layer 2: Tension pad (minor chord, slow swell)
    # A minor: A2=110, C3=130.8, E3=164.8
    for freq, amp, lfo in [(110.0, 0.08, 0.03), (130.8, 0.06, 0.05), (164.8, 0.05, 0.04)]:
        for i in range(n):
            t = i / sample_rate
            # Slow swell: fades in and out over 30-second cycles
            swell = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 30))
            mod = 1.0 - 0.2 + 0.2 * math.sin(2 * math.pi * lfo * t)
            samples[i] += amp * swell * mod * math.sin(2 * math.pi * freq * t)

    # Layer 3: Heartbeat-like pulse (very subtle)
    pulse_freq = 0.9  # ~54 bpm, slightly unsettling
    for i in range(n):
        t = i / sample_rate
        pulse = max(0, math.sin(2 * math.pi * pulse_freq * t)) ** 8
        samples[i] += 0.06 * pulse * math.sin(2 * math.pi * 55 * t)

    # Layer 4: High shimmer (adds air and eeriness)
    for freq, amp, lfo in [(880, 0.015, 0.07), (1320, 0.008, 0.11), (1760, 0.005, 0.09)]:
        for i in range(n):
            t = i / sample_rate
            # Only present 40% of the time (random-ish via slow LFO)
            gate = max(0, math.sin(2 * math.pi * 0.02 * t + freq * 0.01))
            mod = 0.5 + 0.5 * math.sin(2 * math.pi * lfo * t)
            samples[i] += amp * gate * mod * math.sin(2 * math.pi * freq * t)

    # Layer 5: Occasional low rumble (tension builder)
    for i in range(n):
        t = i / sample_rate
        # Rumble every ~45 seconds, lasts ~8 seconds
        cycle = t % 45
        if cycle < 8:
            rumble_env = math.sin(math.pi * cycle / 8)
            samples[i] += 0.12 * rumble_env * math.sin(2 * math.pi * 30 * t)

    # Fade in / out (5 seconds each for smoother transitions)
    fade = sample_rate * 5
    for i in range(fade):
        samples[i] *= i / fade
        samples[n - 1 - i] *= i / fade

    # Normalize
    peak = max(abs(s) for s in samples)
    if peak > 0:
        samples = [s * (0.75 / peak) for s in samples]

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
