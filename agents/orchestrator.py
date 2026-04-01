"""
Orchestrator — coordinates all agents to produce a long-form video.

Pipeline:
1. Research Agent → case data
2. Script Agent → 8-section script (uses case data)
3. Research Agent → fact-check script
4. Design Agent → visual direction plan
5. Visual Agent → source footage + info cards (parallel with Audio)
6. Audio Agent → TTS + subtitles + music
7. Assembly → combine everything into final video
8. QA Agent → review quality → pass or retry
"""
import os
import json
import re
from datetime import datetime


def produce_longform(topic: str, output_base: str = "output",
                     upload: bool = False, slot: int = 1) -> dict:
    """
    Full multi-agent pipeline to produce a long-form crime documentary.
    Returns: {"video_path": ..., "qa_report": ..., "metadata": ...}
    """
    print("\n" + "=" * 60)
    print(f"🎬 Multi-Agent Long-Form Production")
    print(f"   Topic: {topic}")
    print("=" * 60)

    # Output directory
    date_str = datetime.now().strftime("%Y%m%d")
    safe_topic = re.sub(r'[^A-Za-z0-9_-]', '_',
                        re.sub(r'[^\x00-\x7F]+', '', topic[:30])).strip('_') or "longform"
    output_dir = os.path.join(output_base, f"{date_str}_long_{safe_topic}")
    os.makedirs(output_dir, exist_ok=True)

    # Wrap entire pipeline in try/except for failure alerts
    from telegram_notify import notify_failure, notify_qa_fail

    try:
        return _run_pipeline(topic, output_dir, upload, slot)
    except Exception as e:
        notify_failure("Pipeline", str(e), topic)
        print(f"\n❌ Pipeline failed: {e}")
        raise


def _run_pipeline(topic, output_dir, upload, slot):
    """Internal pipeline — separated for error handling."""

    # ── Step 1: Research ──────────────────────────────────────────
    print("\n[1/8] 🔍 Research Agent — investigating case...")
    from agents.research_agent import investigate_case
    case_data = investigate_case(topic)
    _save_json(case_data, output_dir, "case_research.json")

    # ── Step 2: Script ────────────────────────────────────────────
    print("\n[2/8] ✍️ Script Agent — writing 8-section script...")
    from agents.script_agent import generate_script
    script_data = generate_script(case_data)
    _save_json(script_data, output_dir, "metadata.json")

    # Save raw script
    with open(os.path.join(output_dir, "script_zh.txt"), "w", encoding="utf-8") as f:
        f.write(script_data.get("script", ""))

    print(f"   Title: {script_data.get('title', '?')}")
    print(f"   Script: {len(script_data.get('script', ''))} chars")

    # ── Step 3: Fact Check ────────────────────────────────────────
    print("\n[3/8] ✅ Research Agent — fact-checking script...")
    from agents.research_agent import fact_check_script
    fc_result = fact_check_script(script_data.get("script", ""), case_data)
    _save_json(fc_result, output_dir, "fact_check.json")

    if fc_result.get("verdict") == "重寫":
        print("   ⚠️ Script needs rewrite — regenerating...")
        script_data = generate_script(case_data)
        _save_json(script_data, output_dir, "metadata.json")

    # ── Step 4: Design Direction ──────────────────────────────────
    print("\n[4/8] 🎨 Design Agent — planning visuals...")
    from agents.design_agent import plan_visual_direction
    visual_plan = plan_visual_direction(script_data, case_data)
    _save_json(visual_plan, output_dir, "visual_plan.json")

    # ── Step 5: Visual Sourcing ───────────────────────────────────
    print("\n[5/8] 📸 Visual Agent — sourcing footage + info cards...")
    from agents.visual_agent import source_visuals
    visual_results = source_visuals(case_data, script_data, visual_plan, output_dir)

    # ── Step 6: Audio Production ──────────────────────────────────
    print("\n[6/8] 🎤 Audio Agent — TTS + subtitles + music...")
    from agents.audio_agent import generate_audio
    audio_results = generate_audio(script_data, output_dir)

    # ── Step 7: Assembly ──────────────────────────────────────────
    print("\n[7/8] 🎬 Assembling final video...")
    from video_assembler import assemble_video
    from thumbnail_generator import generate_thumbnail

    # Thumbnail
    thumb_path = os.path.join(output_dir, "thumbnail.jpg")
    dur_min = int(audio_results["duration"] / 60)
    dur_sec = int(audio_results["duration"] % 60)
    generate_thumbnail(script_data.get("title", topic), thumb_path,
                       fmt="long", duration_hint=f"{dur_min}:{dur_sec:02d}")

    # Assemble
    final_path = assemble_video(
        output_dir, lang="zh",
        wiki_clips=visual_results.get("wiki_clips"),
        scene_pacing=script_data.get("scene_pacing"),
        fmt="long",
        info_cards=visual_results.get("info_cards"),
    )

    # ── Step 8: QA Review ─────────────────────────────────────────
    print("\n[8/8] 🔎 QA Agent — reviewing quality...")
    from agents.qa_agent import review_video
    qa_report = review_video(output_dir, expected_duration=audio_results["duration"])
    _save_json(qa_report, output_dir, "qa_report.json")

    # ── Handle QA verdict ─────────────────────────────────────────
    verdict = qa_report.get("verdict", "REJECT")
    if verdict == "PASS":
        print("\n✅ QA PASSED — video is ready!")
    elif verdict == "FIX_AND_RETRY":
        print("\n⚠️ QA found issues — see report. Video generated but needs review.")
        notify_qa_fail(topic, qa_report.get("issues", []))
    else:
        print("\n❌ QA REJECTED — video has critical issues.")
        notify_qa_fail(topic, qa_report.get("issues", []))

    # ── Upload if requested ───────────────────────────────────────
    youtube_url = None
    if upload and final_path and verdict != "REJECT":
        print("\n📤 Uploading to YouTube...")
        from youtube_uploader import upload_video
        from telegram_notify import notify_upload
        from analytics_tracker import log_video

        upload_meta = dict(script_data)
        upload_meta["description"] = script_data.get("description", "")
        upload_meta["chapters_text"] = audio_results.get("chapters_text", "")

        youtube_url = upload_video(
            final_path, upload_meta, privacy="private",
            thumb_path=thumb_path, publish_at=None)

        if youtube_url:
            notify_upload(topic, youtube_url, slot, "")
            video_id = youtube_url.split("youtu.be/")[-1].split("?")[0]
            log_video(video_id, topic, slot, audio_results["duration"], "")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"🎬 Production Complete!")
    print(f"   📁 Output: {os.path.abspath(output_dir)}")
    if final_path:
        size_mb = os.path.getsize(final_path) / 1024 / 1024
        print(f"   🎥 Video: {size_mb:.0f} MB, {audio_results['duration']/60:.1f} min")
    if youtube_url:
        print(f"   📺 YouTube: {youtube_url}")
    print(f"   📊 QA: {verdict} ({qa_report.get('passed', 0)}/{qa_report.get('total_checks', 0)})")
    print(f"{'=' * 60}\n")

    return {
        "video_path": final_path,
        "output_dir": output_dir,
        "qa_report": qa_report,
        "metadata": script_data,
        "youtube_url": youtube_url,
    }


def _save_json(data, output_dir, filename):
    with open(os.path.join(output_dir, filename), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── CLI entry point ──────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Agent Video Producer")
    parser.add_argument("--topic", required=True, help="Case topic")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--slot", type=int, default=1)
    args = parser.parse_args()

    produce_longform(args.topic, upload=args.upload, slot=args.slot)
