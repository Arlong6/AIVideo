import asyncio
import edge_tts
from config import VOICE_ZH, VOICE_EN, ELEVENLABS_API_KEY

# edge-tts settings for Chinese (dramatic true crime — TW Mandarin)
TTS_RATE_ZH = "-8%"   # slightly slower than default for gravitas
TTS_PITCH_ZH = "-5Hz" # slightly lower for dark tone


def generate_voiceover(text: str, lang: str, output_path: str):
    """
    Chinese: edge-tts (Microsoft neural voices, better Chinese intonation)
    English: ElevenLabs (more expressive, natural storytelling)
    """
    # ElevenLabs disabled (quota exhausted — re-enable when plan upgraded)
    # if lang == "en" and ELEVENLABS_API_KEY:
    #     try:
    #         _generate_elevenlabs(text, output_path)
    #         return
    #     except Exception as e:
    #         print(f"  [WARN] ElevenLabs failed ({e.__class__.__name__}: {e}), falling back to edge-tts")
    _generate_edge_tts(text, lang, output_path)


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


def _generate_edge_tts(text: str, lang: str, output_path: str):
    if lang == "zh":
        voice, rate, pitch = VOICE_ZH, TTS_RATE_ZH, TTS_PITCH_ZH
    else:
        voice, rate, pitch = VOICE_EN, "-10%", "-2Hz"

    asyncio.run(_edge_tts_async(text, voice, rate, pitch, output_path))
    print(f"  Voiceover saved (edge-tts {lang.upper()}): {output_path}")


def generate_voiceover_sections(sections: list[dict], lang: str,
                                 output_dir: str) -> tuple[str, list[tuple[str, float]]]:
    """
    Generate TTS per-section, concatenate, return (final_audio_path, section_timings).

    sections: list of {"name": "hook", "script": "..."}
    Returns: (combined_audio_path, [(section_name, start_seconds), ...])
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
        generate_voiceover(text, lang, section_path)

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
