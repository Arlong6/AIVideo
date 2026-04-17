import asyncio
import os
import edge_tts
from config import VOICE_ZH, VOICE_EN, ELEVENLABS_API_KEY

# edge-tts settings for Chinese (dramatic true crime — TW Mandarin)
TTS_RATE_ZH = "-8%"   # slightly slower than default for gravitas
TTS_PITCH_ZH = "-5Hz" # slightly lower for dark tone


def _fix_pronunciation(text: str) -> str:
    """Fix known Edge TTS mispronunciations for Traditional Chinese.

    Edge TTS often gets polyphonic chars (多音字) and number conventions wrong.
    We pre-process the text to guide it toward the correct reading.
    Add entries as you discover new mispronunciations.
    """
    import re

    # ── Number conventions: "228事件" should be "二二八事件" not "兩百二十八" ──
    # Common Taiwan historical events with numeric names
    text = re.sub(r"228", "二二八", text)
    text = re.sub(r"318", "三一八", text)
    text = re.sub(r"921", "九二一", text)
    text = re.sub(r"713", "七一三", text)
    text = re.sub(r"911", "九一一", text)
    text = re.sub(r"119", "一一九", text)

    # ── Polyphonic character fixes (多音字) ──
    # 重重 in "問題重重" = chóngchóng, not zhòngzhòng
    text = text.replace("重重", "層層")  # 層層 always reads céngcéng, close enough
    # 重大 = zhòngdà (correct by default, leave alone)
    # 重新 = chóngxīn — TTS usually gets this right

    # ── Other common TTS mistakes ──
    # 仇 in "報仇" = chóu, not qiú (TTS sometimes reads qiú)
    # 血 in crime context = xiě (colloquial) but TTS reads xuè (literary) — both OK

    return text


def generate_voiceover(text: str, lang: str, output_path: str,
                       voice: str | None = None,
                       rate: str | None = None,
                       pitch: str | None = None):
    """
    Chinese: edge-tts (Microsoft neural voices, better Chinese intonation)

    Optional overrides let non-crime channels (e.g. books) use a different
    voice/rate/pitch without touching the global config. Defaults preserve
    the crime channel's current behavior.
    """
    import re
    # Clean pacing tags + markdown from script before TTS
    text = re.sub(r"\[(?:slow|medium|fast|climax)\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\*+", "", text)  # remove **bold** markers
    text = re.sub(r"#{1,6}\s*", "", text)  # remove ### headings
    text = re.sub(r"[`~]", "", text)  # remove code/strikethrough markers
    text = _fix_pronunciation(text)
    _generate_edge_tts(text, lang, output_path, voice=voice, rate=rate, pitch=pitch)


def _generate_elevenlabs(text: str, output_path: str):
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    audio = client.text_to_speech.convert(
        voice_id="onwK4e9ZLuTAKqWW03F9",  # Daniel - deep crime documentary
        text=text,
        model_id="eleven_multilingual_v2",
        voice_settings=VoiceSettings(
            stability=0.4,
            similarity_boost=0.8,
            style=0.5,
            use_speaker_boost=True,
        ),
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            if chunk:
                f.write(chunk)
    print(f"  Voiceover saved (ElevenLabs EN): {output_path}")


async def _edge_tts_async(text: str, voice: str, rate: str, pitch: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


async def _edge_tts_with_timing(text: str, voice: str, rate: str, pitch: str,
                                 output_path: str) -> list[dict]:
    """Generate TTS and capture sentence boundary timing for subtitle sync."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    boundaries = []
    with open(output_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "SentenceBoundary":
                boundaries.append({
                    "offset": chunk["offset"],
                    "duration": chunk["duration"],
                    "text": chunk["text"],
                })
    return boundaries


def _generate_edge_tts(text: str, lang: str, output_path: str,
                       voice: str | None = None,
                       rate: str | None = None,
                       pitch: str | None = None):
    # Per-call overrides take precedence over config defaults. This lets the
    # books pipeline use a warmer Taiwan female voice without changing the
    # crime channel's config.
    if lang == "zh":
        voice = voice or VOICE_ZH
        rate = rate or TTS_RATE_ZH
        pitch = pitch or TTS_PITCH_ZH
    else:
        voice = voice or VOICE_EN
        rate = rate or "-10%"
        pitch = pitch or "-2Hz"

    # Retry up to 3 times (edge-tts can be flaky)
    import time as _time
    for attempt in range(3):
        try:
            asyncio.run(_edge_tts_async(text, voice, rate, pitch, output_path))
            if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
                print(f"  Voiceover saved (edge-tts {lang.upper()}): {output_path}")
                return
        except Exception as e:
            print(f"  [WARN] TTS attempt {attempt+1} failed: {e}")
            _time.sleep(3)

    # Final fallback: try default voice
    print("  [WARN] Retrying with default zh-TW voice...")
    asyncio.run(_edge_tts_async(text, "zh-TW-YunJheNeural", "-8%", "-5Hz", output_path))
    print(f"  Voiceover saved (fallback voice): {output_path}")


def generate_voiceover_with_timing(text: str, lang: str, output_path: str,
                                    voice: str | None = None,
                                    rate: str | None = None,
                                    pitch: str | None = None) -> list[dict]:
    """Generate voiceover and return sentence boundary timing for precise subtitles.

    Optional voice/rate/pitch overrides let books channel use A4 HsiaoYu
    without touching the crime channel's global config.

    Returns list of sentence dicts with keys: offset (100ns), duration (100ns),
    text (the sentence text).
    """
    import re
    text = re.sub(r"\[(?:slow|medium|fast|climax)\]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\*+", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"[`~]", "", text)

    if lang == "zh":
        voice = voice or VOICE_ZH
        rate = rate or TTS_RATE_ZH
        pitch = pitch or TTS_PITCH_ZH
    else:
        voice = voice or VOICE_EN
        rate = rate or "-10%"
        pitch = pitch or "-2Hz"

    boundaries = asyncio.run(_edge_tts_with_timing(text, voice, rate, pitch, output_path))
    print(f"  Voiceover saved with {len(boundaries)} sentence boundaries: {output_path}")
    return boundaries


def generate_voiceover_sections(sections: list[dict], lang: str,
                                 output_dir: str,
                                 voice: str | None = None,
                                 rate: str | None = None,
                                 pitch: str | None = None) -> tuple[str, list[tuple[str, float]]]:
    """
    Generate TTS per-section, concatenate, return (final_audio_path, section_timings).

    sections: list of {"name": "hook", "script": "..."}
    Returns: (combined_audio_path, [(section_name, start_seconds), ...])

    Optional voice/rate/pitch overrides let non-crime channels use a
    different voice without changing the global config.
    """
    import os
    import subprocess
    from moviepy.editor import AudioFileClip

    section_paths = []
    section_timings = []
    current_time = 0.0

    for i, section in enumerate(sections):
        name = section["name"]
        text = section["script"]
        if not text.strip():
            continue

        section_path = os.path.join(output_dir, f"_tts_{name}.mp3")
        print(f"  TTS section {i+1}/{len(sections)}: {name} ({len(text)} chars)")
        generate_voiceover(text, lang, section_path,
                           voice=voice, rate=rate, pitch=pitch)

        # Get duration
        try:
            audio = AudioFileClip(section_path)
            dur = audio.duration
            audio.close()
        except Exception:
            dur = len(text) * 0.25  # fallback estimate

        section_timings.append((name, current_time))
        section_paths.append(section_path)
        current_time += dur + 0.5  # 0.5s pause between sections

    # Concatenate all section audio with 0.5s silence gaps
    combined_path = os.path.join(output_dir, f"voiceover_{lang}.mp3")
    if len(section_paths) == 1:
        os.rename(section_paths[0], combined_path)
    else:
        # Build ffmpeg concat filter with silence between sections
        filter_parts = []
        inputs = []
        for j, sp in enumerate(section_paths):
            inputs.extend(["-i", sp])
        # Generate 0.5s silence
        silence_path = os.path.join(output_dir, "_silence.mp3")
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "anullsrc=r=44100:cl=stereo", "-t", "0.5",
            "-c:a", "libmp3lame", silence_path,
        ], capture_output=True)

        # Build concat list
        concat_list = os.path.join(output_dir, "_tts_concat.txt")
        with open(concat_list, "w") as f:
            for j, sp in enumerate(section_paths):
                f.write(f"file '{os.path.abspath(sp)}'\n")
                if j < len(section_paths) - 1:
                    f.write(f"file '{os.path.abspath(silence_path)}'\n")

        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", combined_path,
        ], capture_output=True, check=True)

        # Cleanup
        for sp in section_paths:
            os.remove(sp)
        os.remove(silence_path)
        os.remove(concat_list)

    total_dur = current_time
    print(f"  Combined voiceover: {total_dur:.0f}s ({total_dur/60:.1f} min)")
    return combined_path, section_timings
