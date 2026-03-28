"""
Topic Manager — picks fresh topics daily, tracks used ones, fetches news.

Flow:
1. Load used_topics.json to know what's been done
2. Try to fetch trending crime news via Google News RSS
3. Use Claude to suggest new topics from the news
4. Fall back to topics.json if no news available
5. Save chosen topic to used_topics.json
"""

import json
import os
import re
import time
from datetime import datetime

import anthropic
import requests

from config import ANTHROPIC_API_KEY

USED_TOPICS_FILE = "used_topics.json"
TOPICS_FILE = "topics.json"

# Google News RSS — crime/true crime related feeds
NEWS_RSS_URLS = [
    "https://news.google.com/rss/search?q=serial+killer+murder+crime&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=true+crime+murder+case&hl=en&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=犯罪+謀殺+案件&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

TODAY_TOPICS_FILE = "today_topics.json"


def _call_claude_text(prompt: str, max_tokens: int = 300) -> str:
    """Call Claude with Opus→Sonnet fallback and 529/500 retry."""
    models = ["claude-opus-4-6", "claude-sonnet-4-6"]
    for model in models:
        for attempt in range(3):
            try:
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text.strip()
            except anthropic.APIStatusError as e:
                if e.status_code in (500, 529):
                    wait = 20 * (attempt + 1)
                    print(f"  [WARN] {model} error {e.status_code}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        print(f"  [WARN] {model} failed after 3 retries, trying next model...")
    raise RuntimeError("All Claude models overloaded")


# ── Used topics tracking ───────────────────────────────────────────────────────

def load_used_topics() -> set:
    if not os.path.exists(USED_TOPICS_FILE):
        return set()
    with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("used", []))


def _load_today_reserved() -> set:
    """Load topics already chosen today (other slots in same run)."""
    if not os.path.exists(TODAY_TOPICS_FILE):
        return set()
    with open(TODAY_TOPICS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("date") != today:
        return set()
    return set(data.get("topics", []))


def save_today_reserved(topic: str):
    """Reserve topic for today so other slots don't reuse it."""
    today = datetime.now().strftime("%Y-%m-%d")
    data = {"date": today, "topics": []}
    if os.path.exists(TODAY_TOPICS_FILE):
        with open(TODAY_TOPICS_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        if existing.get("date") == today:
            data["topics"] = existing.get("topics", [])
    if topic not in data["topics"]:
        data["topics"].append(topic)
    with open(TODAY_TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_used_topic(topic: str):
    used = list(load_used_topics())
    if topic not in used:
        used.append(topic)
    with open(USED_TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "used": used,
            "last_updated": datetime.now().isoformat(),
        }, f, ensure_ascii=False, indent=2)
    print(f"  Saved to used topics: {topic}")


# ── News fetching ──────────────────────────────────────────────────────────────

def _fetch_rss_headlines(url: str, limit: int = 10) -> list[str]:
    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "TrueCrimeBot/1.0"})
        resp.raise_for_status()
        # Simple regex parse — no xml library needed
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", resp.text)
        if not titles:
            titles = re.findall(r"<title>(.*?)</title>", resp.text)
        # Skip the first title (it's the feed name)
        return [t.strip() for t in titles[1:limit+1] if t.strip()]
    except Exception as e:
        print(f"  [WARN] RSS fetch failed ({url[:50]}...): {e}")
        return []


def fetch_crime_news() -> list[str]:
    """Fetch recent crime headlines from Google News RSS."""
    print("  Fetching crime news headlines...")
    all_headlines = []
    for url in NEWS_RSS_URLS:
        headlines = _fetch_rss_headlines(url, limit=8)
        all_headlines.extend(headlines)
        if len(all_headlines) >= 20:
            break

    # Deduplicate
    seen = set()
    unique = []
    for h in all_headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)

    print(f"  Found {len(unique)} headlines")
    return unique[:20]


# ── Claude topic suggestion ────────────────────────────────────────────────────

def suggest_topics_from_news(headlines: list[str], used_topics: set, count: int = 5) -> list[str]:
    """Use Claude to extract/suggest video topics from news headlines."""
    used_list = "\n".join(f"- {t}" for t in list(used_topics)[-20:]) or "（無）"
    headlines_text = "\n".join(f"- {h}" for h in headlines)

    prompt = f"""你是真實犯罪 YouTube 頻道的內容策劃。根據以下最新新聞標題，提出 {count} 個適合製作成3分鐘短影片的題材。

最新新聞標題：
{headlines_text}

已使用過的題材（不要重複）：
{used_list}

要求：
- 每個題材是一個具體案件名稱或故事（不要太泛，要能寫成腳本）
- 可以是新聞中直接提到的案件，也可以是新聞讓你聯想到的歷史相關案件
- 優先選擇台灣觀眾有興趣的案件（台灣本地、日本、知名歐美案件）
- 題材必須有足夠的公開資料可以寫成腳本
- 不要重複已使用過的題材

請直接回傳 JSON 陣列，不要其他文字：
["題材1", "題材2", "題材3", "題材4", "題材5"]"""

    try:
        text = _call_claude_text(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            topics = json.loads(m.group())
            return [t for t in topics if t not in used_topics]
        return []
    except Exception as e:
        print(f"  [WARN] Claude topic suggestion failed: {e}")
        return []


def suggest_topics_from_archive(used_topics: set, count: int = 5) -> list[str]:
    """Use Claude to generate fresh topics without news (pure creative/historical)."""
    used_list = "\n".join(f"- {t}" for t in list(used_topics)[-30:]) or "（無）"

    prompt = f"""你是真實犯罪 YouTube 頻道的內容策劃。請提出 {count} 個適合製作成3分鐘短影片的真實犯罪題材。

已使用過的題材（不要重複）：
{used_list}

要求：
- 選擇有豐富公開資料的真實案件
- 涵蓋不同類型：連環殺手、懸案、綁架、詐欺、間諜案等
- 優先台灣、日本、知名歐美案件
- 每個題材要夠具體（含案件名稱或人名）

請直接回傳 JSON 陣列：
["題材1", "題材2", "題材3", "題材4", "題材5"]"""

    try:
        text = _call_claude_text(prompt)
        m = re.search(r'\[.*?\]', text, re.DOTALL)
        if m:
            topics = json.loads(m.group())
            return [t for t in topics if t not in used_topics]
        return []
    except Exception as e:
        print(f"  [WARN] Claude archive suggestion failed: {e}")
        return []


# ── Topic bank management ──────────────────────────────────────────────────────

def _load_topic_bank() -> list[str]:
    """Load all topics from topics.json into a flat list."""
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    topics = []
    for category in data.values():
        if isinstance(category, list):
            topics.extend(category)
    return topics


def add_topics_to_bank(new_topics: list[str]):
    """Add AI-suggested topics to topics.json under 'ai_generated'."""
    if not new_topics:
        return
    data = {}
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    existing = _load_topic_bank()
    to_add = [t for t in new_topics if t not in existing]
    if not to_add:
        return

    if "ai_generated" not in data:
        data["ai_generated"] = []
    data["ai_generated"].extend(to_add)

    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Added {len(to_add)} new topics to bank")


# ── Main entry point ───────────────────────────────────────────────────────────

def pick_topic(refresh_news: bool = True) -> str:
    """
    Pick a fresh topic for today's video.
    1. Fetch crime news → ask Claude to suggest topics
    2. Add suggestions to topic bank
    3. Pick one that hasn't been used
    Returns the chosen topic string.
    """
    used_topics = load_used_topics()
    today_reserved = _load_today_reserved()
    if today_reserved:
        print(f"  Today's reserved (other slots): {today_reserved}")
    used_topics = used_topics | today_reserved
    print(f"  Used topics so far: {len(used_topics)}")

    suggestions = []

    if refresh_news:
        headlines = fetch_crime_news()
        if headlines:
            suggestions = suggest_topics_from_news(headlines, used_topics, count=5)
            if suggestions:
                print(f"  Claude suggested from news: {suggestions}")
                add_topics_to_bank(suggestions)

    # If news didn't yield results, ask Claude directly
    if not suggestions:
        print("  No news topics — asking Claude for archive suggestions...")
        suggestions = suggest_topics_from_archive(used_topics, count=5)
        if suggestions:
            print(f"  Claude suggested from archive: {suggestions}")
            add_topics_to_bank(suggestions)

    # Pick from suggestions first, fall back to topic bank
    topic_bank = _load_topic_bank()
    unused_bank = [t for t in topic_bank if t not in used_topics]

    candidates = suggestions + unused_bank
    if not candidates:
        raise RuntimeError("No unused topics available! Add more to topics.json.")

    chosen = candidates[0]
    print(f"  Selected topic: {chosen}")
    return chosen
