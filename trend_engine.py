"""
Trend Engine — YouTube search trends, competitor analysis, batch title generation.

Three-stage pipeline:
1. Scrape YouTube autocomplete for real-time search demand
2. Scan competitor channels for outlier videos (views > 3x median)
3. Feed everything into Gemini to generate 30 data-driven titles

Usage:
    python trend_engine.py
"""

import json
import os
import pickle
import re
import statistics
import time
import urllib.parse
from datetime import datetime

import requests
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from config import GEMINI_API_KEY
from title_dna import TITLE_PATTERNS, POWER_WORDS, get_title_prompt_insert

try:
    from pytrends.request import TrendReq
    _pytrends_available = True
except ImportError:
    _pytrends_available = False

# ── Constants ─────────────────────────────────────────────────────────────────

TOKEN_FILE = "youtube_token.pickle"

# Default autocomplete queries (Chinese true crime)
DEFAULT_QUERIES = [
    "台灣 犯罪", "台灣 懸案", "真實犯罪", "連環殺手", "未解之謎",
    "日本 犯罪", "韓國 犯罪", "殺人案", "謀殺案",
]

# Competitor channel IDs (Chinese true crime YouTubers)
DEFAULT_COMPETITOR_CHANNELS = {
    "腦洞烏托邦": "UCLa4dkbjkGnSMIlCW4ytOyg",
    "老高與小茉": "UCMUnInmOkrWN4gof9KlhNmQ",
    "曉涵哥來了": "UCnqnEBzurVpBQgFjWqsDK_A",
}

AUTOCOMPLETE_URL = "https://suggestqueries-clients6.youtube.com/complete/search"


# ── Gemini client ─────────────────────────────────────────────────────────────

_gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass


# ── Google Trends ────────────────────────────────────────────────────────────

DEFAULT_CRIME_QUERIES = [
    "台灣犯罪", "殺人案", "懸案", "連環殺手", "真實犯罪",
    "失蹤案", "謀殺", "詐騙集團", "綁架案",
]


def get_google_trends(queries: list[str] | None = None,
                      geo: str = "TW",
                      timeframe: str = "now 7-d") -> dict:
    """
    Fetch Google Trends data for crime-related queries in Taiwan.

    Uses pytrends to get:
    - Interest over time for each query
    - Rising and top related queries

    Args:
        queries: List of search terms (defaults to crime-related terms)
        geo: Region code (default "TW" for Taiwan)
        timeframe: Trends timeframe (default last 7 days)

    Returns:
        {
            "rising_queries": [str, ...],
            "top_queries": [str, ...],
            "interest_scores": {query: avg_score, ...},
        }
    """
    if not _pytrends_available:
        print("  [ERROR] pytrends not installed. Run: pip install pytrends")
        return {"rising_queries": [], "top_queries": [], "interest_scores": {}}

    if queries is None:
        queries = DEFAULT_CRIME_QUERIES

    pytrends = TrendReq(hl="zh-TW", tz=480)  # UTC+8 for Taiwan

    rising_queries = []
    top_queries = []
    interest_scores = {}
    seen = set()

    # pytrends only allows 5 keywords per request
    for batch_start in range(0, len(queries), 5):
        batch = queries[batch_start:batch_start + 5]

        try:
            pytrends.build_payload(batch, cat=0, timeframe=timeframe, geo=geo)

            # Interest over time — average score per query
            try:
                iot = pytrends.interest_over_time()
                if iot is not None and not iot.empty:
                    for q in batch:
                        if q in iot.columns:
                            avg = float(iot[q].mean())
                            interest_scores[q] = round(avg, 1)
            except Exception:
                pass

            # Related queries (rising + top)
            try:
                related = pytrends.related_queries()
                for q in batch:
                    if q not in related:
                        continue

                    rising_df = related[q].get("rising")
                    if rising_df is not None and not rising_df.empty:
                        for _, row in rising_df.iterrows():
                            term = row.get("query", "")
                            if term and term not in seen:
                                seen.add(term)
                                rising_queries.append(term)

                    top_df = related[q].get("top")
                    if top_df is not None and not top_df.empty:
                        for _, row in top_df.iterrows():
                            term = row.get("query", "")
                            if term and term not in seen:
                                seen.add(term)
                                top_queries.append(term)
            except Exception:
                pass

            time.sleep(1)  # rate limit

        except Exception as e:
            print(f"  [WARN] Google Trends batch failed for {batch}: {e}")
            time.sleep(2)

    print(f"  Google Trends: {len(rising_queries)} rising, "
          f"{len(top_queries)} top queries, "
          f"{len(interest_scores)} scored terms")

    return {
        "rising_queries": rising_queries,
        "top_queries": top_queries,
        "interest_scores": interest_scores,
    }


# ── YouTube OAuth helper ──────────────────────────────────────────────────────

def _get_youtube_service():
    """Build YouTube Data API service using OAuth token."""
    if not os.path.exists(TOKEN_FILE):
        print(f"  [ERROR] {TOKEN_FILE} not found. Run youtube_uploader.py first to authenticate.")
        return None

    with open(TOKEN_FILE, "rb") as f:
        creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(TOKEN_FILE, "wb") as f:
                    pickle.dump(creds, f)
            except Exception as e:
                print(f"  [ERROR] Failed to refresh YouTube credentials: {e}")
                return None
        else:
            print("  [ERROR] YouTube credentials invalid. Re-run youtube_uploader.py to re-authenticate.")
            return None

    return build("youtube", "v3", credentials=creds)


# ── Feature 1: YouTube Search Autocomplete ────────────────────────────────────

def get_youtube_suggestions(queries: list[str] | None = None) -> list[str]:
    """
    Scrape YouTube autocomplete for trending search terms.

    Hits the public suggest endpoint (no API key needed) for each query
    and collects all unique suggestions.
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    all_suggestions = []
    seen = set()

    for query in queries:
        try:
            params = {
                "client": "youtube",
                "ds": "yt",
                "q": query,
            }
            resp = requests.get(
                AUTOCOMPLETE_URL,
                params=params,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()

            # Response is JSONP: window.google.ac.h( [...] )
            # Extract the JSON array from inside the parentheses
            text = resp.text
            match = re.search(r"\((.+)\)\s*$", text, re.DOTALL)
            if not match:
                continue

            data = json.loads(match.group(1))
            # data[1] contains the suggestion arrays: [[suggestion, ...], ...]
            if isinstance(data, list) and len(data) > 1:
                for item in data[1]:
                    if isinstance(item, list) and len(item) > 0:
                        suggestion = item[0]
                        if isinstance(suggestion, str) and suggestion not in seen:
                            seen.add(suggestion)
                            all_suggestions.append(suggestion)

            # Be polite — small delay between requests
            time.sleep(0.3)

        except Exception as e:
            print(f"  [WARN] Autocomplete failed for '{query}': {e}")

    print(f"  Autocomplete: found {len(all_suggestions)} unique suggestions from {len(queries)} queries")
    return all_suggestions


# ── Feature 2: Competitor Channel Scanner ─────────────────────────────────────

def _get_channel_uploads_playlist(youtube, channel_id: str) -> str | None:
    """Get the 'uploads' playlist ID for a channel."""
    try:
        resp = youtube.channels().list(
            part="contentDetails",
            id=channel_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            return None
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"  [WARN] Failed to get uploads playlist for {channel_id}: {e}")
        return None


def _get_recent_videos(youtube, playlist_id: str, max_results: int = 50) -> list[str]:
    """Get video IDs from an uploads playlist."""
    video_ids = []
    try:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=playlist_id,
            maxResults=min(max_results, 50),
        ).execute()

        for item in resp.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])
    except Exception as e:
        print(f"  [WARN] Failed to list playlist {playlist_id}: {e}")

    return video_ids


def _get_video_stats(youtube, video_ids: list[str]) -> list[dict]:
    """Fetch title, view count, and publish date for a batch of videos."""
    videos = []
    # YouTube API allows up to 50 IDs per request
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        try:
            resp = youtube.videos().list(
                part="snippet,statistics",
                id=",".join(batch),
            ).execute()

            for item in resp.get("items", []):
                stats = item.get("statistics", {})
                view_count = int(stats.get("viewCount", 0))
                videos.append({
                    "video_id": item["id"],
                    "title": item["snippet"]["title"],
                    "views": view_count,
                    "published_at": item["snippet"]["publishedAt"],
                    "url": f"https://youtu.be/{item['id']}",
                })
        except Exception as e:
            print(f"  [WARN] Failed to fetch video stats: {e}")

    return videos


def scan_competitor_channels(channel_ids: list[str] | None = None) -> dict:
    """
    Scan competitor channels, find outlier videos, extract title patterns.

    An outlier is any video with views > 3x the channel's median views.

    Returns:
        {
            "channels": {
                "channel_name": {
                    "total_videos": int,
                    "median_views": int,
                    "outliers": [{"title": ..., "views": ..., "url": ...}, ...],
                },
                ...
            },
            "all_outliers": [{"title": ..., "views": ..., "url": ..., "channel": ...}, ...],
            "outlier_titles": [str, ...],
        }
    """
    if channel_ids is None:
        channel_ids = list(DEFAULT_COMPETITOR_CHANNELS.values())

    # Build reverse lookup for channel names
    id_to_name = {v: k for k, v in DEFAULT_COMPETITOR_CHANNELS.items()}

    youtube = _get_youtube_service()
    if not youtube:
        print("  [ERROR] Cannot access YouTube API — returning empty results")
        return {"channels": {}, "all_outliers": [], "outlier_titles": []}

    result = {"channels": {}, "all_outliers": [], "outlier_titles": []}

    for channel_id in channel_ids:
        channel_name = id_to_name.get(channel_id, channel_id)
        print(f"  Scanning: {channel_name} ({channel_id})...")

        uploads_pl = _get_channel_uploads_playlist(youtube, channel_id)
        if not uploads_pl:
            print(f"    Skipped — could not find uploads playlist")
            continue

        video_ids = _get_recent_videos(youtube, uploads_pl, max_results=50)
        if not video_ids:
            print(f"    Skipped — no videos found")
            continue

        videos = _get_video_stats(youtube, video_ids)
        if len(videos) < 3:
            print(f"    Skipped — not enough videos ({len(videos)})")
            continue

        views_list = [v["views"] for v in videos]
        median_views = int(statistics.median(views_list))
        outlier_threshold = median_views * 3

        outliers = [v for v in videos if v["views"] > outlier_threshold]
        outliers.sort(key=lambda v: v["views"], reverse=True)

        channel_data = {
            "total_videos": len(videos),
            "median_views": median_views,
            "outlier_threshold": outlier_threshold,
            "outliers": outliers,
        }
        result["channels"][channel_name] = channel_data

        for o in outliers:
            o_with_channel = {**o, "channel": channel_name}
            result["all_outliers"].append(o_with_channel)
            result["outlier_titles"].append(o["title"])

        print(f"    {len(videos)} videos, median {median_views:,} views, {len(outliers)} outliers")

    # Sort all outliers by views descending
    result["all_outliers"].sort(key=lambda v: v["views"], reverse=True)
    print(f"  Competitor scan complete: {len(result['all_outliers'])} total outliers found")
    return result


# ── Feature 3: Batch Title Generator ──────────────────────────────────────────

def generate_30_titles(
    suggestions: list[str] | None = None,
    outliers: list[dict] | None = None,
) -> list[dict]:
    """
    Generate 30 ranked video titles using Gemini + Title DNA + trends.

    Combines:
    - Title DNA patterns (proven formulas from title_dna.py)
    - Trending search terms from YouTube autocomplete
    - Competitor outlier video data

    Returns:
        [{"rank": 1, "title": "...", "hook_type": "...", "target_query": "..."}, ...]
    """
    if not _gemini_client:
        print("  [ERROR] Gemini API not available. Set GEMINI_API_KEY in .env")
        return []

    # Build context sections
    title_dna_text = get_title_prompt_insert()

    suggestions_text = "（無資料）"
    if suggestions:
        suggestions_text = "\n".join(f"  - {s}" for s in suggestions[:30])

    outlier_text = "（無資料）"
    if outliers:
        top_outliers = outliers[:15]
        outlier_lines = []
        for o in top_outliers:
            channel = o.get("channel", "?")
            views = o.get("views", 0)
            title = o.get("title", "?")
            outlier_lines.append(f"  - [{channel}] {title} ({views:,} views)")
        outlier_text = "\n".join(outlier_lines)

    patterns_list = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(TITLE_PATTERNS))
    power_words_text = "、".join(POWER_WORDS)

    prompt = f"""你是一個頂級的 YouTube 真實犯罪頻道標題策略師。

你的任務：根據以下三大數據來源，生成 30 個高 CTR 的中文影片標題。

━━━━━━━━━━━━━━━━━
📊 數據來源 1：標題 DNA 公式（從百萬級頻道提取）
━━━━━━━━━━━━━━━━━
{title_dna_text}

完整公式清單：
{patterns_list}

高效關鍵字：{power_words_text}

━━━━━━━━━━━━━━━━━
📊 數據來源 2：YouTube 即時搜尋趨勢
━━━━━━━━━━━━━━━━━
以下是目前觀眾正在搜尋的關鍵字：
{suggestions_text}

━━━━━━━━━━━━━━━━━
📊 數據來源 3：競爭對手爆款影片
━━━━━━━━━━━━━━━━━
以下是競爭頻道中觀看量遠超中位數的影片：
{outlier_text}

━━━━━━━━━━━━━━━━━
🎯 生成規則
━━━━━━━━━━━━━━━━━
1. 生成恰好 30 個標題
2. 每個標題必須使用至少一個「標題 DNA 公式」
3. 每個標題必須包含至少一個「高效關鍵字」
4. 優先針對搜尋趨勢中的熱門主題
5. 參考爆款影片的標題結構，但不要抄襲
6. 標題長度：15-30 個中文字
7. 標題要具體（包含案件名/地點/人名/數字等）
8. 前10個標題：台灣案件
9. 第11-20個：日本/韓國/中國案件
10. 第21-30個：國際知名案件

按預估 CTR 高低排序（最佳排第1名）。

請回傳 JSON 陣列，格式如下（不要任何其他文字）：
[
  {{"rank": 1, "title": "標題", "hook_type": "使用的DNA公式類型", "target_query": "對應的搜尋趨勢關鍵字"}},
  ...
]"""

    try:
        print("  Calling Gemini to generate 30 titles...")
        response = _gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        text = response.text.strip()

        # Extract JSON array from response (might have markdown fencing)
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            print("  [ERROR] Gemini response did not contain a JSON array")
            print(f"  Response preview: {text[:200]}")
            return []

        titles = json.loads(match.group())

        if not isinstance(titles, list):
            print("  [ERROR] Parsed result is not a list")
            return []

        print(f"  Generated {len(titles)} titles")
        return titles

    except Exception as e:
        print(f"  [ERROR] Gemini title generation failed: {e}")
        return []


# ── Standalone runner ─────────────────────────────────────────────────────────

def run_full_pipeline():
    """Run the complete trend engine pipeline and print results."""
    print("=" * 60)
    print("  TREND ENGINE — YouTube Growth Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Stage 1: YouTube Autocomplete
    print("\n[1/3] Fetching YouTube autocomplete suggestions...")
    suggestions = get_youtube_suggestions()
    if suggestions:
        print(f"\n  Top trending searches:")
        for i, s in enumerate(suggestions[:15], 1):
            print(f"    {i:2d}. {s}")

    # Stage 2: Competitor Scanner
    print("\n[2/3] Scanning competitor channels for outliers...")
    competitor_data = scan_competitor_channels()
    outliers = competitor_data.get("all_outliers", [])
    if outliers:
        print(f"\n  Top outlier videos:")
        for i, o in enumerate(outliers[:10], 1):
            print(f"    {i:2d}. [{o.get('channel', '?')}] {o['title']}")
            print(f"        {o['views']:,} views — {o['url']}")

    # Stage 3: Generate 30 Titles
    print("\n[3/3] Generating 30 data-driven titles with Gemini...")
    titles = generate_30_titles(suggestions, outliers)
    if titles:
        print(f"\n  {'='*50}")
        print(f"  30 RANKED VIDEO TITLES")
        print(f"  {'='*50}")
        for t in titles:
            rank = t.get("rank", "?")
            title = t.get("title", "?")
            hook = t.get("hook_type", "")
            query = t.get("target_query", "")
            print(f"\n  #{rank}: {title}")
            if hook:
                print(f"       Hook: {hook}")
            if query:
                print(f"       Query: {query}")

    # Save results
    output = {
        "generated_at": datetime.now().isoformat(),
        "suggestions_count": len(suggestions),
        "suggestions": suggestions,
        "outliers_count": len(outliers),
        "outliers": outliers,
        "titles": titles,
    }
    output_file = "trend_engine_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to {output_file}")
    print("=" * 60)

    return output


if __name__ == "__main__":
    run_full_pipeline()
