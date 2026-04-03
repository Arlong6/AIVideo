"""
Audio Agent — TTS voiceover + subtitles + background music.

KEY: Only generate TTS ONCE. Use the same audio's sentence boundaries
for subtitles. This guarantees perfect sync.
"""
import os


def generate_audio(script_data: dict, output_dir: str) -> dict:
    """Generate voiceover + synced subtitles + music. Single TTS pass."""
    print("  [Audio] Generating voiceover (single pass for perfect sync)...")

    sections = script_data.get("sections", [])
    full_script = script_data.get("script", "")

    # 1. Single TTS pass — get audio + sentence boundaries together
    from tts_generator import generate_voiceover_with_timing

    vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
    boundaries = generate_voiceover_with_timing(full_script, "zh", vo_path)

    # 2. Get actual duration
    from moviepy.editor import AudioFileClip
    audio = AudioFileClip(vo_path)
    duration = audio.duration
    audio.close()

    # 3. Generate SRT from boundaries (same audio = perfect sync)
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    if boundaries:
        from subtitle_generator import generate_srt_from_boundaries
        generate_srt_from_boundaries(boundaries, srt_path)
        print(f"  [Audio] Subtitles: {len(boundaries)} sentences, synced from same audio")
    else:
        from subtitle_generator import generate_srt
        generate_srt(full_script, duration, srt_path)
        print("  [Audio] Subtitles: proportional timing (fallback)")

    # 4. Calculate section timings from boundaries (for chapter markers)
    section_timings = _calc_section_timings(sections, boundaries, full_script)

    # 5. Background music — section-based moods
    from music_downloader import get_background_music
    music_sections = []
    if sections:
        for i, s in enumerate(sections):
            sec_dur = duration / len(sections)  # rough estimate
            if i < len(section_timings) - 1:
                sec_dur = section_timings[i + 1][1] - section_timings[i][1]
            music_sections.append({
                "name": s.get("name", "background"),
                "duration": sec_dur,
            })
    get_background_music(output_dir, sections=music_sections, total_duration=duration)

    # 6. Chapter markers
    from chapter_generator import generate_chapters
    chapters_text = generate_chapters(section_timings)

    print(f"  [Audio] Complete: {duration:.0f}s ({duration/60:.1f} min), "
          f"{len(section_timings)} chapters")

    return {
        "voiceover_path": vo_path,
        "srt_path": srt_path,
        "duration": duration,
        "section_timings": section_timings,
        "chapters_text": chapters_text,
        "boundaries": boundaries,
    }


def _calc_section_timings(sections: list, boundaries: list,
                          full_script: str) -> list[tuple[str, float]]:
    """Calculate section start times by matching text positions in boundaries."""
    if not sections or not boundaries:
        return [("full", 0.0)]

    timings = []
    char_pos = 0

    for section in sections:
        name = section.get("name", "unknown")
        text = section.get("script", "")

        # Find which boundary corresponds to this section's start
        best_time = 0.0
        for b in boundaries:
            b_offset = b["offset"] / 10_000_000
            b_text = b["text"]
            # Check if this boundary's text appears near our position
            idx = full_script.find(b_text[:20], max(0, char_pos - 50))
            if idx >= 0 and idx <= char_pos + 50:
                best_time = b_offset
                break

        timings.append((name, best_time))
        char_pos += len(text)

    return timings
