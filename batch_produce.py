"""
Batch produce 10 long-form videos.
Reports progress + errors via Telegram in real-time.

Usage: python batch_produce.py [--count 10] [--upload]
"""
import sys
import os
import time
import argparse
from datetime import datetime

sys.path.insert(0, ".")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared_telegram"))

from topic_manager import pick_topic, save_today_reserved, save_used_topic
from telegram_hub import get_hub, Tag

hub = get_hub()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--upload", action="store_true", help="Auto upload after generation")
    args = parser.parse_args()

    hub.send(Tag.AIVIDEO, f"🏭 批次生產開始", fields={
        "目標": f"{args.count} 支長影片",
        "上傳": "自動" if args.upload else "不上傳（本地預覽）",
    })

    results = []
    for i in range(args.count):
        topic = pick_topic(refresh_news=(i == 0))
        save_today_reserved(topic)

        hub.quick(Tag.AIVIDEO, f"⏳ [{i+1}/{args.count}] 開始製作：{topic[:30]}…")
        print(f"\n{'='*60}")
        print(f"[{i+1}/{args.count}] {topic}")
        print(f"{'='*60}")

        start_time = time.time()
        try:
            from agents.orchestrator import produce_longform
            result = produce_longform(
                topic,
                upload=args.upload,
                slot=2,
            )

            elapsed = (time.time() - start_time) / 60
            verdict = result.get("qa_report", {}).get("verdict", "?")
            video_path = result.get("video_path", "")
            youtube_url = result.get("youtube_url", "")
            size_mb = os.path.getsize(video_path) / 1024 / 1024 if video_path and os.path.exists(video_path) else 0

            results.append({
                "index": i + 1,
                "topic": topic,
                "status": "✅",
                "verdict": verdict,
                "size_mb": size_mb,
                "minutes": elapsed,
                "youtube_url": youtube_url,
                "video_path": video_path,
            })

            hub.send(Tag.AIVIDEO, f"✅ [{i+1}/{args.count}] 完成", fields={
                "題材": topic[:30],
                "QA": verdict,
                "大小": f"{size_mb:.0f} MB",
                "耗時": f"{elapsed:.0f} 分鐘",
                "連結": youtube_url or "未上傳",
            })

            save_used_topic(topic)

        except Exception as e:
            elapsed = (time.time() - start_time) / 60
            error_msg = str(e)[:200]

            results.append({
                "index": i + 1,
                "topic": topic,
                "status": "❌",
                "error": error_msg,
                "minutes": elapsed,
            })

            hub.alert(Tag.AIVIDEO, f"❌ [{i+1}/{args.count}] 製作失敗", fields={
                "題材": topic[:30],
                "耗時": f"{elapsed:.0f} 分鐘",
            }, error=error_msg)

            print(f"\n❌ Failed: {e}")
            # Continue to next video, don't stop the batch
            continue

    # ── Final summary ──
    success = [r for r in results if r["status"] == "✅"]
    failed = [r for r in results if r["status"] == "❌"]
    total_time = sum(r.get("minutes", 0) for r in results)

    summary_lines = []
    for r in results:
        if r["status"] == "✅":
            summary_lines.append(f"✅ #{r['index']} {r['topic'][:25]}… ({r['size_mb']:.0f}MB, {r['minutes']:.0f}min)")
        else:
            summary_lines.append(f"❌ #{r['index']} {r['topic'][:25]}… ({r.get('error', '')[:30]})")

    hub.report(Tag.AIVIDEO, "🏭 批次生產完成", sections=[
        ("結果", f"成功 {len(success)}/{args.count} 支 | 失敗 {len(failed)} 支"),
        ("總耗時", f"{total_time:.0f} 分鐘 ({total_time/60:.1f} 小時)"),
        ("明細", "\n".join(summary_lines)),
    ])

    print(f"\n{'='*60}")
    print(f"🏭 Batch complete: {len(success)}/{args.count} success, {len(failed)} failed")
    print(f"   Total time: {total_time:.0f} min ({total_time/60:.1f} hrs)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
