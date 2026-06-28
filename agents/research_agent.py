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

# Fail-closed thresholds. The PRIMARY signal that a case is real & verifiable is
# the SOURCE COUNT — a dry-run over 12 real cases showed every one returned
# 11-19 sources, while a fabricated topic returned 0. Corpus LENGTH is just how
# verbose the model's summary happened to be (a famous case summarized tersely at
# 777 chars is still real), so it is only a floor to catch genuinely-empty
# retrieval — never the main gate. A terse-but-well-sourced corpus is ENRICHED
# with a second retrieval pass instead of skipped.
MIN_SOURCES = 3          # < this ⇒ topic is unverifiable ⇒ skip (fail-closed)
ENRICH_BELOW = 1100      # corpus shorter than this ⇒ pull a 2nd, deeper pass
MIN_CORPUS_CHARS = 500   # final floor: only truly-empty retrieval fails closed


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
        f"""請用繁體中文，根據網路搜尋到的『真實、可查證』資料，詳細整理以下案件的事實，
至少 800 字。盡可能涵蓋：涉案人物的姓名與年齡、案發的時間與地點、完整事件經過、調查與
審判、判決結果、以及社會影響。只陳述搜尋結果中確實存在的事實；無法查證的細節不要寫、
不要推測、不要編造。

案件：{topic}""")

    # ── 2. FAIL CLOSED on unverifiable topics (no real sources) ──────────
    if len(sources) < MIN_SOURCES:
        raise ThinSourceError(
            f"查無足夠可信來源（sources={len(sources)}），"
            f"跳過題材以避免憑空杜撰：{topic}")

    # ── 2b. ENRICH a terse-but-well-sourced corpus (don't skip a real case
    #        just because the first summary was short) ────────────────────
    if len(corpus) < ENRICH_BELOW:
        try:
            more, more_src = ask_grounded(
                f"""請用繁體中文，根據網路搜尋結果，補充以下案件的更多『可查證』細節：
完整時間線（日期與事件）、涉案人物的姓名與背景、調查與審判過程、最終判決、後續影響與
爭議。只寫搜尋結果中確實存在的事實，不要重複、不要編造。

案件：{topic}""")
            if more:
                corpus = corpus + "\n\n" + more
            seen = {s["uri"] for s in sources}
            sources += [s for s in more_src if s.get("uri") not in seen]
        except Exception as e:
            print(f"  [Research] enrichment pass skipped ({e})")

    # final floor — only a genuinely-empty retrieval fails closed
    if len(corpus) < MIN_CORPUS_CHARS:
        raise ThinSourceError(
            f"檢索內容過少（corpus={len(corpus)}字, sources={len(sources)}），"
            f"跳過題材：{topic}")

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
