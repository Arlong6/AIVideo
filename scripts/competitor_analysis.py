"""
Competitor channel scraper + Gemini pattern analyzer.

Phase 2 of video_quality_upgrade plan. Scrapes 3 channels, asks Gemini what
patterns separate winners from losers, writes markdown report.

Usage:
  cd /Users/arlong/Projects/AIvideo
  python3 scripts/competitor_analysis.py

Reads OAuth creds from youtube_token.pickle (existing). Quota cost ~300 units.

NOTE: 老高與小茉 / 圖文不符 / 上班不要看 are mystery/general entertainment, not
pure crime channels. Pattern transfer to crime is partial — the report calls
out which patterns likely generalize and which are channel-specific.
"""
import json
import os
import pickle
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Path setup so we can import from project root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import GEMINI_API_KEY  # noqa: E402

CHANNELS_TO_ANALYZE = [
    "老高與小茉 Old Gao",
    "圖文不符",
    "上班不要看 NSFW",
]

VIDEOS_PER_CHANNEL = 30
TODAY = datetime.now().strftime("%Y-%m-%d")
RAW_JSON = ROOT / "data" / f"competitor_raw_{TODAY}.json"
REPORT_MD = ROOT / "data" / f"competitor_analysis_{TODAY}.md"


# ── YouTube Data API ──────────────────────────────────────────────────────────

def _yt_client():
    with open(ROOT / "youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    return build("youtube", "v3", credentials=creds)


def _resolve_channel_id(yt, query: str) -> dict | None:
    """Search for channel by name. Return {id, title} of best match."""
    resp = yt.search().list(
        part="snippet",
        q=query,
        type="channel",
        maxResults=3,
        regionCode="TW",
    ).execute()
    items = resp.get("items", [])
    if not items:
        return None
    # Take first (highest rank for the query)
    top = items[0]
    return {
        "id": top["id"]["channelId"],
        "title": top["snippet"]["title"],
        "query": query,
    }


def _get_uploads_playlist(yt, channel_id: str) -> tuple[str, dict]:
    """Return (uploads_playlist_id, channel_stats)."""
    resp = yt.channels().list(
        part="snippet,contentDetails,statistics",
        id=channel_id,
    ).execute()
    item = resp["items"][0]
    return (
        item["contentDetails"]["relatedPlaylists"]["uploads"],
        {
            "subscriberCount": int(item["statistics"].get("subscriberCount", 0)),
            "videoCount": int(item["statistics"].get("videoCount", 0)),
            "viewCount": int(item["statistics"].get("viewCount", 0)),
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", "")[:300],
        },
    )


def _get_recent_video_ids(yt, uploads_playlist_id: str, n: int) -> list[str]:
    ids: list[str] = []
    page_token = None
    while len(ids) < n:
        resp = yt.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=min(50, n - len(ids)),
            pageToken=page_token,
        ).execute()
        for it in resp.get("items", []):
            ids.append(it["contentDetails"]["videoId"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids[:n]


def _get_video_details(yt, video_ids: list[str]) -> list[dict]:
    """Batch fetch video details (50 per call max)."""
    out = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = yt.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(batch),
        ).execute()
        for v in resp.get("items", []):
            sn = v["snippet"]
            st = v.get("statistics", {})
            cd = v.get("contentDetails", {})
            out.append({
                "id": v["id"],
                "title": sn["title"],
                "publishedAt": sn["publishedAt"],
                "description": sn.get("description", "")[:500],
                "thumbnail_url": (
                    sn.get("thumbnails", {}).get("maxres")
                    or sn.get("thumbnails", {}).get("high")
                    or sn.get("thumbnails", {}).get("default", {})
                ).get("url", ""),
                "viewCount": int(st.get("viewCount", 0)),
                "likeCount": int(st.get("likeCount", 0)),
                "commentCount": int(st.get("commentCount", 0)),
                "duration": cd.get("duration", ""),
            })
    return out


# ── Scrape ────────────────────────────────────────────────────────────────────

def scrape_all() -> dict:
    yt = _yt_client()
    payload = {"scraped_at": datetime.now(timezone.utc).isoformat(), "channels": []}

    for query in CHANNELS_TO_ANALYZE:
        print(f"\n[scrape] Resolving: {query}")
        ch = _resolve_channel_id(yt, query)
        if not ch:
            print(f"  ✗ no channel found for '{query}'")
            continue
        print(f"  → matched: {ch['title']} ({ch['id']})")

        uploads_id, stats = _get_uploads_playlist(yt, ch["id"])
        print(f"  → subs: {stats['subscriberCount']:,}  videos: {stats['videoCount']:,}")

        vids_ids = _get_recent_video_ids(yt, uploads_id, VIDEOS_PER_CHANNEL)
        print(f"  → fetching {len(vids_ids)} recent videos")

        vids = _get_video_details(yt, vids_ids)
        # Sort by view count desc to make outliers obvious
        vids.sort(key=lambda v: v["viewCount"], reverse=True)

        avg_views = sum(v["viewCount"] for v in vids) / max(1, len(vids))
        median_views = sorted(v["viewCount"] for v in vids)[len(vids) // 2]

        payload["channels"].append({
            "query": query,
            "channel_id": ch["id"],
            "channel_title": ch["title"],
            "channel_stats": stats,
            "videos": vids,
            "avg_views_recent_30": int(avg_views),
            "median_views_recent_30": int(median_views),
        })
        time.sleep(1)  # gentle on quota

    return payload


# ── Gemini analysis ───────────────────────────────────────────────────────────

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)

ANALYSIS_PROMPT = """你是 YouTube 競品分析師。我給你 3 個中文 YT 頻道的近 30 部影片資料。

⚠️ 重要 context: 這 3 個頻道是「綜合解謎/懸疑」類型,不是「真實犯罪」。
我的目標頻道是真實犯罪 (true crime),所以請特別標記:
- ✅ 哪些 pattern 可以遷移到 crime 頻道
- ⚠️ 哪些 pattern 是這幾個頻道專屬的

請輸出 markdown report,結構如下:

# 競品分析 — {today}

## TL;DR (5 行)
給我 5 個最 actionable 的洞見

## Per-Channel Snapshot
每個頻道一段:
- 訂閱/總觀看
- 近 30 部影片平均觀看 / 中位數
- Top 3 outlier (view > 平均 2x) 共同點

## Title Patterns (3-5 條)
從所有影片 title 抓共通結構,例如「數字+名詞」「問句」「驚嘆+揭秘」
每條給:
- 模式範例 (引用真實 title)
- 用此模式的影片平均觀看數 vs 不用的差距
- ✅/⚠️ 是否可遷移 crime

## Thumbnail Patterns (3-5 條)
從 thumbnail URL 推測 (你看不到圖,但可從 title + view 推測):
- 哪種 title 配高 view → 推測 thumbnail 走什麼路線
- 標 ✅/⚠️

## Description Patterns (2-3 條)
description 開頭 200 字常見什麼結構?

## Outlier 拆解
全部 90 部影片中,觀看 > 該頻道平均 3x 的影片:
- title 共同點
- 主題共同點
- 給我 1 句 "如果我要做類似題材的 crime 影片應該怎麼下標" 範例

## 給 arlong Crime 頻道的 5 條具體 action
依優先順序,每條一句話。

---
資料 (raw JSON):
{data_json}
"""


def call_gemini(prompt: str) -> str:
    resp = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 8000,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise RuntimeError(f"Gemini bad response: {json.dumps(data)[:500]}")


def build_compact_data(raw: dict) -> dict:
    """Strip raw down to what Gemini needs (avoid token bloat)."""
    out = {"channels": []}
    for ch in raw["channels"]:
        out["channels"].append({
            "channel": ch["channel_title"],
            "subs": ch["channel_stats"]["subscriberCount"],
            "avg_views_30": ch["avg_views_recent_30"],
            "median_views_30": ch["median_views_recent_30"],
            "videos": [
                {
                    "title": v["title"],
                    "views": v["viewCount"],
                    "likes": v["likeCount"],
                    "duration": v["duration"],
                    "desc_head": v["description"][:200].replace("\n", " "),
                }
                for v in ch["videos"]
            ],
        })
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 2 — Competitor Analysis")
    print("=" * 60)

    # Step 1: scrape
    try:
        raw = scrape_all()
    except HttpError as e:
        print(f"\n✗ YT API error: {e}")
        sys.exit(1)

    RAW_JSON.parent.mkdir(exist_ok=True)
    RAW_JSON.write_text(json.dumps(raw, ensure_ascii=False, indent=2))
    print(f"\n[save] raw → {RAW_JSON}")

    # Step 2: Gemini analysis
    print("\n[gemini] running pattern analysis...")
    compact = build_compact_data(raw)
    prompt = ANALYSIS_PROMPT.format(
        today=TODAY,
        data_json=json.dumps(compact, ensure_ascii=False),
    )
    report = call_gemini(prompt)

    REPORT_MD.write_text(report)
    print(f"[save] report → {REPORT_MD}")

    # Step 3: Telegram notify
    try:
        from telegram_notify import _send_raw
        summary_lines = [
            f"🔍 [AIvideo] 競品分析完成 ({TODAY})",
            f"  分析頻道: {len(raw['channels'])}",
            f"  總影片: {sum(len(c['videos']) for c in raw['channels'])}",
            f"  Report: {REPORT_MD.name}",
            "",
            "請開檔 review:",
            f"  {REPORT_MD}",
        ]
        _send_raw("\n".join(summary_lines))
        print("[telegram] notified")
    except Exception as e:
        print(f"[telegram] skipped: {e}")

    print("\n✅ done")


if __name__ == "__main__":
    main()
