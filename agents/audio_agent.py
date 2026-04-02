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
    Generate all audio: voiceover (with timing), synced subtitles, music.
    Uses edge-tts sentence boundaries for precise subtitle sync.
    """
    print("  [Audio] Generating voiceover with timing data...")

    sections = script_data.get("sections", [])
    full_script = script_data.get("script", "")

    # 1. Per-section TTS with timing
    from tts_generator import generate_voiceover_sections, generate_voiceover_with_timing

    all_boundaries = []
    if sections:
        vo_path, section_timings = generate_voiceover_sections(
            sections, "zh", output_dir)

        # Now re-generate full voiceover to get sentence boundaries
        # (section concat doesn't give us boundaries across the full audio)
        print("  [Audio] Extracting sentence timing from full voiceover...")
        vo_full_path = os.path.join(output_dir, "voiceover_zh.mp3")
        all_boundaries = generate_voiceover_with_timing(
            full_script, "zh", vo_full_path)
    else:
        vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
        all_boundaries = generate_voiceover_with_timing(
            full_script, "zh", vo_path)
        section_timings = [("full", 0.0)]

    # 2. Get actual duration
    from moviepy.editor import AudioFileClip
    audio = AudioFileClip(os.path.join(output_dir, "voiceover_zh.mp3"))
    duration = audio.duration
    audio.close()

    # 3. Generate synced subtitles (using real timing, not proportional)
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    if all_boundaries:
        from subtitle_generator import generate_srt_from_boundaries
        generate_srt_from_boundaries(all_boundaries, srt_path)
        print(f"  [Audio] Subtitles synced from {len(all_boundaries)} sentence boundaries")
    else:
        from subtitle_generator import generate_srt
        generate_srt(full_script, duration, srt_path)
        print("  [Audio] Subtitles using proportional timing (fallback)")

    # 4. Background music — section-based moods
    from music_downloader import get_background_music
    music_sections = []
    if sections:
        section_dur = duration / len(sections)
        for s in sections:
            music_sections.append({
                "name": s.get("name", "background"),
                "duration": len(s.get("script", "")) * 0.25,  # estimate from text
            })
    get_background_music(output_dir, sections=music_sections, total_duration=duration)

    # 5. Chapter markers
    from chapter_generator import generate_chapters
    chapters_text = generate_chapters(section_timings)

    print(f"  [Audio] Complete: {duration:.0f}s ({duration/60:.1f} min), "
          f"{len(section_timings)} chapters, {len(all_boundaries)} synced sentences")

    return {
        "voiceover_path": os.path.join(output_dir, "voiceover_zh.mp3"),
        "srt_path": srt_path,
        "duration": duration,
        "section_timings": section_timings,
        "chapters_text": chapters_text,
        "boundaries": all_boundaries,
    }
