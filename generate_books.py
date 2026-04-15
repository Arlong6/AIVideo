#!/usr/bin/env python3
"""
Books channel orchestrator — Phase 3 dry run.

Thin wrapper that runs the long-form pipeline for the books channel.
Deliberately KEPT SEPARATE from generate.py so there is zero risk of
affecting the crime channel's 02:00 launchd run.

Skipped vs. crime long-form pipeline:
- YouTube upload (dry run by default)
- Telegram notification
- analytics_tracker logging
- info_cards (victim / timeline cards are crime-specific)
- shorts_extractor (can add back when books channel is producing)

Usage:
    python generate_books.py --topic "1929 華爾街崩盤前夜..."
    python generate_books.py --auto                # pick from data/books/topics.json
    python generate_books.py --auto --skip-render  # script-only dry run
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

# Ensure moviepy can find ffmpeg when launched directly (mirrors daily_run.sh).
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/opt/homebrew/bin/ffmpeg")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)

# Shared engine (channel-agnostic) — same imports crime uses.
from tts_generator import (
    generate_voiceover_sections,
    generate_voiceover,
    generate_voiceover_with_timing,
)
from subtitle_generator import generate_srt
from footage_downloader import download_footage
from wiki_footage import get_wiki_clips
from music_downloader import get_background_music
from video_assembler import assemble_video
from thumbnail_generator import generate_thumbnail
from chapter_generator import generate_chapters

# Books-specific content layer.
from script_generator_books import generate_book_scripts
from script_generator import _normalize_script_field
from topic_manager_books import pick_topic_books, save_used_topic


# ── v5 sentence-pair helpers ──────────────────────────────────────────────────

def _group_sentences_into_pairs(boundaries: list[dict],
                                 pair_size: int = 2) -> list[dict]:
    """Group edge-tts sentence boundaries into pairs for v5 flow.

    edge-tts returns offset/duration in 100-nanosecond units (WinRT MSTTS).
    Converts to seconds and computes the span from the start of the first
    sentence in a pair to the end of the last.

    Returns list of dicts with keys: text, start (sec), duration (sec).
    """
    pairs: list[dict] = []
    for i in range(0, len(boundaries), pair_size):
        chunk = boundaries[i:i + pair_size]
        if not chunk:
            continue
        start_units = chunk[0]["offset"]
        end_units = chunk[-1]["offset"] + chunk[-1]["duration"]
        start_s = start_units / 1e7
        duration_s = max((end_units - start_units) / 1e7, 2.0)  # min 2s per pair
        text = " ".join(s["text"].strip() for s in chunk if s.get("text"))
        if not text:
            continue
        pairs.append({
            "text": text,
            "start": start_s,
            "duration": duration_s,
        })
    return pairs


def _parse_book_from_topic(topic: str) -> dict:
    """Extract book name, author, and event description from the topic string.

    Expected format: '事件描述｜《Book Name》by Author (optional note)'
    Returns: {book, author, description}
    """
    import re
    book_match = re.search(r"《(.+?)》", topic)
    author_match = re.search(r"by\s+(.+?)(?:\s*\(|$)", topic)
    parts = re.split(r"[｜|]", topic)
    desc = parts[0].strip() if len(parts) > 1 else topic[:60]
    return {
        "book": book_match.group(1) if book_match else "unknown",
        "author": author_match.group(1).strip() if author_match else "unknown",
        "description": desc,
    }


def _generate_intro_segment(topic: str, output_dir: str,
                             voice: str, rate: str, pitch: str) -> str | None:
    """Generate the 'AL 說故事' intro segment: TTS + book card visual.

    Returns path to the intro mp4, or None on failure.
    The intro is: '大家好，歡迎來到 AL 說故事。今天的書是《X》，作者是 Y...'
    with a book title card visual behind it.
    """
    import asyncio
    import subprocess
    import edge_tts

    parsed = _parse_book_from_topic(topic)
    intro_text = (
        f"大家好，歡迎來到 AL 說故事。"
        f"今天要分享的書是《{parsed['book']}》，"
        f"作者是 {parsed['author']}。"
        f"這是一個關於{parsed['description']}的故事。"
        f"讓我們一起來看看。"
    )

    intro_audio = os.path.join(output_dir, "_intro_audio.mp3")
    try:
        asyncio.run(edge_tts.Communicate(
            intro_text, voice, rate=rate, pitch=pitch
        ).save(intro_audio))
    except Exception as e:
        print(f"  [WARN] Intro TTS failed: {e}")
        return None

    from moviepy.editor import AudioFileClip
    a = AudioFileClip(intro_audio)
    intro_dur = a.duration
    a.close()

    # Book card visual
    from video_assembler import _make_opening_card
    card_path = os.path.join(output_dir, "_intro_card.mp4")
    card_text = f"本片改編自\n《{parsed['book']}》\n{parsed['author']} 著"
    _make_opening_card(card_text, card_path, duration=intro_dur, fmt="long")

    # Merge card + audio
    intro_vid = os.path.join(output_dir, "_intro.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", card_path, "-i", intro_audio,
        "-c:v", "copy", "-c:a", "aac", "-shortest", intro_vid,
    ], capture_output=True, check=True)

    # Cleanup temp
    for f in (intro_audio, card_path):
        if os.path.exists(f):
            os.remove(f)

    print(f"  Intro generated: {intro_dur:.1f}s — 《{parsed['book']}》by {parsed['author']}")
    return intro_vid


def _prepend_intro_to_video(intro_path: str, main_path: str,
                             output_path: str) -> bool:
    """Concatenate [intro] + [main video] into output_path via ffmpeg."""
    import subprocess
    temp_dir = os.path.dirname(output_path)
    ts_paths = []
    try:
        for i, src in enumerate([intro_path, main_path]):
            ts = os.path.join(temp_dir, f"_concat_ts_{i}.ts")
            subprocess.run([
                "ffmpeg", "-y", "-i", src,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-ar", "44100",
                "-bsf:v", "h264_mp4toannexb", "-f", "mpegts", ts,
            ], capture_output=True, check=True)
            ts_paths.append(ts)

        concat_input = "|".join(os.path.abspath(t) for t in ts_paths)
        subprocess.run([
            "ffmpeg", "-y", "-i", f"concat:{concat_input}",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-movflags", "+faststart", output_path,
        ], capture_output=True, check=True)
        return True
    except Exception as e:
        print(f"  [WARN] Intro concat failed: {e}")
        return False
    finally:
        for f in ts_paths:
            if os.path.exists(f):
                os.remove(f)


def _infer_section_timings_from_script(sections: list[dict],
                                        total_duration: float) -> list[tuple]:
    """Approximate section start times by distributing proportionally to
    section script character counts. Used for chapter markers in v5 where
    we no longer have per-section TTS timings."""
    if not sections or total_duration <= 0:
        return []
    total_chars = sum(len(s.get("script", "")) for s in sections)
    if total_chars == 0:
        return []
    cumulative = 0
    timings = []
    for s in sections:
        start_ratio = cumulative / total_chars
        timings.append((s.get("name", "unknown"), start_ratio * total_duration))
        cumulative += len(s.get("script", ""))
    return timings


def save_metadata(output_dir: str, scripts: dict):
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)


def _notify_telegram(msg: str):
    """Best-effort Telegram status ping. Silent on failure so a missing
    Telegram config can't break the dry-run pipeline."""
    try:
        from telegram_notify import _send_raw
        _send_raw(msg)
    except Exception as e:
        print(f"  [WARN] Telegram notify failed: {e}")


def _run(args):
    # args is already parsed by main(); the dead duplicate argparse block
    # was a leftover from the earlier refactor — removed 2026-04-09.

    # ── Topic selection ───────────────────────────────────────────────────────
    if args.auto:
        print("\n[0/9] Picking books topic...")
        topic = pick_topic_books(refresh=args.refresh_topics)
    elif args.topic:
        topic = args.topic
    else:
        print("[ERROR] Provide --topic or --auto")
        return

    print(f"  Topic: {topic}")

    # ── Output directory ──────────────────────────────────────────────────────
    date_str = datetime.now().strftime("%Y%m%d")
    safe_topic = re.sub(r'[^A-Za-z0-9_-]', '_',
                        re.sub(r'[^\x00-\x7F]+', '', topic[:30])).strip('_') or "book"
    output_dir = os.path.join("output", f"{date_str}_books_{safe_topic}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"  Output directory: {output_dir}")

    # ── Step 1: Generate long-form script (books DNA + books prompts) ────────
    print("\n[1/9] Generating 15-20 min books script...")
    scripts = generate_book_scripts(topic)
    zh = scripts["zh"]
    save_metadata(output_dir, scripts)

    print(f"  Title: {zh.get('title', topic)}")
    print(f"  Opening card: {zh.get('opening_card', '')}")
    print(f"  Sections: {len(zh.get('sections', []))}")
    print(f"  Total chars: {len(zh.get('script', ''))}")
    print(f"  Visual scenes: {len(zh.get('visual_scenes', []))}")

    # Save full script as text
    zh = _normalize_script_field(zh)
    with open(os.path.join(output_dir, "script_zh.txt"), "w", encoding="utf-8") as f:
        f.write(zh.get("script", ""))

    # Print section summary for quality review
    print("\n  --- Section breakdown ---")
    from title_dna_books import SECTION_NAMES_BOOKS
    for i, s in enumerate(zh.get("sections", []), 1):
        label = SECTION_NAMES_BOOKS.get(s["name"], s["name"])
        chars = len(s.get("script", ""))
        preview = s.get("script", "")[:60].replace("\n", " ")
        print(f"  {i}. 【{label}】{chars} chars — {preview}...")

    if args.skip_render:
        print(f"\n✅ Script dry run complete. Output: {os.path.abspath(output_dir)}")
        print("   Review script_zh.txt and metadata.json, then re-run without --skip-render")
        return

    # ── v5 sentence-pair flow ────────────────────────────────────────────────
    # Books voice: V2 台灣女 HsiaoChen (user-approved 2026-04-11).
    # Crime's dark-toned Yunjian is unchanged.
    BOOKS_VOICE = "zh-TW-HsiaoChenNeural"
    BOOKS_RATE = "-3%"
    BOOKS_PITCH = "+0Hz"

    # ── Step 2: Single-pass TTS with per-sentence timing ─────────────────────
    # v5 uses ONE continuous TTS call on the flat script so sentence
    # boundaries are reliable and there are no silence gaps between sections.
    print("\n[2/9] TTS with sentence timing (v5 single-pass)...")
    flat_script = zh.get("script", "")
    voiceover_path = os.path.join(output_dir, "voiceover_zh.mp3")
    sentence_boundaries = generate_voiceover_with_timing(
        flat_script, "zh", voiceover_path,
        voice=BOOKS_VOICE, rate=BOOKS_RATE, pitch=BOOKS_PITCH,
    )
    print(f"  Captured {len(sentence_boundaries)} sentence boundaries")

    # ── Step 3: Subtitles (from flat script + actual audio duration) ─────────
    print("\n[3/9] Generating subtitles...")
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    from moviepy.editor import AudioFileClip
    audio = AudioFileClip(voiceover_path)
    actual_duration = audio.duration
    audio.close()
    generate_srt(flat_script, actual_duration, srt_path)
    print(f"  Duration: {actual_duration:.1f}s ({actual_duration/60:.1f} min)")

    # ── Step 4: Group sentences into pairs for illustrations ─────────────────
    print("\n[4/9] Grouping sentences into illustration pairs...")
    pairs = _group_sentences_into_pairs(sentence_boundaries, pair_size=2)
    print(f"  {len(sentence_boundaries)} sentences → {len(pairs)} pairs")
    print(f"  Avg pair duration: "
          f"{sum(p['duration'] for p in pairs) / max(len(pairs), 1):.1f}s")

    # ── Step 5: Generate one illustration per pair (Imagen or Pollinations) ──
    print(f"\n[5/9] Generating {len(pairs)} illustrations (v5 sentence-pair)...")
    print(f"  Cost: up to ${len(pairs) * 0.02:.2f} if Imagen (may fall back to free)")
    from illustration_generator import (
        generate_illustrations_from_pairs,
        BOOKS_STYLE_PREFIX,
    )
    clip_paths = generate_illustrations_from_pairs(
        pairs, output_dir,
        style_prefix=BOOKS_STYLE_PREFIX,
        allow_fallback=args.allow_fallback,
    )

    if not clip_paths:
        raise RuntimeError("No illustrations generated — both Imagen and "
                           "Pollinations fallback failed")

    # ── Step 6: Background music (books contemplative library) ──────────────
    print("\n[6/9] Loading books contemplative music...")
    get_background_music(output_dir, style="contemplative")

    # ── Step 7: Thumbnail ────────────────────────────────────────────────────
    print("\n[7/9] Generating thumbnail...")
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    zh_title = zh.get("title", topic)
    generate_thumbnail(zh_title, thumb_path, fmt="long", duration_hint="15:00")

    # ── Step 8: Assemble video using pre-sized pair clips (v5 direct mode) ──
    print("\n[8/9] Assembling v5 books video (direct pair mode)...")
    final_path = assemble_video(
        output_dir,
        lang="zh",
        wiki_clips=[],
        fmt="long",
        info_cards=None,
        direct_cut_paths=clip_paths,
    )

    # ── Step 8.5: Prepend AL 說故事 intro ────────────────────────────────────
    # Auto-generates: "大家好，歡迎來到 AL 說故事。今天的書是《X》..."
    # with a book title card visual. Concatenates in front of main video.
    if final_path:
        print("\n[8.5/9] Generating AL 說故事 intro...")
        intro_path = _generate_intro_segment(
            topic, output_dir,
            voice=BOOKS_VOICE, rate=BOOKS_RATE, pitch=BOOKS_PITCH,
        )
        if intro_path:
            main_path = final_path  # e.g. final_zh.mp4
            combined_path = os.path.join(output_dir, "final_zh_with_intro.mp4")
            if _prepend_intro_to_video(intro_path, main_path, combined_path):
                # Replace main with intro version
                os.remove(main_path)
                os.rename(combined_path, main_path)
                print(f"  ✅ Intro prepended to {os.path.basename(main_path)}")
            else:
                print("  [WARN] Intro concat failed — video saved without intro")
            # Cleanup intro temp
            if os.path.exists(intro_path):
                os.remove(intro_path)
        else:
            print("  [WARN] Intro generation failed — video saved without intro")

    # ── Step 9: Chapter markers (approximate from script proportions) ───────
    print("\n[9/9] Generating chapter markers...")
    from title_dna_books import SECTION_NAMES_BOOKS
    section_timings = _infer_section_timings_from_script(
        zh.get("sections", []), actual_duration,
    )
    chapters_text = generate_chapters(section_timings, section_names=SECTION_NAMES_BOOKS)
    print(f"\n  Chapters:\n{chapters_text}")
    with open(os.path.join(output_dir, "chapters.txt"), "w", encoding="utf-8") as f:
        f.write(chapters_text)

    # ── QA Gate — pre-upload quality check ──────────────────────────────────
    qa_verdict = "SKIP"
    if final_path:
        print("\n  🔎 QA Agent — reviewing quality...")
        from agents.qa_agent import review_video
        qa_report = review_video(output_dir, expected_duration=actual_duration,
                                 channel="books")
        qa_verdict = qa_report.get("verdict", "REJECT")
        # Save report
        import json as _json
        with open(os.path.join(output_dir, "qa_report.json"), "w") as f:
            _json.dump(qa_report, f, ensure_ascii=False, indent=2)

    # ── Mark topic as used only if render succeeded ──────────────────────────
    if final_path and args.auto:
        save_used_topic(topic)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 50}")
    print(f"📊 QA: {qa_verdict}")
    if qa_verdict == "PASS":
        print(f"✅ Books video ready for upload")
    elif qa_verdict == "REJECT":
        print(f"❌ QA REJECTED — critical issues found, do NOT upload")
    else:
        print(f"⚠️ QA found issues — review before uploading")
    print(f"📁 Output: {os.path.abspath(output_dir)}")
    if final_path:
        print(f"🎬 Video: {os.path.basename(final_path)}")
        print(f"📑 Subtitles: subtitles_zh.srt")
        print(f"📖 Chapters: chapters.txt")
    print(f"{'=' * 50}")

    # ── Telegram notification ─────────────────────────────────────────────────
    duration_min = int(actual_duration / 60) if actual_duration else 0
    final_name = os.path.basename(final_path) if final_path else "(no video)"
    qa_icon = "✅" if qa_verdict == "PASS" else ("❌" if qa_verdict == "REJECT" else "⚠️")
    _notify_telegram(
        f"📚 [Books 生成完成]\n"
        f"題材: {topic[:80]}\n"
        f"標題: {zh.get('title', '')[:80]}\n"
        f"時長: ~{duration_min} min\n"
        f"QA: {qa_icon} {qa_verdict}\n"
        f"路徑: {os.path.abspath(output_dir)}\n"
        f"(本機 only，未上傳 YT)"
    )


def main():
    parser = argparse.ArgumentParser(description="Books Channel Video Generator (dry run)")
    parser.add_argument("--topic", type=str, help="Book topic. Format: '事件：描述｜《書名》'")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-pick from data/books/topics.json")
    parser.add_argument("--skip-render", action="store_true",
                        help="Script + metadata only, skip TTS/footage/assembly")
    parser.add_argument("--refresh-topics", action="store_true",
                        help="Ask LLM for new topics before picking")
    parser.add_argument("--allow-fallback", action="store_true",
                        help="EMERGENCY ONLY: allow Pollinations.ai free Flux "
                             "fallback if Imagen quota exhausted. Default is "
                             "Imagen strict mode (quality baseline).")
    args = parser.parse_args()

    try:
        _run(args)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"\n❌ Books dry run FAILED:\n{tb}", file=sys.stderr)
        _notify_telegram(
            f"❌ [AIvideo 說書 dry run 失敗]\n"
            f"Error: {type(e).__name__}: {str(e)[:200]}\n"
            f"(查 output 底下的 log)"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
