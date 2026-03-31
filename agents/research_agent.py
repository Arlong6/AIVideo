"""
Research Agent — deep case investigation.

Responsibilities:
- Extract verified facts about the case
- Build detailed timeline
- Identify key people (victims, suspects, investigators)
- Find news sources and references
- Fact-check the script against known sources
"""
from agents.llm import ask


def investigate_case(topic: str) -> dict:
    """
    Deep research on a crime case. Returns structured case data
    that all other agents can use.
    """
    print(f"  [Research] Investigating: {topic}")

    result = ask(f"""你是一位資深犯罪紀實研究員。請深入調查以下案件，提供完整且準確的資料。

案件主題：{topic}

請用 JSON 格式回傳以下資訊（所有資訊必須基於真實記錄，不可捏造）：

{{
  "case_name": "案件正式名稱",
  "case_name_en": "English case name",
  "year": "案發年份",
  "date": "案發日期（如 1997-04-14）",
  "country": "國家",
  "city": "城市",
  "summary": "案件概述（100字以內）",

  "victims": [
    {{"name": "姓名", "age": "年齡", "description": "身份簡述"}}
  ],
  "suspects": [
    {{"name": "姓名", "role": "角色（主嫌/共犯）", "description": "簡述", "outcome": "結果（判刑/在逃/死刑）"}}
  ],

  "timeline": [
    {{"date": "日期", "event": "事件標題", "detail": "詳細描述（30字以內）"}}
  ],

  "key_facts": [
    "關鍵事實1",
    "關鍵事實2",
    "關鍵事實3"
  ],

  "case_type": "案件類型（綁架/連環殺人/懸案/...）",
  "status": "結案狀態（已破案/懸案/審理中）",
  "social_impact": "社會影響（一句話）",

  "search_keywords_en": ["English search term 1", "term 2", "term 3", "term 4", "term 5"],
  "search_keywords_zh": ["中文搜尋1", "搜尋2", "搜尋3"]
}}""")

    print(f"  [Research] Found: {len(result.get('timeline', []))} timeline events, "
          f"{len(result.get('victims', []))} victims, {len(result.get('suspects', []))} suspects")
    return result


def fact_check_script(script: str, case_data: dict) -> dict:
    """
    Cross-check a generated script against known case facts.
    Returns issues found.
    """
    print(f"  [Research] Fact-checking script...")

    result = ask(f"""你是犯罪紀實的事實查核編輯。請比對以下腳本和已知案件資料，找出任何事實錯誤。

=== 已知案件資料 ===
{case_data}

=== 生成的腳本 ===
{script[:3000]}

請回傳 JSON：
{{
  "accuracy_score": 0-100 的準確度分數,
  "issues": [
    {{"type": "事實錯誤/時間錯誤/人名錯誤/誇大", "description": "問題描述", "suggestion": "修正建議"}}
  ],
  "verdict": "通過/需修正/重寫"
}}""")

    score = result.get("accuracy_score", 0)
    issues = result.get("issues", [])
    print(f"  [Research] Accuracy: {score}/100, issues: {len(issues)}")
    return result
