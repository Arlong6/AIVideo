"""
Research Agent — combined case investigation + fact check + visual direction.

Merged into ONE LLM call to save quota.
"""
from agents.llm import ask


def investigate_and_plan(topic: str) -> dict:
    """
    Single LLM call: research case + plan visuals + extract info card data.
    Returns everything other agents need.
    """
    print(f"  [Research] Investigating + planning: {topic}")

    result = ask(f"""你是一位資深犯罪紀實研究員兼視覺總監。請深入調查以下案件並規劃影片視覺。

案件主題：{topic}

請用 JSON 格式回傳（所有資訊必須基於真實記錄，不可捏造）：

{{
  "case_name": "案件正式名稱",
  "case_name_en": "English case name",
  "year": "案發年份",
  "date": "案發日期",
  "country": "國家",
  "city": "城市",
  "summary": "案件概述（100字以內）",
  "victims": [
    {{"name": "姓名", "age": "年齡", "description": "身份簡述"}}
  ],
  "suspects": [
    {{"name": "姓名", "role": "主嫌/共犯", "outcome": "判刑結果"}}
  ],
  "timeline": [
    {{"date": "日期", "event": "事件標題", "detail": "詳細描述30字以內"}}
  ],
  "key_facts": ["關鍵事實1", "關鍵事實2", "關鍵事實3"],
  "case_type": "案件類型",
  "status": "結案狀態",
  "social_impact": "社會影響（一句話）",
  "search_keywords_en": ["English search 1", "search 2", "search 3"],
  "search_keywords_zh": ["中文搜尋1", "搜尋2"],
  "visual_plan": {{
    "wiki_search_queries": ["案件相關圖片搜尋1", "搜尋2", "搜尋3"],
    "pexels_queries": ["atmospheric query 1", "query 2", "query 3"],
    "style_notes": "視覺風格建議"
  }},
  "ticker": "新聞跑馬燈文字"
}}""")

    print(f"  [Research] Found: {len(result.get('timeline', []))} timeline events, "
          f"{len(result.get('victims', []))} victims")
    return result
