"""
Research Agent — search-grounded case investigation + visual planning.

Two steps, both on Gemini:
  1. RETRIEVE — `ask_grounded` pulls REAL source text via live Google Search
     (the model is NOT allowed to write from memory).
  2. STRUCTURE — the retrieved corpus is the ONLY authority fed into a JSON
     extraction pass; anything not in the corpus is left blank.

Fail-closed: if retrieval returns thin/no sources, raise ThinSourceError so the
orchestrator skips the topic and alerts — we NEVER fall back to memory-only
writing (that is the root cause of both the "Wikipedia voice" and the
fabrication takedowns).
"""
from agents.llm import ask, ask_grounded

# Fail-closed thresholds — below these the retrieved corpus is too thin to
# write a truthful video from, so the topic is skipped.
MIN_CORPUS_CHARS = 1200
MIN_SOURCES = 3


class ThinSourceError(Exception):
    """Raised when live search returns too little real source material."""
    pass


_SCHEMA = """{
  "case_name": "案件正式名稱",
  "case_name_en": "English case name",
  "year": "案發年份",
  "date": "案發日期",
  "country": "國家",
  "city": "城市",
  "summary": "案件概述（100字以內）",
  "victims": [
    {"name": "姓名", "age": "年齡", "description": "身份簡述"}
  ],
  "suspects": [
    {"name": "姓名", "role": "主嫌/共犯", "outcome": "判刑結果"}
  ],
  "timeline": [
    {"date": "日期", "event": "事件標題", "detail": "詳細描述30字以內"}
  ],
  "key_facts": ["關鍵事實1", "關鍵事實2", "關鍵事實3"],
  "case_type": "案件類型",
  "status": "結案狀態",
  "social_impact": "社會影響（一句話）",
  "search_keywords_en": ["English search 1", "search 2", "search 3"],
  "search_keywords_zh": ["中文搜尋1", "搜尋2"],
  "visual_plan": {
    "wiki_search_queries": ["案件相關圖片搜尋1", "搜尋2", "搜尋3"],
    "pexels_queries": ["atmospheric query 1", "query 2", "query 3"],
    "style_notes": "視覺風格建議"
  },
  "ticker": "新聞跑馬燈文字"
}"""


def investigate_and_plan(topic: str) -> dict:
    """Search-ground the case, then structure the retrieved facts into case_data.

    Returns the same case_data shape downstream agents already expect, plus
    `_grounding_corpus` (the retrieved source text) and `_grounding_sources`
    (the cited URLs) for the claim verifier and the description.
    """
    print(f"  [Research] Grounding via live search: {topic}")

    # ── 1. RETRIEVE real source text ─────────────────────────────────────
    corpus, sources = ask_grounded(
        f"""請用繁體中文，根據網路搜尋到的『真實、可查證』資料，詳細整理以下案件的事實。
盡可能涵蓋：涉案人物的姓名與年齡、案發的時間與地點、事件經過、調查與審判、判決結果、
以及社會影響。只陳述搜尋結果中確實存在的事實；無法查證的細節不要寫、不要推測、不要編造。

案件：{topic}""")

    # ── 2. FAIL CLOSED on thin sources ───────────────────────────────────
    if len(corpus) < MIN_CORPUS_CHARS or len(sources) < MIN_SOURCES:
        raise ThinSourceError(
            f"來源不足（corpus={len(corpus)}字, sources={len(sources)}），"
            f"跳過題材以避免憑空杜撰：{topic}")

    print(f"  [Research] Grounded: {len(corpus)} chars from {len(sources)} sources")

    # ── 3. STRUCTURE the corpus into case_data (corpus = ONLY authority) ──
    result = ask(
        f"""你是一位資深犯罪紀實研究員兼視覺總監。以下是針對此案件「透過網路搜尋檢索到的
原始資料」。請『只』根據這份原始資料，整理成 JSON。

鐵則：
- 原始資料中沒有提到的事實，對應欄位一律留空（空字串或空陣列）。
- 絕對不可從你自己的記憶補充、推測或編造任何人名、日期、數字或情節。
- 寧可留空，也不要填入無法在原始資料中找到的內容。

案件主題：{topic}

=== 檢索到的原始資料（唯一可信來源）===
{corpus}
=== 原始資料結束 ===

請用以下 JSON 格式回傳（所有資訊必須能在上面的原始資料中找到）：

{_SCHEMA}""")

    # ── 4. attach grounding for the verifier + sources list ──────────────
    if isinstance(result, dict):
        result["_grounding_corpus"] = corpus
        result["_grounding_sources"] = sources
    else:
        result = {"_grounding_corpus": corpus, "_grounding_sources": sources}

    print(f"  [Research] Structured: {len(result.get('timeline', []))} timeline events, "
          f"{len(result.get('victims', []))} victims")
    return result
