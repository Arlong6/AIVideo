#!/usr/bin/env python3
"""
AI True Crime Video Generator — Full Auto Pipeline
Usage:
  python generate.py --topic "黑色達利亞謀殺案"
  python generate.py --auto
  python generate.py --auto --upload        # also upload to YouTube
  python generate.py --auto --upload --public  # upload as public
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from script_generator import generate_scripts, _normalize_script_field
from tts_generator import generate_voiceover
from subtitle_generator import generate_srt
from footage_downloader import download_footage
from wiki_footage import get_wiki_clips
from music_downloader import get_background_music
from video_assembler import assemble_video
from youtube_uploader import upload_video
from topic_manager import pick_topic, save_used_topic, save_today_reserved
from thumbnail_generator import generate_thumbnail, upload_thumbnail
from telegram_notify import notify_upload
from analytics_tracker import log_video, fetch_and_update_stats, send_daily_report


def save_metadata(output_dir: str, scripts: dict):
    """Save metadata JSON for YouTube uploader."""
    meta_path = os.path.join(output_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="AI True Crime Video Generator")
    parser.add_argument("--topic", type=str, help="Case topic to generate")
    parser.add_argument("--auto", action="store_true", help="Auto-select a random topic")
    parser.add_argument("--upload", action="store_true", help="Upload to YouTube after assembly")
    parser.add_argument("--public", action="store_true", help="Upload as public (default: scheduled)")
    parser.add_argument("--slot", type=int, choices=[1, 2, 3, 4], default=None,
                        help="Schedule slot: 1=10AM, 2=2PM, 3=6PM, 4=10PM (Taiwan)")
    parser.add_argument("--format", type=str, choices=["short", "long"], default="short",
                        help="Video format: short (60s) or long (15-20min)")
    parser.add_argument("--channel", type=str, default="truecrime",
                        help="Content channel: truecrime | books (default: truecrime)")
    args = parser.parse_args()

    # Validate channel early — Phase 3 will add actual dispatch.
    import channel_config
    if args.channel not in channel_config.CHANNELS:
        parser.error(f"Unknown channel: {args.channel}. "
                     f"Known: {', '.join(channel_config.CHANNELS.keys())}")
    if args.channel != "truecrime" and not channel_config.get(args.channel).get("enabled", True):
        parser.error(f"Channel {args.channel!r} exists in config but is not enabled yet "
                     f"(content modules pending). See channel_config.py.")

    if args.format == "long":
        return _generate_long(args)

    if args.auto:
        print("\n[0/6] Picking today's topic...")
        topic = pick_topic(refresh_news=True)
        save_today_reserved(topic)
        print(f"Today's topic: {topic}")
    elif args.topic:
        topic = args.topic
    else:
        parser.print_help()
        return

    # Create output directory (ASCII-only path for ffmpeg/subtitle compatibility)
    date_str = datetime.now().strftime("%Y%m%d")
    safe_topic = re.sub(r'[^A-Za-z0-9_-]', '_', re.sub(r'[^\x00-\x7F]+', '', topic[:30])).strip('_') or f"slot{args.slot or 1}"
    output_dir = os.path.join("output", f"{date_str}_{safe_topic}")
    os.makedirs(output_dir, exist_ok=True)
    print(f"\nOutput directory: {output_dir}")

    # Feature flag: switch crime shorts visual pipeline to Remotion.
    # Affects only short + truecrime. Long-form and books always use MoviePy.
    VIDEO_ENGINE = os.getenv("VIDEO_ENGINE", "moviepy").lower()
    use_remotion = (VIDEO_ENGINE == "remotion"
                    and args.format == "short"
                    and args.channel == "truecrime")

    # Step 1: Generate scripts
    print("\n[1/6] Generating scripts with Claude...")
    scripts = generate_scripts(topic, engine=VIDEO_ENGINE if use_remotion else "moviepy")
    for lang, data in scripts.items():
        # Remotion's zh is Case-shaped (no `script` field) — serialize whole dict.
        # MoviePy zh/en have a `script` string field.
        script_path = os.path.join(output_dir, f"script_{lang}.txt")
        if use_remotion and lang == "zh":
            # Write the joined section texts so the file is still a human-
            # readable transcript for auditing
            case = scripts["zh"]
            text = "\n\n".join([
                f"【hook】{case['hook']}",
                f"【setup】{case['setup']}",
                *[f"【event-{i+1}】{ev['text']}" for i, ev in enumerate(case['events'])],
                f"【twist】{case['twist']}",
                f"【aftermath】{case['aftermath']}",
                f"【cta】{case['cta']}",
            ])
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(text)
        else:
            data = _normalize_script_field(data)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(data.get("script", ""))
        print(f"  Script saved: script_{lang}.txt")
    save_metadata(output_dir, scripts)

    # ─── Remotion branch ───────────────────────────────────────────────────
    # Bypasses MoviePy steps 2-5. TTS is per-section inside the adapter.
    # Images come from Pexels photos / Wikimedia. BGM is baked into the
    # Remotion composition. Subtitles are not burned — SRT is derived from
    # section timings and uploaded to YouTube as a caption track.
    # After this block, final_path + thumb_path are set; we skip to the
    # shared Step 6 upload logic via the `_remotion_done` sentinel.
    final_path = None
    thumb_path = None
    _remotion_done = False
    if use_remotion:
        print("\n[2/3] Remotion: build case + per-section TTS + images + render...")
        from crime_reel_adapter import build_crime_reel
        final_path = build_crime_reel(scripts["zh"], output_dir)

        print("\n[3/3] Generating SRT from case timings (for YouTube CC)...")
        from subtitle_generator import generate_srt_from_case
        srt_path = os.path.join(output_dir, "subtitles_zh.srt")
        case_json_path = os.path.join(output_dir, "case.json")
        generate_srt_from_case(case_json_path, srt_path)

        print("\n  Generating thumbnail...")
        thumb_path = os.path.join(output_dir, "thumbnail.jpg")
        zh_title = scripts["zh"].get("title", topic)
        generate_thumbnail(zh_title, thumb_path, fmt="short", case_data=scripts["zh"])

        _remotion_done = True

    # ─── MoviePy branch (default) ────────────────────────────────────────
    if not _remotion_done:
        print("\n[2/6] Generating voiceovers...")
        for lang, data in scripts.items():
            audio_path = os.path.join(output_dir, f"voiceover_{lang}.mp3")
            generate_voiceover(data.get("script", ""), lang, audio_path)

        # Step 3: Generate subtitles (use actual voiceover duration, not hardcoded 180s)
        print("\n[3/6] Generating subtitles...")
        for lang, data in scripts.items():
            srt_path = os.path.join(output_dir, f"subtitles_{lang}.srt")
            audio_path = os.path.join(output_dir, f"voiceover_{lang}.mp3")
            if os.path.exists(audio_path):
                from moviepy.editor import AudioFileClip as _AFC
                _a = _AFC(audio_path)
                actual_duration = _a.duration
                _a.close()
            else:
                actual_duration = 180.0
            generate_srt(data.get("script", ""), actual_duration, srt_path)

        # Step 4: Download scene-matched stock footage from Pexels
        print("\n[4/6] Downloading scene-matched footage...")
        visual_scenes = scripts["en"].get("visual_scenes") or []
        if not visual_scenes:
            keywords = scripts["en"].get("keywords", ["crime", "mystery", "dark"])
            visual_scenes = keywords * 5
        visual_scenes = visual_scenes[:15]
        print(f"  Using {len(visual_scenes)} visual scene queries")
        download_footage(visual_scenes, output_dir)

        # Step 4c: Fetch archival images from Wikimedia Commons (search in English)
        print("\n[4c/6] Fetching archival images from Wikimedia Commons...")
        en_keywords = scripts["en"].get("keywords", [])
        wiki_search_term = " ".join(en_keywords[:2]) if en_keywords else topic
        wiki_clips = get_wiki_clips(wiki_search_term, output_dir, max_images=5)

        # Step 4.5: Download background music
        print("\n[4.5/6] Downloading background music...")
        get_background_music(output_dir)

        # Step 4.9: Generate thumbnail
        print("\n[4.9/6] Generating thumbnail...")
        thumb_path = os.path.join(output_dir, "thumbnail.jpg")
        zh_title = scripts["zh"].get("title", topic)
        generate_thumbnail(zh_title, thumb_path)

        # Step 5: Assemble video
        print("\n[5/6] Assembling video...")
        scene_pacing = scripts["en"].get("scene_pacing") or None
        final_path = assemble_video(output_dir, lang="zh", wiki_clips=wiki_clips,
                                    scene_pacing=scene_pacing)

    # Step 6: Upload to YouTube (optional)
    youtube_url = None
    if args.upload and final_path:
        print("\n[6/6] Uploading to YouTube...")

        # Calculate scheduled publish time (Taiwan UTC+8)
        publish_at = None
        if args.slot and not args.public:
            TW = ZoneInfo("Asia/Taipei")
            now_tw = datetime.now(TW)
            slot_hour = {1: 10, 2: 14, 3: 18, 4: 22}.get(args.slot, 10)
            publish_dt = now_tw.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            # If slot time already passed today, schedule for tomorrow
            if publish_dt <= now_tw:
                publish_dt += timedelta(days=1)
            publish_at = publish_dt.isoformat()
            print(f"  Scheduled publish: {publish_dt.strftime('%Y-%m-%d %H:%M')} (Taiwan)")

        privacy = "public" if args.public else "private"
        youtube_url = upload_video(final_path, scripts["zh"], privacy=privacy,
                                   thumb_path=thumb_path, publish_at=publish_at)
        if youtube_url:
            pub_str = publish_dt.strftime('%Y-%m-%d %H:%M') if publish_at else ""
            # Get duration for notification + analytics
            video_id = youtube_url.split("youtu.be/")[-1].split("?")[0]
            try:
                from crime_reel_adapter import _probe_duration
                _dur = _probe_duration(final_path)
            except Exception:
                _dur = 0
            notify_upload(topic, youtube_url, args.slot or 1, pub_str,
                          engine=VIDEO_ENGINE, duration_s=_dur,
                          verified=use_remotion)
            log_video(video_id, topic, args.slot or 1, _dur, publish_at or "")
    else:
        print("\n[6/6] Skipping YouTube upload (add --upload to enable)")

    # Mark topic as used (only after successful video)
    if final_path and args.auto:
        save_used_topic(topic)

    # Done
    print(f"\n{'='*50}")
    print(f"✅ Complete! Output: {os.path.abspath(output_dir)}")
    if final_path:
        print(f"🎬 Video: final_zh.mp4")
    if youtube_url:
        print(f"📺 YouTube: {youtube_url}")
    print(f"{'='*50}")


def _generate_long(args):
    """Generate a 15-20 minute long-form crime documentary video."""
    from tts_generator import generate_voiceover_sections
    from chapter_generator import generate_chapters

    # Step 0: Pick topic
    if args.auto:
        print("\n[0/9] Picking topic for long-form video...")
        topic = pick_topic(refresh_news=True)
        save_today_reserved(topic)
    elif args.topic:
        topic = args.topic
    else:
        print("[ERROR] Provide --topic or --auto")
        return

    print(f"  Topic: {topic}")

    # Output directory
    date_str = datetime.now().strftime("%Y%m%d")
    safe_topic = re.sub(r'[^A-Za-z0-9_-]', '_', re.sub(r'[^\x00-\x7F]+', '', topic[:30])).strip('_') or "longform"
    output_dir = os.path.join("output", f"{date_str}_long_{safe_topic}")
    os.makedirs(output_dir, exist_ok=True)

    # Step 1: Generate long-form scripts
    print("\n[1/9] Generating 15-20 min script...")
    scripts = generate_scripts(topic, fmt="long")
    zh = scripts["zh"]
    save_metadata(output_dir, scripts)
    print(f"  Title: {zh.get('title', topic)}")
    print(f"  Sections: {len(zh.get('sections', []))}")

    # Save full script
    zh = _normalize_script_field(zh)
    with open(os.path.join(output_dir, "script_zh.txt"), "w", encoding="utf-8") as f:
        f.write(zh.get("script", ""))

    # Step 2: Generate TTS per section
    print("\n[2/9] Generating voiceover per section...")
    sections = zh.get("sections", [])
    if sections:
        vo_path, section_timings = generate_voiceover_sections(sections, "zh", output_dir)
    else:
        # Fallback: single TTS
        from tts_generator import generate_voiceover
        vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
        generate_voiceover(zh.get("script", ""), "zh", vo_path)
        section_timings = [("full", 0.0)]

    # Step 3: Generate subtitles
    print("\n[3/9] Generating subtitles...")
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    audio_path = os.path.join(output_dir, "voiceover_zh.mp3")
    if os.path.exists(audio_path):
        from moviepy.editor import AudioFileClip
        audio = AudioFileClip(audio_path)
        actual_duration = audio.duration
        audio.close()
        generate_srt(zh.get("script", ""), actual_duration, srt_path)

    # Step 4: Download footage (40-60 scenes)
    print("\n[4/9] Downloading footage (long-form, 1 clip/scene for transitions)...")
    visual_scenes = zh.get("visual_scenes", [])[:60]
    download_footage(visual_scenes, output_dir, fmt="long")

    # Step 5: Get wiki footage
    print("\n[5/9] Fetching archival images (long-form: max 25)...")
    wiki_clips = get_wiki_clips(topic, output_dir, max_images=25)

    # Step 6: Generate thumbnail
    print("\n[6/9] Generating thumbnail...")
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    zh_title = zh.get("title", topic)
    generate_thumbnail(zh_title, thumb_path, fmt="long", duration_hint="15:00")

    # Step 7: Assemble video (16:9 landscape)
    # Step 6.5: Generate info cards (case file, timeline, breaking news)
    print("\n[6.5/9] Generating documentary info cards...")
    from info_cards import generate_info_cards
    info_card_paths = generate_info_cards(zh, output_dir)

    print("\n[7/9] Assembling long-form video (16:9)...")
    scene_pacing = zh.get("scene_pacing")
    final_path = assemble_video(output_dir, lang="zh", wiki_clips=wiki_clips,
                                scene_pacing=scene_pacing, fmt="long",
                                info_cards=info_card_paths)

    # Step 8: Generate chapter markers
    print("\n[8/9] Generating chapter markers...")
    chapters_text = generate_chapters(section_timings)
    print(f"  Chapters:\n{chapters_text}")

    # Step 8.5: Extract Shorts from long-form
    shorts_results = []
    if final_path:
        print("\n[8.5/9] Extracting Shorts from long-form video...")
        from shorts_extractor import extract_shorts
        shorts_results = extract_shorts(final_path, zh, output_dir)

    # Step 9: Upload
    youtube_url = None
    if args.upload and final_path:
        print("\n[9/9] Uploading to YouTube...")
        # Add chapters to description
        description = zh.get("description", "")
        full_description = f"{description}\n\n{chapters_text}"
        upload_meta = dict(zh)
        upload_meta["description"] = full_description

        privacy = "public" if args.public else "private"
        publish_at = None
        if args.slot and not args.public:
            TW = ZoneInfo("Asia/Taipei")
            now_tw = datetime.now(TW)
            slot_hour = {1: 10, 2: 14, 3: 18, 4: 22}.get(args.slot, 10)
            publish_dt = now_tw.replace(hour=slot_hour, minute=0, second=0, microsecond=0)
            if publish_dt <= now_tw:
                publish_dt += timedelta(days=1)
            publish_at = publish_dt.isoformat()

        youtube_url = upload_video(final_path, upload_meta, privacy=privacy,
                                   thumb_path=thumb_path, publish_at=publish_at)
        if youtube_url:
            pub_str = publish_dt.strftime('%Y-%m-%d %H:%M') if publish_at else ""
            notify_upload(topic, youtube_url, args.slot or 1, pub_str)
            video_id = youtube_url.split("youtu.be/")[-1].split("?")[0]
            log_video(video_id, topic, args.slot or 1, actual_duration, publish_at or "")

    # Upload extracted Shorts
    if args.upload and shorts_results:
        print(f"\n  Uploading {len(shorts_results)} Shorts...")
        for si, short in enumerate(shorts_results):
            try:
                short_meta = {
                    "title": short["title"][:100],
                    "description": short.get("description", ""),
                    "hashtags": short.get("hashtags", []),
                }
                s_url = upload_video(short["path"], short_meta, privacy="public",
                                     thumb_path=None, publish_at=None)
                if s_url:
                    print(f"    Short {si+1}: {s_url}")
            except Exception as e:
                print(f"    [WARN] Short {si+1} upload failed: {e}")

    if final_path and args.auto:
        save_used_topic(topic)

    print(f"\n{'='*50}")
    print(f"✅ Long-form video complete! Output: {os.path.abspath(output_dir)}")
    if final_path:
        print(f"🎬 Video: final_zh.mp4")
    if youtube_url:
        print(f"📺 YouTube: {youtube_url}")
    if shorts_results:
        print(f"📱 Shorts: {len(shorts_results)} clips generated")
    print(f"{'='*50}")


if __name__ == "__main__":
    # Wrap main() in a Telegram-reporting error handler. Before this was
    # added (2026-04-09), crime slot 1 crashed silently at 02:00 with a
    # TypeError and the user had no awareness until they manually checked
    # logs the next morning. Per feedback memory `telegram_all_status`,
    # every crash on this script must ping Telegram.
    try:
        main()
    except SystemExit:
        raise  # argparse exits etc. — not an error
    except Exception as _exc:
        import sys as _sys
        import traceback as _tb
        _tb.print_exc()
        # Best-effort: figure out which topic we were processing
        _topic = "unknown"
        try:
            import json as _json
            if os.path.exists("today_topics.json"):
                with open("today_topics.json", "r", encoding="utf-8") as _f:
                    _d = _json.load(_f)
                    _topic = ", ".join(_d.get("topics", []))[:120] or "unknown"
        except Exception:
            pass
        try:
            from telegram_notify import notify_failure
            notify_failure(
                "generate.py",
                f"{type(_exc).__name__}: {str(_exc)[:250]}",
                topic=_topic,
            )
        except Exception as _e:
            print(f"  (could not send telegram alert: {_e})", file=_sys.stderr)
        _sys.exit(1)
