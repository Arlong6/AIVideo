"""
Track Shorts → Long-form upgrade performance vs old long-form baseline.

Filters video_log entries where source=shorts_upgrade, fetches latest YT
views, and compares against the baseline (avg 14 views per old long-form,
established in tasks/todo.md context).

Output: stdout table + Telegram summary.
"""
import json
import os
import pickle
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build


BASELINE_AVG_VIEWS = 14  # Old long-form baseline (per tasks/todo.md context line 7)


def load_shorts_upgrade_videos() -> list[dict]:
    log = json.load(open("video_log.json"))
    return [v for v in log.get("videos", []) if v.get("source") == "shorts_upgrade"]


def fetch_views(video_ids: list[str]) -> dict[str, int]:
    """Batch fetch view counts via YT Data API."""
    if not video_ids:
        return {}
    with open("youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    yt = build("youtube", "v3", credentials=creds)
    out = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        resp = yt.videos().list(
            part="statistics", id=",".join(batch),
        ).execute()
        for item in resp.get("items", []):
            out[item["id"]] = int(item["statistics"].get("viewCount", 0))
    return out


def age_days(uploaded_at: str) -> int:
    try:
        up = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - up).days
    except Exception:
        return -1


def main():
    print("=" * 70)
    print("📊 Shorts → Long-form upgrade performance tracker")
    print(f"   Baseline (old long-form avg): {BASELINE_AVG_VIEWS} views")
    print("=" * 70)

    videos = load_shorts_upgrade_videos()
    if not videos:
        print("\n⚠️  No videos tagged source=shorts_upgrade in video_log.json")
        print("   Did the upgrade pipeline run? Or is the source_tag broken?")
        return 1

    print(f"\nFound {len(videos)} shorts_upgrade video(s):\n")
    views_map = fetch_views([v["video_id"] for v in videos])

    # Header
    print(f"  {'Date':12} {'Video ID':12} {'Age':>5} {'Views':>7} {'vs base':>9}  Topic")
    print(f"  {'-'*12} {'-'*12} {'-'*5} {'-'*7} {'-'*9}  {'-'*40}")

    total_views = 0
    rows = []
    for v in sorted(videos, key=lambda v: v.get("uploaded_at", "")):
        vid = v["video_id"]
        views = views_map.get(vid, 0)
        age = age_days(v.get("uploaded_at", ""))
        topic = (v.get("topic") or "")[:40]
        upload_date = v.get("uploaded_at", "")[:10]
        boost = views / BASELINE_AVG_VIEWS if BASELINE_AVG_VIEWS > 0 else 0
        print(f"  {upload_date:12} {vid:12} {age:>4}d {views:>7} {boost:>7.1f}×  {topic}")
        total_views += views
        rows.append({
            "video_id": vid,
            "topic": topic,
            "age_days": age,
            "views": views,
            "boost": boost,
        })

    n = len(videos)
    avg = total_views / n if n else 0
    avg_boost = avg / BASELINE_AVG_VIEWS if BASELINE_AVG_VIEWS > 0 else 0

    print(f"\n  Total: {n} video(s) / {total_views} views")
    print(f"  Avg: {avg:.0f} views ({avg_boost:.1f}× baseline)")
    print(f"  {'✅ Upgrade hypothesis CONFIRMED' if avg_boost >= 2 else '⚠️  No clear lift vs baseline'}")

    # Telegram summary
    try:
        from telegram_notify import _send_raw
        msg = (
            f"📊 <b>Shorts→Long-form Upgrade Track</b>\n\n"
            f"Baseline: {BASELINE_AVG_VIEWS} views\n"
            f"Upgraded: {n} 部 / 平均 {avg:.0f} views ({avg_boost:.1f}×)\n\n"
        )
        for r in rows[:5]:
            msg += f"• {r['topic'][:30]} — {r['views']} views ({r['boost']:.1f}×, {r['age_days']}d)\n"
        if avg_boost >= 2:
            msg += "\n✅ 假設成立 (≥2× baseline)"
        else:
            msg += "\n⚠️ 沒明顯提升 (<2×), 重新評估"
        _send_raw(msg)
        print("\n✓ Telegram 已通知")
    except Exception as e:
        print(f"\n  Telegram failed (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
