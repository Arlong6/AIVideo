"""
Audio Agent — TTS voiceover + subtitles + background music.

Responsibilities:
- Generate per-section TTS voiceover
- Generate accurate subtitle timing
- Add background music
- Return section timestamps for chapter markers
"""
import os


def generate_audio(script_data: dict, output_dir: str) -> dict:
    """
    Generate all audio: voiceover, subtitles, music.
    Returns timing data for chapter markers.
    """
    print("  [Audio] Generating voiceover and subtitles...")

    sections = script_data.get("sections", [])
    full_script = script_data.get("script", "")

    # 1. Per-section TTS
    from tts_generator import generate_voiceover_sections, generate_voiceover
    if sections:
        vo_path, section_timings = generate_voiceover_sections(
            sections, "zh", output_dir)
    else:
        vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
        generate_voiceover(full_script, "zh", vo_path)
        section_timings = [("full", 0.0)]

    # 2. Get actual duration
    from moviepy.editor import AudioFileClip
    audio = AudioFileClip(os.path.join(output_dir, "voiceover_zh.mp3"))
    duration = audio.duration
    audio.close()

    # 3. Generate subtitles
    from subtitle_generator import generate_srt
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    generate_srt(full_script, duration, srt_path)

    # 4. Background music
    from music_downloader import get_background_music
    get_background_music(output_dir)

    # 5. Chapter markers
    from chapter_generator import generate_chapters
    chapters_text = generate_chapters(section_timings)

    print(f"  [Audio] Complete: {duration:.0f}s ({duration/60:.1f} min), "
          f"{len(section_timings)} chapters")

    return {
        "voiceover_path": os.path.join(output_dir, "voiceover_zh.mp3"),
        "srt_path": srt_path,
        "duration": duration,
        "section_timings": section_timings,
        "chapters_text": chapters_text,
    }
