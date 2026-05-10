"""
6/10 戰略檢核 — 對 STRATEGY_2026Q2.md 30 天 KPI 做自動判讀.
Runs weekly_title_review + 抓頻道訂閱 + 比對劇本 A/B/C 觸發條件.

劇本判讀:
  🟢 A 反彈: 平均 ≥ 150 / Top 1 ≥ 800 / 訂閱 增 200+
  🟡 B 持平: 平均 80-150 / Top 1 400-800 / 訂閱 50-100
  🔴 C 沒救: 平均 < 80 / Top 1 < 400 / 訂閱停滯
"""
import json
import os
import pickle
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build


def get_channel_stats():
    with open("youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="statistics,snippet", mine=True).execute()
    if not ch.get("items"):
        return None
    s = ch["items"][0]["statistics"]
    return {
        "subscribers": int(s.get("subscriberCount", 0)),
        "views": int(s.get("viewCount", 0)),
        "videos": int(s.get("videoCount", 0)),
    }


def fetch_recent_views(days: int = 7) -> dict:
    """抓過去 N 天上傳影片觀看數."""
    import re
    from datetime import datetime, timedelta, timezone
    with open("youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    yt = build("youtube", "v3", credentials=creds)

    log = json.load(open("video_log.json"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_ids = []
    for v in log.get("videos", []):
        try:
            up = datetime.fromisoformat(v.get("uploaded_at", "").replace("Z", "+00:00"))
            if up >= cutoff and v.get("video_id"):
                recent_ids.append(v["video_id"])
        except: pass

    views = []
    for i in range(0, len(recent_ids), 50):
        batch = recent_ids[i:i+50]
        resp = yt.videos().list(part="statistics", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            views.append(int(item["statistics"].get("viewCount", 0)))

    if not views:
        return {"n": 0, "mean": 0, "median": 0, "top1": 0}
    views.sort()
    return {
        "n": len(views),
        "mean": sum(views) // len(views),
        "median": views[len(views) // 2],
        "top1": views[-1] if views else 0,
        "total": sum(views),
    }


def judge_scenario(stats: dict, prev_subs: int = 0) -> dict:
    """根據 KPI 判讀劇本."""
    mean = stats.get("mean", 0)
    top1 = stats.get("top1", 0)

    if mean >= 150 and top1 >= 800:
        return {
            "scenario": "A",
            "label": "🟢 反彈",
            "verdict": "繼續 Phase 2-3 (真人配音 / B-roll / Series 深耕)",
        }
    elif mean >= 80 and top1 >= 400:
        return {
            "scenario": "B",
            "label": "🟡 持平",
            "verdict": "單點突破: 1) 真人配音 ($22/月) 2) Trending 案件 3) 主持人 IP",
        }
    else:
        return {
            "scenario": "C",
            "label": "🔴 沒救",
            "verdict": ("Pivot 選項: A) 動物頻道 ViewMax.io / "
                        "B) 1 部/週深耕 / C) Kill switch — 把時間轉回 LTC primary"),
        }


def main():
    print("=" * 60)
    print("📊 AIvideo 戰略檢核 (STRATEGY_2026Q2.md 30 天 KPI)")
    print("=" * 60)

    print("\n[1/3] 抓頻道訂閱數...")
    ch = get_channel_stats()
    if ch:
        print(f"  訂閱: {ch['subscribers']:,}")
        print(f"  總觀看: {ch['views']:,}")
        print(f"  影片數: {ch['videos']}")
    else:
        print("  ❌ 無法取得頻道資料")

    print("\n[2/3] 抓過去 7 天觀看...")
    recent = fetch_recent_views(days=7)
    print(f"  影片數: {recent['n']}")
    print(f"  平均: {recent['mean']}")
    print(f"  中位數: {recent['median']}")
    print(f"  Top 1: {recent['top1']}")

    print("\n[3/3] 劇本判讀...")
    judgment = judge_scenario(recent)
    print(f"  {judgment['label']} (劇本 {judgment['scenario']})")
    print(f"  ➡️  {judgment['verdict']}")

    # Telegram alert
    try:
        from telegram_notify import _send_raw
        msg = (
            f"📊 <b>AIvideo 6/10 戰略檢核</b>\n\n"
            f"訂閱: {ch['subscribers'] if ch else '?'}\n"
            f"7天平均: {recent['mean']}\n"
            f"7天 Top 1: {recent['top1']}\n\n"
            f"判讀: {judgment['label']} (劇本 {judgment['scenario']})\n"
            f"行動: {judgment['verdict']}"
        )
        _send_raw(msg)
        print("\n✓ Telegram 已通知")
    except Exception as e:
        print(f"  Telegram 失敗: {e}")


if __name__ == "__main__":
    main()
