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


def log_video(video_id: str, topic: str, slot: int, duration_s: float,
              publish_at: str = "", source: str = "", series_tag: str = "",
              title: str = ""):
    """Record a newly uploaded video.

    source: optional tag like "shorts_upgrade" to track origin (manual vs
    automated, regenerated from a top-performing Short, etc.)
    series_tag: optional tag for series ("wrongful_conviction", "campus", etc.)
    title: the published YouTube title — feeds the title fatigue guard
    (title_dna.get_title_prompt_insert reads it back at generation time).
    """
    data = _load_log()
    if any(v["video_id"] == video_id for v in data["videos"]):
        return
    entry = {
        "video_id": video_id,
        "topic": topic,
        "slot": slot,
        "duration_s": round(duration_s),
        "publish_at": publish_at,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "stats": [],
    }
    if title:
        entry["title"] = title
    if source:
        entry["source"] = source
    if series_tag:
        entry["series_tag"] = series_tag
    data["videos"].append(entry)
    _save_log(data)
    print(f"  📊 Logged video {video_id}"
          + (f" [source={source}]" if source else "")
          + (f" [series={series_tag}]" if series_tag else ""))


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


# ── Audience retention (manual YT Studio CSV ingestion) ─────────────────────────
# The Analytics API is blocked (not enabled + lost OAuth on AL_Story), so the
# retention learning loop ships as a MANUAL slice: export the "Audience retention"
# CSV from YT Studio, run this, and the worst drop-off lands in video_log.json +
# a Telegram alert. Keeps the operator in the loop (no auto prompt-mutation on n=1).

def _mmss(seconds: float) -> str:
    s = max(0, int(round(seconds)))
    return f"{s // 60}:{s % 60:02d}"


def parse_retention_csv(csv_path: str, duration_s: float = 0.0) -> dict:
    """Parse a YouTube Studio audience-retention CSV into a retention summary.

    Tolerant to EN/ZH column naming: needs a position column (% or seconds) and a
    retention column (absolute preferred, else relative/any %).
    """
    import csv as _csv
    rows = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = _csv.reader(f)
        header = next(reader, [])

        def _find(keys):
            for i, h in enumerate(header):
                hl = h.strip().lower()
                if any(k.lower() in hl for k in keys):
                    return i
            return -1

        pos_i = _find(["position", "elapsed", "time", "位置", "時間"])
        ret_i = _find(["absolute", "絕對"])
        if ret_i < 0:
            ret_i = _find(["relative", "相對"])
        if ret_i < 0:
            ret_i = _find(["retention", "watched", "續看", "比率", "%"])
        if pos_i < 0 or ret_i < 0:
            raise ValueError(f"無法辨識 retention CSV 欄位 (header={header})")
        for r in reader:
            if len(r) <= max(pos_i, ret_i):
                continue
            try:
                pos = float(str(r[pos_i]).replace("%", "").strip())
                ret = float(str(r[ret_i]).replace("%", "").strip())
            except ValueError:
                continue
            rows.append((pos, ret))

    if len(rows) < 2:
        raise ValueError("retention CSV 資料點不足")

    max_pos = max(p for p, _ in rows)
    if max_pos <= 1.5:                              # position is a 0-1 fraction
        rows = [(p * 100.0, r) for p, r in rows]
    elif duration_s and max_pos > 100.5:           # position is in seconds
        rows = [(p / duration_s * 100.0, r) for p, r in rows]
    if max(r for _, r in rows) <= 1.5:             # retention is a 0-1 fraction
        rows = [(p, r * 100.0) for p, r in rows]

    worst_delta, worst_at = 0.0, rows[0][0]
    for (p0, r0), (p1, r1) in zip(rows, rows[1:]):
        if (r1 - r0) < worst_delta:
            worst_delta, worst_at = (r1 - r0), p1
    worst_sec = (worst_at / 100.0) * duration_s if duration_s else 0.0
    return {
        "points": len(rows),
        "curve": [[round(p, 1), round(r, 1)] for p, r in rows],
        "worst_drop_pct": round(worst_delta, 1),
        "worst_drop_at_pct": round(worst_at, 1),
        "worst_drop_at_mmss": _mmss(worst_sec) if duration_s else "",
        "start_retention": round(rows[0][1], 1),
        "end_retention": round(rows[-1][1], 1),
    }


def ingest_retention_csv(video_id: str, csv_path: str, notify: bool = True) -> dict | None:
    """Parse a retention CSV, store the summary on the video_log entry, alert TG."""
    data = _load_log()
    entry = next((v for v in data["videos"] if v["video_id"] == video_id), None)
    if entry is None:
        print(f"  [retention] video_id {video_id} 不在 video_log 中")
        return None
    summary = parse_retention_csv(csv_path, float(entry.get("duration_s", 0) or 0))
    entry["retention"] = summary
    _save_log(data)
    where = summary["worst_drop_at_mmss"] or f"{summary['worst_drop_at_pct']}%"
    print(f"  📉 retention: 開頭 {summary['start_retention']}% → 結尾 "
          f"{summary['end_retention']}%, 最大流失 {summary['worst_drop_pct']}% @ {where}")
    if notify:
        try:
            from telegram_notify import _send_raw
            _send_raw(
                f"📉 <b>留存分析</b> {entry.get('topic','')[:30]}\n"
                f"開頭 {summary['start_retention']}% → 結尾 {summary['end_retention']}%\n"
                f"最大流失點: {where} ({summary['worst_drop_pct']}%)\n"
                f"→ 檢視該段腳本/視覺是否該調整")
        except Exception as e:
            print(f"  [retention] Telegram alert failed: {e}")
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Ingest a YT Studio audience-retention CSV")
    ap.add_argument("video_id")
    ap.add_argument("csv_path")
    ap.add_argument("--no-notify", action="store_true")
    _a = ap.parse_args()
    ingest_retention_csv(_a.video_id, _a.csv_path, notify=not _a.no_notify)
