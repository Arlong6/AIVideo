#!/usr/bin/env python3
"""
Resume an incomplete books render — generates remaining illustrations
then assembles the final video.

Scans output/ for books dirs that have:
  - metadata.json (script was generated)
  - voiceover_zh.mp3 (TTS was done)
  - illustrations/ with FEWER PNGs than expected pairs
  - NO final_zh.mp4 or final_zh_with_intro.mp4

If found, resumes from where it stopped: generates missing illustrations,
builds Ken Burns clips, then assembles + adds intro.

Usage:
    python resume_books.py              # auto-find and resume oldest incomplete
    python resume_books.py --dir output/20260413_books_29   # resume specific dir
"""
import argparse
import json
import os
import subprocess
import sys
import time

os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/opt/homebrew/bin/ffmpeg")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)


def find_incomplete_books_dirs() -> list[str]:
    """Find books output dirs that have metadata + TTS but no final video."""
    output_dir = os.path.join(PROJECT_DIR, "output")
    if not os.path.exists(output_dir):
        return []

    incomplete = []
    for name in sorted(os.listdir(output_dir)):
        if "books" not in name:
            continue
        d = os.path.join(output_dir, name)
        if not os.path.isdir(d):
            continue
        meta = os.path.join(d, "metadata.json")
        vo = os.path.join(d, "voiceover_zh.mp3")
        final1 = os.path.join(d, "final_zh.mp4")
        final2 = os.path.join(d, "final_zh_with_intro.mp4")

        if os.path.exists(meta) and os.path.exists(vo):
            if not os.path.exists(final1) and not os.path.exists(final2):
                incomplete.append(d)
    return incomplete


def count_expected_pairs(outdir: str) -> int:
    """Rebuild pair count from saved voiceover."""
    from tts_generator import generate_voiceover_with_timing
    from generate_books import _group_sentences_into_pairs

    with open(os.path.join(outdir, "metadata.json"), "r", encoding="utf-8") as f:
        zh = json.load(f).get("zh", {})

    flat_script = zh.get("script", "")
    vo_path = os.path.join(outdir, "voiceover_zh.mp3")

    boundaries = generate_voiceover_with_timing(
        flat_script, "zh", vo_path,
        voice="zh-TW-HsiaoChenNeural", rate="-3%", pitch="+0Hz",
    )
    pairs = _group_sentences_into_pairs(boundaries, pair_size=2)
    return len(pairs), pairs


def resume_render(outdir: str) -> str | None:
    """Resume an incomplete render. Returns final video path or None."""
    import numpy as np
    from PIL import Image as PILImage
    from illustration_generator import (
        generate_illustration, _make_ken_burns_clip,
        BOOKS_STYLE_PREFIX, ImagenQuotaExhausted,
    )
    from google import genai
    from config import GEMINI_API_KEY

    print(f"\n=== Resuming: {os.path.basename(outdir)} ===")

    total_pairs, pairs = count_expected_pairs(outdir)
    clips_dir = os.path.join(outdir, "clips")
    illust_dir = os.path.join(outdir, "illustrations")
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(illust_dir, exist_ok=True)

    # Find missing pairs
    missing = []
    for i in range(total_pairs):
        png = os.path.join(illust_dir, f"pair_{i:03d}.png")
        clip = os.path.join(clips_dir, f"p{i:03d}_clip1.mp4")
        if not os.path.exists(png) or not os.path.exists(clip):
            missing.append(i)

    existing = total_pairs - len(missing)
    print(f"  Total pairs: {total_pairs}")
    print(f"  Already done: {existing}")
    print(f"  Missing: {len(missing)}")

    if not missing:
        print("  All illustrations present — skipping to assembly")
    else:
        print(f"  Resuming from pair {missing[0]}...")
        client = genai.Client(api_key=GEMINI_API_KEY)
        done = 0

        for idx in missing:
            pair = pairs[idx]
            dur = float(pair["duration"])
            png_path = os.path.join(illust_dir, f"pair_{idx:03d}.png")
            clip_path = os.path.join(clips_dir, f"p{idx:03d}_clip1.mp4")

            print(f"  [{idx + 1}/{total_pairs}] ({dur:.1f}s) {pair['text'][:50]}...")

            try:
                ok = generate_illustration(
                    pair["text"], png_path, client=client,
                    style_prefix=BOOKS_STYLE_PREFIX,
                )
            except ImagenQuotaExhausted:
                print(f"\n  [STOP] Quota exhausted at pair {idx + 1}/{total_pairs}")
                print(f"         Done {done} more this run. Total: {existing + done}/{total_pairs}")
                try:
                    from telegram_notify import _send_raw
                    _send_raw(
                        f"⏸️ [Books 續跑] 額度用完，暫停\n"
                        f"進度: {existing + done}/{total_pairs}\n"
                        f"題材: {os.path.basename(outdir)}\n"
                        f"明天會繼續"
                    )
                except Exception:
                    pass
                return None

            if not ok:
                print(f"    ✗ Failed, skip")
                continue

            try:
                img = np.array(PILImage.open(png_path).convert("RGB"))
                clip = _make_ken_burns_clip(img, duration=dur)
                clip.write_videofile(clip_path, fps=25, codec="libx264",
                                     audio=False, logger=None)
                clip.close()
                done += 1
                print(f"    ✓")
            except Exception as e:
                print(f"    ✗ Ken Burns: {e}")

    # Check if all pairs now exist
    all_clips = sorted([
        os.path.join(clips_dir, f) for f in os.listdir(clips_dir)
        if f.endswith(".mp4") and f.startswith("p")
    ])
    print(f"\n  Total clips ready: {len(all_clips)}/{total_pairs}")

    if len(all_clips) < total_pairs - 2:
        print(f"  Still missing too many — will continue tomorrow")
        return None

    # ── Assembly ──────────────────────────────────────────────────────────
    print("\n  Assembling video...")

    # Hide metadata.json so assembler doesn't add its own opening card
    meta = os.path.join(outdir, "metadata.json")
    meta_bak = meta + ".resume_bak"
    os.rename(meta, meta_bak)

    from video_assembler import assemble_video
    final_path = assemble_video(
        outdir, lang="zh", wiki_clips=[], fmt="long",
        info_cards=None, direct_cut_paths=all_clips,
    )
    os.rename(meta_bak, meta)

    if not final_path:
        print("  ❌ Assembly failed")
        return None

    # ── Add intro ─────────────────────────────────────────────────────────
    print("  Adding AL 說故事 intro...")
    with open(meta, "r", encoding="utf-8") as f:
        zh = json.load(f).get("zh", {})

    # Get topic from metadata
    topic = zh.get("description", "")
    # Try to find the original topic from the script
    from generate_books import (
        _generate_intro_segment, _prepend_intro_to_video,
        _parse_book_from_topic,
    )

    # Reconstruct topic from metadata
    with open(os.path.join(outdir, "metadata.json"), "r", encoding="utf-8") as f:
        full_meta = json.load(f)
    # The topic might be stored — check channel field or title
    title = zh.get("title", "")

    # Use topic from seed bank if available in metadata
    intro_path = _generate_intro_segment(
        title, outdir,
        voice="zh-TW-HsiaoChenNeural", rate="-3%", pitch="+0Hz",
    )

    if intro_path:
        combined = os.path.join(outdir, "final_zh_with_intro.mp4")
        if _prepend_intro_to_video(intro_path, final_path, combined):
            os.remove(final_path)
            os.rename(combined, final_path)
            print("  ✅ Intro added")
        if os.path.exists(intro_path):
            os.remove(intro_path)

    size_mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"\n  ✅ Complete: {final_path} ({size_mb:.1f} MB)")

    # Telegram
    try:
        from telegram_notify import _send_raw
        _send_raw(
            f"📚 [Books 續跑完成！]\n"
            f"題材: {os.path.basename(outdir)}\n"
            f"大小: {size_mb:.1f} MB\n"
            f"插圖: {len(all_clips)}/{total_pairs}"
        )
    except Exception:
        pass

    # Open on desktop
    subprocess.Popen(["open", final_path])
    return final_path


def main():
    parser = argparse.ArgumentParser(description="Resume incomplete books render")
    parser.add_argument("--dir", type=str, help="Specific output dir to resume")
    args = parser.parse_args()

    if args.dir:
        dirs = [args.dir] if os.path.isdir(args.dir) else []
    else:
        dirs = find_incomplete_books_dirs()

    if not dirs:
        print("No incomplete books renders found.")
        return

    print(f"Found {len(dirs)} incomplete render(s):")
    for d in dirs:
        illust = os.path.join(d, "illustrations")
        n = len(os.listdir(illust)) if os.path.exists(illust) else 0
        print(f"  • {os.path.basename(d)} — {n} illustrations so far")

    # Resume the oldest incomplete one
    result = resume_render(dirs[0])
    if result:
        print(f"\n🎉 Done: {result}")
    else:
        print(f"\nPaused — will continue next run")


if __name__ == "__main__":
    main()
