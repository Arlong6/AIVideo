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


def check_copyright_issues(youtube):
    """Scan all tracked videos for copyright blocks or restrictions."""
    from telegram_notify import notify_copyright

    data = _load_log()
    if not data["videos"]:
        return

    video_ids = [v["video_id"] for v in data["videos"]]

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        try:
            resp = youtube.videos().list(
                part="status,contentDetails,snippet",
                id=",".join(batch),
            ).execute()
        except Exception as e:
            print(f"  [WARN] Copyright check failed: {e}")
            continue

        for item in resp.get("items", []):
            vid_id = item["id"]
            title = item["snippet"]["title"][:40]
            status = item.get("status", {})
            content = item.get("contentDetails", {})

            issues = []

            # Check upload status
            rejection = status.get("rejectionReason", "")
            if rejection:
                issues.append(f"影片被拒絕: {rejection}")

            # Check region blocks
            block = content.get("regionRestriction", {})
            blocked = block.get("blocked", [])
            if "TW" in blocked or len(blocked) > 100:
                issues.append(f"被封鎖在 {len(blocked)} 個國家（包含台灣）")

            # Check content claims
            upload_status = status.get("uploadStatus", "")
            if upload_status == "rejected":
                issues.append(f"上傳被拒: {status.get('failureReason', '未知')}")

            # Check privacy (might have been forced to private)
            privacy = status.get("privacyStatus", "")
            if privacy == "private":
                # Check if it was supposed to be public
                video_data = next((v for v in data["videos"] if v["video_id"] == vid_id), None)
                if video_data and "public" in str(video_data.get("publish_at", "")):
                    issues.append("影片被設為私人（可能被 YouTube 強制下架）")

            if issues:
                for issue in issues:
                    notify_copyright(vid_id, title, issue)
                print(f"  ⚠️ {title}: {'; '.join(issues)}")

    print(f"  📊 Copyright check done for {len(video_ids)} videos")


# ── Telegram daily report ──────────────────────────────────────────────────────

def fetch_channel_stats(youtube) -> dict:
    """Fetch channel subscriber count and total views."""
    try:
        resp = youtube.channels().list(part="statistics", mine=True).execute()
        if resp.get("items"):
            stats = resp["items"][0]["statistics"]
            return {
                "subscribers": int(stats.get("subscriberCount", 0)),
                "total_views": int(stats.get("viewCount", 0)),
                "total_videos": int(stats.get("videoCount", 0)),
            }
    except Exception as e:
        print(f"  [WARN] Channel stats fetch failed: {e}")
    return {}


def send_daily_report(youtube=None):
    """Send Telegram summary: channel stats + video performance."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared_telegram"))
    try:
        from telegram_hub import get_hub, Tag
        hub = get_hub()
    except ImportError:
        hub = None

    data = _load_log()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── Channel stats ──
    channel = {}
    if youtube:
        channel = fetch_channel_stats(youtube)

    # ── Today's upload check ──
    today_videos = [v for v in data["videos"] if v["uploaded_at"][:10] == today]
    target = 3
    count = len(today_videos)
    if count >= target:
        upload_line = f"✅ 今日上傳：{count}/{target} 支"
    else:
        upload_line = f"⚠️ 今日上傳：{count}/{target} 支（差 {target - count} 支）"

    # ── Build sections ──
    sections = []

    # Channel overview
    if channel:
        sections.append(("📺 頻道狀態", (
            f"訂閱：{channel.get('subscribers', 0):,} 人\n"
            f"總觀看：{channel.get('total_views', 0):,} 次\n"
            f"影片數：{channel.get('total_videos', 0)} 支"
        )))

    # Upload status
    sections.append(("📤 上傳", upload_line))

    # Today's videos
    if today_videos:
        vid_lines = []
        for v in sorted(today_videos, key=lambda x: x["slot"]):
            slot_label = {1: "🌅10AM", 2: "🌆2PM", 3: "🌆6PM"}.get(v["slot"], "📹")
            topic_short = v["topic"][:28] + "…" if len(v["topic"]) > 28 else v["topic"]
            vid_lines.append(f"{slot_label} {topic_short}\nhttps://youtu.be/{v['video_id']}")
        sections.append(("🎬 今日影片", "\n".join(vid_lines)))

    # Recent video performance
    all_videos = sorted(data["videos"], key=lambda v: v["uploaded_at"], reverse=True)
    past_videos = [v for v in all_videos if v["uploaded_at"][:10] != today][:8]
    if past_videos:
        perf_lines = []
        total_today_views = 0
        for v in past_videos:
            latest = v["stats"][-1] if v["stats"] else None
            views = latest["views"] if latest else 0
            likes = latest["likes"] if latest else 0
            total_today_views += views if isinstance(views, int) else 0
            topic_short = v["topic"][:20] + "…" if len(v["topic"]) > 20 else v["topic"]
            perf_lines.append(f"👁{views} ❤️{likes}  {topic_short}")
        sections.append(("📊 近期表現", "\n".join(perf_lines)))

    # Trend
    if len(all_videos) >= 6:
        recent_views = sum(
            (v["stats"][-1]["views"] if v["stats"] else 0) for v in all_videos[:5])
        older_views = sum(
            (v["stats"][-1]["views"] if v["stats"] else 0) for v in all_videos[5:10])
        if older_views > 0:
            trend = ((recent_views - older_views) / older_views) * 100
            arrow = "📈" if trend > 0 else "📉"
            sections.append(("趨勢", f"{arrow} {trend:+.1f}%"))

    # Send via hub
    if hub:
        hub.report(Tag.AIVIDEO, "頻道日報", sections=sections)
    else:
        # Fallback
        import requests as req
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if bot_token and chat_id:
            msg = "\n".join(f"{t}: {b}" for t, b in sections)
            req.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                     json={"chat_id": chat_id, "text": msg}, timeout=10)

    print("  📊 Daily report sent to Telegram")
