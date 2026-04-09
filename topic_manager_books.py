"""
Topic Manager — books channel (Route B: narrative retelling of book-sourced stories).

Flow is simpler than the crime topic manager for now:
1. Load `data/books/used_topics.json` to know what's been done
2. Load `data/books/topics.json` topic bank (hand-curated + LLM-augmented)
3. Optionally ask Gemini/Claude for fresh suggestions when the bank is thin
4. Pick the first unused topic with fuzzy dedup against history

Unlike the crime channel, there is no real-time news source — books / historical
events are evergreen. Topic freshness comes from the bank being periodically
refreshed by an LLM suggestion call, not daily news scraping.

All state files live under `data/books/` so the crime channel is untouched.
"""

import json
import os
import re
import time

import anthropic
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

# ── Paths ──────────────────────────────────────────────────────────────────────

BOOKS_DIR = "data/books"
USED_TOPICS_FILE = os.path.join(BOOKS_DIR, "used_topics.json")
TOPICS_FILE = os.path.join(BOOKS_DIR, "topics.json")
TODAY_TOPICS_FILE = os.path.join(BOOKS_DIR, "today_topics.json")


# ── LLM clients (shared pattern with crime topic_manager) ─────────────────────

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


def _call_llm_text(prompt: str, max_tokens: int = 500) -> str:
    """Try Gemini first (free), fall back to Claude."""
    if _gemini_client:
        try:
            r = _gemini_client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt
            )
            return r.text.strip()
        except Exception as e:
            print(f"  [WARN] Gemini books topic failed: {e}")

    if not _claude_client:
        raise RuntimeError("No LLM available")

    for model in ["claude-sonnet-4-6", "claude-opus-4-6"]:
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
    raise RuntimeError("All LLM models failed")


# ── State helpers ──────────────────────────────────────────────────────────────

def _ensure_books_dir():
    os.makedirs(BOOKS_DIR, exist_ok=True)


def load_used_topics() -> set:
    if not os.path.exists(USED_TOPICS_FILE):
        return set()
    try:
        with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("used", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_used_topic(topic: str):
    _ensure_books_dir()
    used = load_used_topics()
    used.add(topic)
    from datetime import datetime
    with open(USED_TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"used": sorted(used), "last_updated": datetime.utcnow().isoformat()},
            f,
            ensure_ascii=False,
            indent=2,
        )


def _load_topic_bank() -> list[str]:
    if not os.path.exists(TOPICS_FILE):
        return []
    with open(TOPICS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    topics = []
    if isinstance(data, list):
        topics = data
    elif isinstance(data, dict):
        for category in data.values():
            if isinstance(category, list):
                topics.extend(category)
    return topics


def add_topics_to_bank(new_topics: list[str]):
    if not new_topics:
        return
    _ensure_books_dir()
    data = {}
    if os.path.exists(TOPICS_FILE):
        with open(TOPICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    if not isinstance(data, dict):
        data = {"curated": data if isinstance(data, list) else []}
    existing = _load_topic_bank()
    to_add = [t for t in new_topics if t not in existing]
    if not to_add:
        return
    data.setdefault("ai_generated", []).extend(to_add)
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Added {len(to_add)} new books topics to bank")


# ── LLM topic suggestion ──────────────────────────────────────────────────────

def suggest_topics_from_llm(used_topics: set, count: int = 5) -> list[str]:
    """Ask LLM to generate fresh Route-B book topics (narrative-driven)."""
    used_str = "\n".join(f"- {t}" for t in sorted(used_topics)[:20]) or "（無）"
    prompt = f"""你是一個華語 YouTube 說書頻道的選題策略師。這個頻道走「故事化說書」路線 —
不是書評摘要、不是書單，而是挑選「一本書 + 一個戲劇化的歷史事件/人物/事件」，
用紀錄片敘事節奏重現故事本身，把書當作權威錨點。

題材必須符合：
1. 有強烈戲劇張力（人物命運、意外轉折、謎團、權力鬥爭）
2. 有一本廣為人知或有權威性的**真實存在**的書作為主要資料來源（不要虛構書名）
3. 繁體中文觀眾感興趣（台灣、華人世界、或全球知名事件）
4. 非小說題材（歷史、傳記、報導文學、社會事件）

避免以下已經用過的題材：
{used_str}

請生成 {count} 個題材建議，每個格式為「事件/人物名稱：一句話戲劇化描述｜《書名》」。
例如：「1929 華爾街崩盤前夜：最富有的三個人做了同一件事｜《恐慌的時代》」

直接回傳 JSON 陣列，不要其他說明：
["題材1｜《書名1》", "題材2｜《書名2》", ...]"""

    try:
        text = _call_llm_text(prompt, max_tokens=800)
        m = re.search(r"\[.*?\]", text, re.DOTALL)
        if m:
            topics = json.loads(m.group())
            return [t for t in topics if t not in used_topics]
        return []
    except Exception as e:
        print(f"  [WARN] Books topic LLM call failed: {e}")
        return []


# ── Main entry point ───────────────────────────────────────────────────────────

def pick_topic_books(refresh: bool = False) -> str:
    """Pick a fresh books topic. Mirrors the crime channel's pick_topic API."""
    _ensure_books_dir()
    used_topics = load_used_topics()
    print(f"  Books used topics so far: {len(used_topics)}")

    # Try topic bank first — it's the curated high-quality source
    topic_bank = _load_topic_bank()
    unused_bank = [t for t in topic_bank if t not in used_topics]

    if refresh or len(unused_bank) < 3:
        print("  Books topic bank thin — asking LLM for suggestions...")
        suggestions = suggest_topics_from_llm(used_topics, count=5)
        if suggestions:
            print(f"  LLM suggested: {suggestions}")
            add_topics_to_bank(suggestions)
            unused_bank = [t for t in _load_topic_bank() if t not in used_topics]

    if not unused_bank:
        raise RuntimeError(
            "No unused books topics available! Seed data/books/topics.json "
            "or run with refresh=True to get LLM suggestions."
        )

    # Fuzzy dedup: skip topics that share 4+ consecutive chars with any used topic
    def _is_too_similar(candidate: str, used: set) -> bool:
        c = candidate.replace(" ", "").lower()
        for u in used:
            u2 = u.replace(" ", "").lower()
            for i in range(len(c) - 3):
                if c[i : i + 4] in u2:
                    return True
        return False

    for candidate in unused_bank:
        if not _is_too_similar(candidate, used_topics):
            print(f"  Selected books topic: {candidate}")
            return candidate

    # All too similar — warn and pick first anyway
    print("  [WARN] All books candidates similar to used topics, picking first anyway")
    print(f"  Selected books topic: {unused_bank[0]}")
    return unused_bank[0]
