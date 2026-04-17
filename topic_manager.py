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

# Google News RSS — prioritize Taiwan/Asia crime news
NEWS_RSS_URLS = [
    "https://news.google.com/rss/search?q=台灣+犯罪+殺人+案件&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=犯罪+謀殺+懸案+台灣&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=日本+犯罪+殺人+事件&hl=zh-TW&gl=TW&ceid=TW:zh-Hant",
    "https://news.google.com/rss/search?q=taiwan+crime+murder+case&hl=en&gl=TW&ceid=TW:en",
    "https://news.google.com/rss/search?q=asia+crime+murder+case&hl=en&gl=US&ceid=US:en",
]

from config import GEMINI_API_KEY

_gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass

_claude_client = None
if ANTHROPIC_API_KEY:
    _claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

TODAY_TOPICS_FILE = "today_topics.json"


def _call_claude_text(prompt: str, max_tokens: int = 300) -> str:
    """Call LLM: Gemini first (free), Claude fallback (paid)."""
    # Try Gemini
    if _gemini_client:
        try:
            r = _gemini_client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt)
            return r.text.strip()
        except Exception as e:
            print(f"  [WARN] Gemini topic suggestion failed: {e}")

    # Fallback to Claude
    if not _claude_client:
        raise RuntimeError("No LLM available")

    models = ["claude-sonnet-4-6", "claude-opus-4-6"]
    for model in models:
        for attempt in range(3):
            try:
                msg = _claude_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text.strip()
            except anthropic.APIStatusError as e:
                if e.status_code in (400, 500, 529):
                    wait = 20 * (attempt + 1)
                    print(f"  [WARN] {model} error {e.status_code}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        print(f"  [WARN] {model} failed after 3 retries, trying next model...")
    raise RuntimeError("All LLM models failed")


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
- 【優先順序】：台灣本地案件 > 日本/韓國/中國案件 > 東南亞案件 > 知名歐美案件
- 前3個題材必須是台灣或亞洲案件
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
- 涵蓋不同類型：連環殺手、懸案、綁架、詐欺、間諜案、隨機殺人等
- 【優先順序】：台灣本地案件 > 日本/韓國/中國案件 > 東南亞案件 > 知名歐美案件
- 前3個題材必須是台灣或亞洲案件（例：台灣隨機殺人案、日本奧姆真理教、韓國華城連環殺人案、中國滅門案等）
- 每個題材要夠具體（含案件名稱或人名）
- 台灣觀眾對本地案件有更強共鳴，優先選擇

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

    # Fuzzy dedup: skip topics that share 4+ consecutive chars with any used topic
    def _is_too_similar(candidate: str, used: set) -> bool:
        c = candidate.replace(" ", "").lower()
        for u in used:
            u2 = u.replace(" ", "").lower()
            for i in range(len(c) - 3):
                if c[i:i+4] in u2:
                    return True
        return False

    # Taiwan-priority: reorder so Taiwan/local topics come first
    # Data shows Taiwan cases avg 49 views vs overseas 27 views
    _TW_KEYWORDS = {"台灣", "台北", "台南", "台中", "高雄", "桃園", "新北",
                    "彰化", "嘉義", "屏東", "花蓮", "基隆", "新竹", "苗栗",
                    "南投", "雲林", "宜蘭", "澎湖", "金門", "馬祖"}

    def _is_taiwan(t: str) -> bool:
        return any(kw in t for kw in _TW_KEYWORDS)

    tw_candidates = [c for c in candidates if _is_taiwan(c)]
    other_candidates = [c for c in candidates if not _is_taiwan(c)]
    candidates = tw_candidates + other_candidates

    for candidate in candidates:
        if not _is_too_similar(candidate, used_topics):
            # Verify topic is a real case via web search before committing.
            # LLMs fabricate plausible-sounding case names (e.g. 嘉義女教師姦殺案,
            # 東海花園命案). If Google returns zero relevant results → skip it.
            if not _verify_topic_exists(candidate):
                print(f"  [SKIP] Topic failed verification: {candidate}")
                used_topics.add(candidate)  # don't retry this one
                continue
            tag = "[台灣優先]" if _is_taiwan(candidate) else "[海外]"
            print(f"  Selected topic: {candidate} {tag} [已驗證]")
            return candidate

    # All candidates are similar or unverifiable
    print(f"  [WARN] All candidates similar/unverifiable, picking first anyway")
    print(f"  Selected topic: {candidates[0]}")
    return candidates[0]


def _verify_topic_exists(topic: str) -> bool:
    """Quick web search to verify a crime topic is a real, documented case.

    Uses Google News RSS (same as fetch_crime_news) to check if the case name
    appears in any search results. Returns True if at least 1 relevant result.
    This catches LLM hallucinations like fabricated case names.
    """
    import re

    # Extract the core case name (before any ：or | delimiters)
    core = re.split(r"[：:｜|（(]", topic)[0].strip()
    if len(core) < 3:
        return True  # Too short to verify meaningfully

    print(f"  [verify] Checking: {core[:40]}...")

    # Primary: Wikipedia (curated, fabricated cases won't have pages)
    wiki_hit = False
    try:
        resp = requests.get(
            "https://zh.wikipedia.org/w/api.php",
            params={"action": "query", "list": "search", "srsearch": core,
                    "srlimit": 3, "format": "json"},
            timeout=10,
        )
        if resp.status_code == 200:
            hits = resp.json().get("query", {}).get("search", [])
            if hits:
                # Check the top result title shares ≥2 Chinese chars with our query
                top_title = hits[0].get("title", "")
                shared = sum(1 for c in core if c in top_title and len(c.encode()) > 1)
                if shared >= 2:
                    print(f"  [verify] ✓ Wikipedia: {top_title[:30]} (shared={shared})")
                    wiki_hit = True
    except Exception as e:
        print(f"  [verify] Wikipedia failed: {e}")

    if wiki_hit:
        return True

    # Fallback: Google News RSS — two tiers:
    #   Tier 1: exact-match (quotes) → ≥1 result = real
    #   Tier 2: loose match (no quotes) → ≥10 results = real
    # This handles cases where the exact phrase is rare but individual
    # keywords are common enough to confirm the case exists.
    for query_fmt, threshold, label in [
        (f'"{core}"', 1, "exact"),
        (core, 10, "loose"),
    ]:
        try:
            resp = requests.get(
                "https://news.google.com/rss/search",
                params={"q": query_fmt, "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"},
                timeout=10,
                headers={"User-Agent": "TrueCrimeBot/1.0"},
            )
            if resp.status_code == 200:
                titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", resp.text)
                results = [t for t in titles[1:] if len(t) > 5]
                if len(results) >= threshold:
                    print(f"  [verify] ✓ Google News ({label}): {len(results)} results")
                    return True
                elif results:
                    print(f"  [verify] ~ Google News ({label}): {len(results)} results (need {threshold})")
        except Exception as e:
            print(f"  [verify] Google News ({label}) failed: {e}")

    print(f"  [verify] ✗ No Wikipedia + insufficient Google — likely fabricated")
    return False
