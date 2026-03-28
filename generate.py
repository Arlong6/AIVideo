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

from script_generator import generate_scripts
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
    parser.add_argument("--slot", type=int, choices=[1, 2], default=None,
                        help="Schedule slot: 1=10:00 AM, 2=18:00 PM (Taiwan time)")
    args = parser.parse_args()

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

    # Step 1: Generate scripts
    print("\n[1/6] Generating scripts with Claude...")
    scripts = generate_scripts(topic)
    for lang, data in scripts.items():
        script_path = os.path.join(output_dir, f"script_{lang}.txt")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(data.get("script", ""))
        print(f"  Script saved: script_{lang}.txt")
    save_metadata(output_dir, scripts)

    # Step 2: Generate voiceovers
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
    # Use first 2 English keywords as search term (specific enough for Wikimedia)
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
            slot_hour = 10 if args.slot == 1 else 18
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
            notify_upload(topic, youtube_url, args.slot or 1, pub_str)
            # Log to analytics tracker
            video_id = youtube_url.split("youtu.be/")[-1].split("?")[0]
            from moviepy.editor import VideoFileClip as _VFC
            try:
                _dur = _VFC(final_path, audio=False).duration
            except Exception:
                _dur = 0
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


if __name__ == "__main__":
    main()
