"""
Track Shorts → Long-form upgrade performance.

Filters video_log entries where source=shorts_upgrade, classifies each as
Short or Long-form, then compares against the format-matched baseline:
  - Short upgrade entries: compared against current Shorts baseline (auto-computed)
  - Long-form upgrade entries: compared against old Long-form baseline (14)

⚠️ 2026-05-11 history note: original version compared Short views to
   Long-form baseline (apples vs oranges, inflated 52×). Fixed to compute
   per-format baseline from the same video_log.

Output: stdout table + Telegram summary.
"""
import json
import os
import pickle
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build


OLD_LONGFORM_BASELINE = 14  # Established in tasks/todo.md context line 7 (13 videos avg 14)
SHORT_THRESHOLD_SEC = 90  # YT short = ≤60s, but allow buffer for our durations


def load_shorts_upgrade_videos() -> list[dict]:
    log = json.load(open("video_log.json"))
    return [v for v in log.get("videos", []) if v.get("source") == "shorts_upgrade"]


def compute_shorts_baseline(video_log_path: str = "video_log.json") -> float:
    """Median views of channel's Shorts (apples-vs-apples baseline)."""
    with open(video_log_path) as f:
        log = json.load(f)
    short_views = []
    for v in log.get("videos", []):
        if v.get("duration_s", 999) <= SHORT_THRESHOLD_SEC and v.get("stats"):
            latest = max(v["stats"], key=lambda s: s.get("date", ""))
            short_views.append(latest.get("views", 0))
    if not short_views:
        return 50.0
    short_views.sort()
    return short_views[len(short_views) // 2]


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

    shorts_baseline = compute_shorts_baseline()
    print(f"   Old Long-form baseline: {OLD_LONGFORM_BASELINE} views")
    print(f"   Current Shorts baseline (median): {shorts_baseline:.0f} views")
    print(f"   Threshold: ≤{SHORT_THRESHOLD_SEC}s = Short, >{SHORT_THRESHOLD_SEC}s = Long-form")
    print("=" * 70)

    videos = load_shorts_upgrade_videos()
    if not videos:
        print("\n⚠️  No videos tagged source=shorts_upgrade in video_log.json")
        print("   Possible reasons:")
        print("   - Upgrade pipeline never produced a long-form yet")
        print("   - workflow_dispatch source_tag never passed (use --source on manual runs)")
        print(f"   Shorts baseline {shorts_baseline:.0f} stays as reference for future upgrades.")
        return 1

    print(f"\nFound {len(videos)} shorts_upgrade video(s):\n")
    views_map = fetch_views([v["video_id"] for v in videos])

    # Header
    print(f"  {'Date':12} {'Video ID':12} {'Fmt':>4} {'Age':>5} {'Views':>7} {'vs base':>9}  Topic")
    print(f"  {'-'*12} {'-'*12} {'-'*4} {'-'*5} {'-'*7} {'-'*9}  {'-'*40}")

    rows = []
    for v in sorted(videos, key=lambda v: v.get("uploaded_at", "")):
        vid = v["video_id"]
        views = views_map.get(vid, 0)
        age = age_days(v.get("uploaded_at", ""))
        topic = (v.get("topic") or "")[:40]
        upload_date = v.get("uploaded_at", "")[:10]
        dur = v.get("duration_s", 0)
        is_short = dur <= SHORT_THRESHOLD_SEC
        fmt = "S" if is_short else "L"
        baseline = shorts_baseline if is_short else OLD_LONGFORM_BASELINE
        boost = views / baseline if baseline > 0 else 0
        print(f"  {upload_date:12} {vid:12} {fmt:>4} {age:>4}d {views:>7} {boost:>7.1f}×  {topic}")
        rows.append({
            "video_id": vid, "topic": topic, "format": fmt,
            "age_days": age, "views": views, "boost": boost,
            "baseline_used": baseline,
        })

    # Aggregate per format
    shorts = [r for r in rows if r["format"] == "S"]
    longs = [r for r in rows if r["format"] == "L"]
    print()
    if shorts:
        avg_s = sum(r["views"] for r in shorts) / len(shorts)
        print(f"  Shorts: {len(shorts)} 部, 平均 {avg_s:.0f} views "
              f"({avg_s/shorts_baseline:.1f}× Shorts baseline {shorts_baseline:.0f})")
    if longs:
        avg_l = sum(r["views"] for r in longs) / len(longs)
        print(f"  Long-form: {len(longs)} 部, 平均 {avg_l:.0f} views "
              f"({avg_l/OLD_LONGFORM_BASELINE:.1f}× old Long-form baseline {OLD_LONGFORM_BASELINE})")
        if avg_l / OLD_LONGFORM_BASELINE >= 2:
            print(f"  ✅ Upgrade hypothesis CONFIRMED (Long-form upgrade ≥2× baseline)")
        else:
            print(f"  ⚠️  Long-form upgrade <2× baseline, hypothesis weak")
    else:
        print(f"  ⚠️  No long-form upgrade videos yet — main hypothesis NOT YET TESTED")
        print(f"  (Original 'D.B.庫柏 long-form' run 24946381573 failed 4/26, never re-tried)")

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
