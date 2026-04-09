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

def _piano_note(freq: float, duration: float, volume: float,
                sample_rate: int = 44100) -> list[float]:
    """Generate a single piano note with natural decay."""
    n = int(duration * sample_rate)
    samples = []
    for i in range(n):
        t = i / sample_rate
        envelope = math.exp(-t * 1.0) * volume
        # Piano timbre: fundamental + harmonics
        s = (math.sin(2 * math.pi * freq * t) * 1.0 +
             math.sin(2 * math.pi * freq * 2 * t) * 0.35 +
             math.sin(2 * math.pi * freq * 3 * t) * 0.12 +
             math.sin(2 * math.pi * freq * 4 * t) * 0.05)
        samples.append(envelope * s)
    return samples


def _string_pad(freqs: list[float], duration: float, volume: float,
                sample_rate: int = 44100) -> list[float]:
    """Generate sustained string chord."""
    n = int(duration * sample_rate)
    samples = [0.0] * n
    for freq in freqs:
        for i in range(n):
            t = i / sample_rate
            swell = 0.3 + 0.7 * (0.5 + 0.5 * math.sin(2 * math.pi * t / 40))
            samples[i] += volume * swell * math.sin(2 * math.pi * freq * t)
    return samples


# Section mood → music style mapping
SECTION_MOODS = {
    "hook":          {"style": "tension_piano", "tempo": "slow", "intensity": 0.7},
    "background":    {"style": "soft_strings", "tempo": "slow", "intensity": 0.4},
    "crime":         {"style": "tension_piano", "tempo": "medium", "intensity": 0.8},
    "investigation": {"style": "suspense_drone", "tempo": "slow", "intensity": 0.5},
    "twist":         {"style": "climax_piano", "tempo": "fast", "intensity": 1.0},
    "resolution":    {"style": "heavy_piano", "tempo": "slow", "intensity": 0.7},
    "reflection":    {"style": "soft_strings", "tempo": "slow", "intensity": 0.3},
    "cta":           {"style": "fade_out", "tempo": "slow", "intensity": 0.2},
}


def _synth_section_music(mood: dict, duration_sec: float,
                         sample_rate: int = 44100) -> list[float]:
    """Generate music for a specific section based on mood."""
    n = int(duration_sec * sample_rate)
    samples = [0.0] * n
    style = mood.get("style", "soft_strings")
    intensity = mood.get("intensity", 0.5)
    import random as _rng

    if style == "tension_piano":
        # Slow minor piano notes, single notes with space
        notes = [(220.0, 1.0), (196.0, 0.9), (174.6, 0.95), (164.8, 0.85),
                 (146.8, 0.9), (130.8, 0.95), (220.0, 0.85), (261.6, 0.9)]
        interval = 3.5 if mood["tempo"] == "slow" else 2.5
        for ni in range(int(duration_sec / interval)):
            freq, vol = notes[ni % len(notes)]
            note = _piano_note(freq, interval, vol * intensity * 0.12, sample_rate)
            start = int(ni * interval * sample_rate)
            for j, s in enumerate(note):
                if start + j < n:
                    samples[start + j] += s

    elif style == "climax_piano":
        # Faster, more intense piano chords
        chords = [
            [(220.0, 261.6, 329.6)],  # Am
            [(196.0, 246.9, 293.7)],  # G
            [(174.6, 220.0, 261.6)],  # F
            [(164.8, 196.0, 246.9)],  # Em
        ]
        interval = 2.0
        for ni in range(int(duration_sec / interval)):
            chord = chords[ni % len(chords)][0]
            start = int(ni * interval * sample_rate)
            for freq in chord:
                note = _piano_note(freq, interval, intensity * 0.10, sample_rate)
                for j, s in enumerate(note):
                    if start + j < n:
                        samples[start + j] += s

    elif style == "heavy_piano":
        # Slow heavy single notes, deeper register
        notes = [(130.8, 1.0), (110.0, 0.95), (98.0, 0.9), (146.8, 0.85),
                 (130.8, 0.9), (110.0, 0.95)]
        interval = 4.0
        for ni in range(int(duration_sec / interval)):
            freq, vol = notes[ni % len(notes)]
            note = _piano_note(freq, interval, vol * intensity * 0.14, sample_rate)
            start = int(ni * interval * sample_rate)
            for j, s in enumerate(note):
                if start + j < n:
                    samples[start + j] += s

    elif style == "soft_strings":
        # Sustained string chord, very gentle
        chord_freqs = [110.0, 130.8, 164.8]  # Am
        pad = _string_pad(chord_freqs, duration_sec, intensity * 0.025, sample_rate)
        for i in range(min(len(pad), n)):
            samples[i] += pad[i]

    elif style == "suspense_drone":
        # Low drone + occasional high shimmer
        for i in range(n):
            t = i / sample_rate
            mod = 0.7 + 0.3 * math.sin(2 * math.pi * 0.04 * t)
            samples[i] += intensity * 0.03 * mod * math.sin(2 * math.pi * 73.4 * t)
            # Occasional high tone
            gate = max(0, math.sin(2 * math.pi * 0.015 * t)) ** 4
            samples[i] += intensity * 0.008 * gate * math.sin(2 * math.pi * 660 * t)

    elif style == "fade_out":
        # Very quiet strings fading away
        chord_freqs = [110.0, 130.8, 164.8]
        pad = _string_pad(chord_freqs, duration_sec, intensity * 0.02, sample_rate)
        for i in range(min(len(pad), n)):
            fade = 1.0 - (i / n)  # linear fade out
            samples[i] += pad[i] * fade

    elif style == "contemplative_piano":
        # Books channel — warm, reflective piano in major key.
        # Uses higher register (D3 through D4) and D major chord tones
        # rather than the dark Am minor used by crime's tension_piano.
        # D3=146.83  F#3=185.00  A3=220.00  D4=293.66  F#4=369.99  A4=440.00
        notes = [
            (293.66, 0.90),  # D4 — sustain
            (369.99, 0.75),  # F#4
            (293.66, 0.70),  # D4
            (220.00, 0.85),  # A3
            (185.00, 0.80),  # F#3
            (293.66, 0.85),  # D4
            (246.94, 0.75),  # B3 — relative minor color
            (329.63, 0.80),  # E4
        ]
        interval = 4.5 if mood["tempo"] == "slow" else 3.0
        for ni in range(int(duration_sec / interval)):
            freq, vol = notes[ni % len(notes)]
            note = _piano_note(freq, interval * 1.2, vol * intensity * 0.10, sample_rate)
            start = int(ni * interval * sample_rate)
            for j, s in enumerate(note):
                if start + j < n:
                    samples[start + j] += s
        # Layer a gentle D major string pad underneath
        chord_freqs = [146.83, 220.00, 293.66]  # D3, A3, D4
        pad = _string_pad(chord_freqs, duration_sec, intensity * 0.018, sample_rate)
        for i in range(min(len(pad), n)):
            samples[i] += pad[i]

    return samples


def _synth_dark_ambient(duration_sec: int = 300) -> bytes:
    """Generate default background music (used for Shorts or when no sections)."""
    return _synth_section_based_music([], duration_sec)


def _synth_contemplative(duration_sec: int = 300) -> bytes:
    """Generate warm reflective music for the books channel (B3 choice).

    Uses contemplative_piano style throughout — D major chord progression,
    higher register, spacious 4.5 sec note intervals, layered string pad.
    Contrast with _synth_dark_ambient which uses Am minor in a lower register.
    """
    sample_rate = 44100
    n = int(duration_sec * sample_rate)
    mood = {"style": "contemplative_piano", "tempo": "slow", "intensity": 0.6}
    samples = _synth_section_music(mood, duration_sec, sample_rate)

    # Global fade in/out
    fade = sample_rate * 3
    for i in range(min(fade, n)):
        samples[i] *= i / fade
        samples[n - 1 - i] *= i / fade

    # Normalize
    peak = max(abs(s) for s in samples) or 1.0
    samples = [s * (0.70 / peak) for s in samples]

    # Convert to WAV bytes
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for s in samples:
            w.writeframes(struct.pack("<h", int(s * 32767)))
    return buf.getvalue()


def _synth_section_based_music(sections: list[dict],
                                total_duration: float = 300) -> bytes:
    """
    Generate music that changes style based on video sections.
    Each section gets appropriate mood music with crossfade transitions.
    """
    sample_rate = 44100

    if not sections:
        # Default: just use tension_piano for the whole duration
        sections = [{"name": "hook", "duration": total_duration}]

    n = int(total_duration * sample_rate)
    samples = [0.0] * n

    # Calculate section durations if not provided
    if not any("duration" in s for s in sections):
        per_section = total_duration / len(sections)
        for s in sections:
            s["duration"] = per_section

    # Generate music per section
    current_pos = 0
    for section in sections:
        name = section.get("name", "background")
        dur = section.get("duration", 30)
        mood = SECTION_MOODS.get(name, SECTION_MOODS["background"])

        section_samples = _synth_section_music(mood, dur + 2, sample_rate)

        # Crossfade: 1 second fade in/out at boundaries
        fade_len = int(1.0 * sample_rate)
        for i, s in enumerate(section_samples):
            pos = current_pos + i
            if pos >= n:
                break
            # Fade in
            fade_in = min(1.0, i / fade_len) if i < fade_len else 1.0
            # Fade out
            remaining = len(section_samples) - i
            fade_out = min(1.0, remaining / fade_len) if remaining < fade_len else 1.0
            samples[pos] += s * fade_in * fade_out

        current_pos += int(dur * sample_rate)

    # Global fade in/out
    fade = sample_rate * 3
    for i in range(min(fade, n)):
        samples[i] *= i / fade
        samples[n - 1 - i] *= i / fade

    # Normalize
    peak = max(abs(s) for s in samples) or 1.0
    samples = [s * (0.70 / peak) for s in samples]

    # Convert to WAV
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for s in samples:
            w.writeframes(struct.pack("<h", int(s * 32767)))
    return buf.getvalue()


def _get_synth_music(output_dir: str, style: str = "dark") -> str | None:
    """Generate and save synthesized ambient music. Returns path.

    style:
      - "dark" (default): crime channel's dark Am ambient drone
      - "contemplative": books channel's warm D major reflective piano
    """
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)

    if style == "contemplative":
        cache_wav = os.path.join(MUSIC_CACHE_DIR, "synth_contemplative.wav")
        cache_mp3 = os.path.join(MUSIC_CACHE_DIR, "synth_contemplative.mp3")
        synth_fn = _synth_contemplative
        label = "contemplative piano"
    else:
        cache_wav = os.path.join(MUSIC_CACHE_DIR, "synth_dark_ambient.wav")
        cache_mp3 = os.path.join(MUSIC_CACHE_DIR, "synth_dark_ambient.mp3")
        synth_fn = _synth_dark_ambient
        label = "dark ambient"

    if not os.path.exists(cache_mp3):
        print(f"  Generating {label} music...")
        wav_bytes = synth_fn(duration_sec=300)
        with open(cache_wav, "wb") as f:
            f.write(wav_bytes)
        # Convert WAV → MP3 via ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", cache_wav, "-q:a", "4", cache_mp3],
            capture_output=True,
        )
        if result.returncode != 0 or not os.path.exists(cache_mp3):
            cache_mp3 = cache_wav
        else:
            os.remove(cache_wav)
        print(f"  {label.capitalize()} ready")

    dest = os.path.join(output_dir, "background_music.mp3")
    with open(cache_mp3, "rb") as src, open(dest, "wb") as dst:
        dst.write(src.read())
    print(f"  Music ready (synthesized {label} — 100% copyright-free)")
    return dest


# ── Public API ─────────────────────────────────────────────────────────────────

def get_background_music(output_dir: str, sections: list[dict] = None,
                         total_duration: float = 300,
                         style: str = "dark") -> str | None:
    """
    Get background music for the video.

    style:
      - "dark" (default): crime channel — synthesized dark ambient drone
      - "contemplative": books channel — picks a random track from
        music_cache/books_library/ (user-managed local MP3 library)

    Synthesized music is explicitly avoided for books because sustained
    pure-sine pads cause an ear-ringing sensation for the user. See
    memory/feedback_no_synth_music.md.

    Returns the destination path, or None if no music is available (the
    video assembler handles None as "no background music, just voiceover").
    """
    if sections:
        return _get_section_music(output_dir, sections, total_duration)

    if style == "contemplative":
        return _get_books_library_music(output_dir)

    return _get_synth_music(output_dir, style=style)


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


def _get_section_music(output_dir: str, sections: list[dict],
                       total_duration: float) -> str | None:
    """Generate section-based music (different mood per section)."""
    os.makedirs(MUSIC_CACHE_DIR, exist_ok=True)
    dest = os.path.join(output_dir, "background_music.mp3")

    print(f"  Generating section-based music ({len(sections)} sections)...")
    for s in sections:
        mood = SECTION_MOODS.get(s.get("name", ""), {})
        print(f"    {s.get('name', '?'):15s} → {mood.get('style', '?')} "
              f"(intensity {mood.get('intensity', 0):.1f})")

    wav_bytes = _synth_section_based_music(sections, total_duration)

    # Save as WAV then convert to MP3
    cache_wav = os.path.join(MUSIC_CACHE_DIR, "section_music.wav")
    with open(cache_wav, "wb") as f:
        f.write(wav_bytes)

    result = subprocess.run(
        ["ffmpeg", "-y", "-i", cache_wav, "-q:a", "4", dest],
        capture_output=True,
    )
    os.remove(cache_wav)

    if result.returncode != 0:
        print("  [WARN] MP3 conversion failed, using WAV")
        dest = dest.replace(".mp3", ".wav")
        with open(dest, "wb") as f:
            f.write(wav_bytes)

    print(f"  Music ready (section-based, {len(sections)} moods)")
    return dest
