"""
Script Agent — generate 8-section long-form script.

Uses case data from Research Agent to write an accurate,
engaging 15-20 minute documentary script.
"""
from agents.llm import ask
from title_dna import get_title_prompt_insert


def generate_script(case_data: dict) -> dict:
    """Generate a full long-form script based on researched case data."""
    topic = case_data.get("case_name", "")
    title_dna = get_title_prompt_insert()

    print(f"  [Script] Generating 8-section script...")

    # Pass 1: First 4 sections
    p1 = ask(f"""你是百萬訂閱犯罪紀實 YouTube 頻道的腳本作家。

{title_dna}

=== 案件資料（經過事實查核）===
案件：{case_data.get('case_name', '')}
日期：{case_data.get('date', '')}
地點：{case_data.get('city', '')}, {case_data.get('country', '')}
受害者：{case_data.get('victims', [])}
嫌疑人：{case_data.get('suspects', [])}
時間線：{case_data.get('timeline', [])}
關鍵事實：{case_data.get('key_facts', [])}
結案狀態：{case_data.get('status', '')}
社會影響：{case_data.get('social_impact', '')}

=== 任務：生成前半部（4段，約 1300字 → 影片 7-8 分鐘）===
※ 2026-05-07 起改為 8-12 分鐘策略（光暗雜學館的甜蜜點），
   原 15-20 分鐘 retention 過低。短一點更易破 50% AVD。

【1. Hook（150-200字）】從最震撼的事實開始
【2. 背景（300-400字）】介紹受害者，建立情感連結
【3. 案件經過（400-500字）】時間線還原，短句製造緊張
【4. 調查過程（300-400字）】警方行動、線索、嫌疑人

語言要求：繁體中文、台灣用語、短句、英文人名保留原文

⚠️⚠️⚠️ 事實底線（違反必須整段重寫）⚠️⚠️⚠️
1. **所有具體事實**(人名/年份/地點/數字/職業/案發過程)**只能來自上方的「案件資料」**
2. 不准自行加入 case_data 沒提供的人名、地名、年份、機構名稱
3. 不准混搭 — 不可把不同案件的細節組合成新故事
4. 若 case_data 某欄位是空 (e.g. victims=[])、模糊或不確定,**用模糊措辭**(「一名年輕人」「某縣市」),不要編造具體人名/地點
5. 寧可文采少 10%,也不要為了戲劇效果加未經查證的細節
6. 標題可以聳動但**不可虛構** — 「99%沒看懂」「真相顛覆想像」OK,「為求健康竟活活餓死親兒」必須案件確實有此情節才能用
7. 若你發現 case_data 內部矛盾或太薄弱,在 hook 第一句加一個 `[FACT_DOUBT]` 標記讓人類審查者知道

回傳 JSON：
{{
  "title": "影片標題（使用標題DNA公式，30字以內）",
  "opening_card": "開場字卡（8字以內）",
  "sections": [
    {{"name": "hook", "script": "全文", "visual_hints": ["這段需要什麼畫面1", "畫面2"]}},
    {{"name": "background", "script": "全文", "visual_hints": ["畫面描述"]}},
    {{"name": "crime", "script": "全文", "visual_hints": ["畫面描述"]}},
    {{"name": "investigation", "script": "全文", "visual_hints": ["畫面描述"]}}
  ],
  "keywords_en": ["English Pexels search 1", "search 2", "...共20個"]
}}""")

    print(f"  [Script] Pass 1 done: {sum(len(s['script']) for s in p1.get('sections', []))} chars")

    # Pass 2: Last 4 sections
    sections_context = "\n".join(
        f"【{s['name']}】{s['script'][:150]}..." for s in p1.get("sections", []))

    p2 = ask(f"""繼續生成後半部（4段，約 1000字）+ YouTube 描述欄。

案件：{case_data.get('case_name', '')}
前半部摘要：{sections_context}

【5. 轉折（300-400字）】意外發展、新證據
【6. 結局（300-400字）】破案/未破案、審判結果
【7. 反思（150-200字）】社會影響、法律改變
【8. 結語（80-100字）】留下餘韻、呼籲訂閱

同時選出 2-3 個最適合截取為 Shorts 的精彩段落。

=== YouTube 描述欄要求（依 UCzut 競品分析,中位數 63k 靠這個）===
前 150 字必須三段式鉤子（這是搜尋預覽 + AI Overview 看到的部分）：
  ① 場景句：「{{年}}年{{月}},{{地點}},{{人物身份}}」一句帶出時間+地點+人物
  ② 衝突句：「{{核心矛盾或最荒誕細節}}」用最具體的一句點出案件核心
  ③ 開放問題：「{{留鉤子的問題}}?」引發觀眾繼續看
接著 200-300 字案件深度摘要（事件脈絡 + 結局），自然置入 SEO 關鍵字：
  「台灣真實犯罪」「{{地名}}事件」「真實案件記錄」「未解懸案」（依案件擇用）

回傳 JSON：
{{
  "sections": [
    {{"name": "twist", "script": "全文", "visual_hints": ["畫面描述"]}},
    {{"name": "resolution", "script": "全文", "visual_hints": ["畫面描述"]}},
    {{"name": "reflection", "script": "全文", "visual_hints": ["畫面描述"]}},
    {{"name": "cta", "script": "全文", "visual_hints": ["畫面描述"]}}
  ],
  "shorts_candidates": [
    {{"title": "Shorts標題", "script": "200字獨立片段", "section_source": "twist"}}
  ],
  "youtube_description": "前150字三段式鉤子 + 200-300字案件深度摘要"
}}""")

    print(f"  [Script] Pass 2 done: {sum(len(s['script']) for s in p2.get('sections', []))} chars")

    # Merge
    all_sections = p1.get("sections", []) + p2.get("sections", [])
    full_script = "\n\n".join(s["script"] for s in all_sections)

    # Build visual_scenes from visual_hints
    visual_scenes = []
    for s in all_sections:
        hints = s.get("visual_hints", [])
        visual_scenes.extend(hints[:8])

    # Build pacing
    pacing_map = {"hook": "fast", "crime": "medium", "twist": "fast",
                  "resolution": "medium", "cta": "slow"}
    scene_pacing = []
    for s in all_sections:
        pace = pacing_map.get(s["name"], "medium")
        n_scenes = len(s.get("visual_hints", []))
        scene_pacing.extend([pace] * max(n_scenes, 1))

    result = {
        "title": p1.get("title", case_data.get("case_name", "")),
        "opening_card": p1.get("opening_card", ""),
        "sections": all_sections,
        "script": full_script,
        "visual_scenes": visual_scenes,
        "scene_pacing": scene_pacing,
        "keywords": p1.get("keywords_en", case_data.get("search_keywords_en", [])),
        "description": p2.get("youtube_description") or case_data.get("summary", ""),
        "hashtags": ["#真實犯罪", "#犯罪紀實", "#懸案", "#深度解析", "#台灣"],
        "shorts_candidates": p2.get("shorts_candidates", []),
        "format": "long",
    }

    total = len(full_script)
    print(f"  [Script] Complete: {total} chars, {len(all_sections)} sections, "
          f"{len(visual_scenes)} visual hints")
    return result
