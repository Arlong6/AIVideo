"""
Trend Scraper — PTT & Dcard trending crime/mystery topics for Taiwan.

Scrapes:
  1. PTT Gossiping board (八卦版) — HTML scrape with over18 cookie
  2. PTT CriminalCase board (犯罪版)
  3. Dcard trending posts — public API

Returns a unified list of trending topics with title, source, engagement, url.

Usage:
    python trend_scraper.py
"""

import re
import time
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup


# ── Crime/mystery keyword filter ─────────────────────────────────────────────

CRIME_KEYWORDS = [
    "殺", "死", "命案", "兇手", "犯罪", "犯人", "嫌犯", "嫌疑",
    "懸案", "謀殺", "綁架", "詐騙", "失蹤", "屍", "槍", "毒",
    "性侵", "強盜", "搶劫", "縱火", "逃犯", "通緝", "判刑",
    "監獄", "警察", "警方", "刑事", "偵查", "法院", "法官",
    "檢察", "鑑識", "DNA", "血", "案件", "被害", "受害",
    "恐怖", "靈異", "神秘", "離奇", "詭異", "驚悚", "懸疑",
    "冤獄", "黑道", "幫派", "組織犯罪", "洗錢", "暗網",
]

# Boards where every post is crime-related (no keyword filter needed)
CRIME_BOARDS = {"criminalcase"}


@dataclass
class TrendingTopic:
    title: str
    source: str          # "PTT" or "Dcard"
    board: str           # e.g. "Gossiping", "CriminalCase", "trending"
    engagement: int      # push count or like count
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


# ── PTT Scraper ──────────────────────────────────────────────────────────────

PTT_BASE = "https://www.ptt.cc"
PTT_COOKIES = {"over18": "1"}
PTT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


def _parse_push_count(text: str) -> int:
    """Convert PTT push count text to int. 'X1' = -1, '爆' = 100, '' = 0."""
    text = text.strip()
    if not text:
        return 0
    if text == "爆":
        return 100
    if text.startswith("X"):
        try:
            return -int(text[1:])
        except ValueError:
            return -1
    try:
        return int(text)
    except ValueError:
        return 0


def _scrape_ptt_board(board: str, pages: int = 3,
                      min_push: int = 50,
                      skip_keyword_filter: bool = False) -> list[TrendingTopic]:
    """
    Scrape a PTT board's recent pages for trending posts.

    Args:
        board: Board name (e.g. "Gossiping", "CriminalCase")
        pages: Number of index pages to scan (latest N)
        min_push: Minimum push count to consider "trending"

    Returns:
        List of TrendingTopic for posts above the push threshold.
    """
    results = []
    board_lower = board.lower()
    skip_keyword_filter = board_lower in CRIME_BOARDS

    session = requests.Session()
    session.cookies.update(PTT_COOKIES)
    session.headers.update(PTT_HEADERS)

    # Start from the latest index page
    url = f"{PTT_BASE}/bbs/{board}/index.html"

    for page_num in range(pages):
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [WARN] PTT {board} page fetch failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "html.parser")

        # Parse each post entry
        for entry in soup.select("div.r-ent"):
            # Push count
            push_el = entry.select_one("div.nrec span")
            push_text = push_el.get_text() if push_el else ""
            push_count = _parse_push_count(push_text)

            if push_count < min_push:
                continue

            # Title and link
            title_el = entry.select_one("div.title a")
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            post_url = f"{PTT_BASE}{href}" if href else ""

            # Skip announcements
            if title.startswith("[公告]") or title.startswith("Fw: [公告]"):
                continue

            # Crime keyword filter (unless board is inherently crime-related)
            if not skip_keyword_filter:
                if not any(kw in title for kw in CRIME_KEYWORDS):
                    continue

            results.append(TrendingTopic(
                title=title,
                source="PTT",
                board=board,
                engagement=push_count,
                url=post_url,
            ))

        # Navigate to previous page
        prev_link = soup.select_one('a.btn.wide:-soup-contains("上頁")')
        if not prev_link:
            # Fallback: look for link with "上頁" text
            for a in soup.select("a.btn.wide"):
                if "上頁" in a.get_text():
                    prev_link = a
                    break

        if prev_link and prev_link.get("href"):
            url = f"{PTT_BASE}{prev_link['href']}"
        else:
            break

        time.sleep(0.5)  # polite delay

    return results


def scrape_ptt(min_push: int = 50) -> list[TrendingTopic]:
    """Scrape both PTT Gossiping and CriminalCase boards."""
    topics = []

    print("  Scraping PTT Gossiping (八卦版)...")
    gossiping = _scrape_ptt_board("Gossiping", pages=3, min_push=min_push)
    topics.extend(gossiping)
    print(f"    Found {len(gossiping)} trending crime/mystery posts")

    # Also try broader search on Gossiping with lower threshold
    print("  Scraping PTT Gossiping (八卦版, 低門檻)...")
    broad = _scrape_ptt_board("Gossiping", pages=5, min_push=max(5, min_push // 5))
    # Deduplicate
    existing = {t.title for t in topics}
    for t in broad:
        if t.title not in existing:
            topics.append(t)
            existing.add(t.title)
    print(f"    Found {len(broad)} additional posts")

    return topics


# ── Dcard Scraper ────────────────────────────────────────────────────────────

DCARD_API = "https://www.dcard.tw/service/api/v2"
DCARD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.dcard.tw/",
}


def scrape_dcard(limit: int = 100, min_likes: int = 50) -> list[TrendingTopic]:
    """
    Fetch trending Dcard posts and filter for crime/mystery topics.

    Uses Dcard's public API for trending posts across all forums,
    then filters by crime-related keywords.
    """
    topics = []

    # Try trending posts endpoint
    endpoints = [
        f"{DCARD_API}/posts?popular=true&limit={limit}",
        f"{DCARD_API}/forums/trending/posts?limit={limit}",
    ]

    posts = []
    for endpoint in endpoints:
        try:
            resp = requests.get(endpoint, headers=DCARD_HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    posts = data
                    break
        except Exception as e:
            print(f"  [WARN] Dcard endpoint failed ({endpoint}): {e}")
            continue

    if not posts:
        print("  [WARN] Could not fetch Dcard posts from any endpoint")
        return topics

    for post in posts:
        title = post.get("title", "")
        like_count = post.get("likeCount", 0)
        post_id = post.get("id", "")
        forum_name = post.get("forumName", "unknown")

        if like_count < min_likes:
            continue

        # Crime keyword filter
        excerpt = title + " " + post.get("excerpt", "")
        if not any(kw in excerpt for kw in CRIME_KEYWORDS):
            continue

        post_url = f"https://www.dcard.tw/f/{forum_name}/p/{post_id}" if post_id else ""

        topics.append(TrendingTopic(
            title=title,
            source="Dcard",
            board=forum_name,
            engagement=like_count,
            url=post_url,
        ))

    return topics


# ── Public API ───────────────────────────────────────────────────────────────

def scrape_all_trends(ptt_min_push: int = 50,
                      dcard_min_likes: int = 50) -> list[dict]:
    """
    Scrape all sources and return a unified, sorted list of trending topics.

    Returns:
        List of dicts with keys: title, source, board, engagement, url
        Sorted by engagement descending.
    """
    all_topics: list[TrendingTopic] = []

    # PTT
    try:
        ptt_topics = scrape_ptt(min_push=ptt_min_push)
        all_topics.extend(ptt_topics)
    except Exception as e:
        print(f"  [ERROR] PTT scraping failed: {e}")

    time.sleep(1)

    # Dcard
    try:
        print("  Scraping Dcard trending posts...")
        dcard_topics = scrape_dcard(min_likes=dcard_min_likes)
        all_topics.extend(dcard_topics)
        print(f"    Found {len(dcard_topics)} trending crime/mystery posts")
    except Exception as e:
        print(f"  [ERROR] Dcard scraping failed: {e}")

    # Deduplicate by title similarity (exact match)
    seen_titles = set()
    unique_topics = []
    for t in all_topics:
        normalized = t.title.strip()
        if normalized not in seen_titles:
            seen_titles.add(normalized)
            unique_topics.append(t)

    # Sort by engagement
    unique_topics.sort(key=lambda t: t.engagement, reverse=True)

    print(f"\n  Total trending crime/mystery topics: {len(unique_topics)}")
    return [t.to_dict() for t in unique_topics]


# ── Standalone runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json
    from datetime import datetime

    print("=" * 60)
    print("  TREND SCRAPER — PTT & Dcard Crime/Mystery Topics")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    topics = scrape_all_trends()

    if topics:
        print(f"\n  {'='*50}")
        print(f"  TOP TRENDING TOPICS")
        print(f"  {'='*50}")
        for i, t in enumerate(topics[:20], 1):
            print(f"\n  {i:2d}. [{t['source']}/{t['board']}] {t['title']}")
            print(f"      Engagement: {t['engagement']} | {t['url']}")

    # Save results
    output = {
        "scraped_at": datetime.now().isoformat(),
        "total_topics": len(topics),
        "topics": topics,
    }
    with open("trend_scraper_results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to trend_scraper_results.json")
    print("=" * 60)
