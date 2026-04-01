"""
Phase 1: Video performance tracking.

- log_video(): called after each upload, saves to video_log.json
- fetch_and_update_stats(): fetches view counts via YouTube Data API
- send_daily_report(): posts Telegram summary of recent performance
"""

import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

VIDEO_LOG_FILE = "video_log.json"


# ── Log management ─────────────────────────────────────────────────────────────

def _load_log() -> dict:
    if not os.path.exists(VIDEO_LOG_FILE):
        return {"videos": []}
    with open(VIDEO_LOG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_log(data: dict):
    with open(VIDEO_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_video(video_id: str, topic: str, slot: int, duration_s: float, publish_at: str = ""):
    """Record a newly uploaded video."""
    data = _load_log()
    # Avoid duplicate entries
    if any(v["video_id"] == video_id for v in data["videos"]):
        return
    data["videos"].append({
        "video_id": video_id,
        "topic": topic,
        "slot": slot,
        "duration_s": round(duration_s),
        "publish_at": publish_at,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "stats": [],
    })
    _save_log(data)
    print(f"  📊 Logged video {video_id} to analytics tracker")


# ── Stats fetching ─────────────────────────────────────────────────────────────

def fetch_and_update_stats(youtube):
    """Fetch latest view counts for all tracked videos via YouTube Data API."""
    data = _load_log()
    if not data["videos"]:
        return

    video_ids = [v["video_id"] for v in data["videos"]]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Batch request (max 50 per call)
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = youtube.videos().list(
                part="statistics,contentDetails",
                id=",".join(batch),
            ).execute()
        except Exception as e:
            print(f"  [WARN] Analytics fetch failed: {e}")
            continue

        stats_map = {}
        for item in resp.get("items", []):
            vid = item["id"]
            s = item.get("statistics", {})
            stats_map[vid] = {
                "date": today,
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
            }

        for video in data["videos"]:
            if video["video_id"] in stats_map:
                new_stat = stats_map[video["video_id"]]
                # Update today's entry if exists, otherwise append
                existing = next((s for s in video["stats"] if s["date"] == today), None)
                if existing:
                    existing.update(new_stat)
                else:
                    video["stats"].append(new_stat)

    _save_log(data)
    print(f"  📊 Updated stats for {len(video_ids)} videos")


# ── Telegram daily report ──────────────────────────────────────────────────────

def send_daily_report():
    """Send Telegram summary of recent video performance."""
    import requests as req

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return

    data = _load_log()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Today's upload check ──
    today_videos = [
        v for v in data["videos"]
        if v["uploaded_at"][:10] == today
    ]
    target = 3  # 2 Shorts + 1 long-form per day
    count = len(today_videos)
    if count >= target:
        upload_status = f"✅ 今日上傳：{count}/{target} 支"
    else:
        upload_status = f"⚠️ 今日上傳：{count}/{target} 支（差 {target - count} 支）"

    lines = [f"📊 *頻道表現日報*\n{upload_status}\n"]

    # Today's videos detail
    if today_videos:
        lines.append("*今日影片：*")
        for v in sorted(today_videos, key=lambda x: x["slot"]):
            slot_label = "🌅10AM" if v["slot"] == 1 else "🌆6PM"
            topic_short = v["topic"][:28] + "…" if len(v["topic"]) > 28 else v["topic"]
            vid_url = f"https://youtu.be/{v['video_id']}"
            lines.append(f"{slot_label} {topic_short}\n  🔗 {vid_url}")
        lines.append("")

    # Recent performance (last 10 excluding today)
    all_videos = sorted(data["videos"], key=lambda v: v["uploaded_at"], reverse=True)
    past_videos = [v for v in all_videos if v["uploaded_at"][:10] != today][:8]

    if past_videos:
        lines.append("*近期表現：*")
        for v in past_videos:
            latest = v["stats"][-1] if v["stats"] else None
            views = latest["views"] if latest else "—"
            likes = latest["likes"] if latest else "—"
            topic_short = v["topic"][:22] + "…" if len(v["topic"]) > 22 else v["topic"]
            slot_label = "🌅" if v["slot"] == 1 else "🌆"
            lines.append(f"{slot_label} {topic_short}  👁{views} ❤️{likes}")

    # Simple trend: compare latest 5 vs previous 5
    if len(all_videos) >= 6:
        recent_views = sum(
            (v["stats"][-1]["views"] if v["stats"] else 0)
            for v in all_videos[:5]
        )
        older_views = sum(
            (v["stats"][-1]["views"] if v["stats"] else 0)
            for v in all_videos[5:10]
        )
        if older_views > 0:
            trend = ((recent_views - older_views) / older_views) * 100
            arrow = "📈" if trend > 0 else "📉"
            lines.append(f"\n{arrow} 近期趨勢：{trend:+.1f}%")

    msg = "\n".join(lines)
    try:
        req.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
        print("  📊 Daily report sent to Telegram")
    except Exception as e:
        print(f"  [WARN] Daily report failed: {e}")
