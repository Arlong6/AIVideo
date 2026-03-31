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

=== 任務：生成前半部（4段，約 2000字）===

【1. Hook（200-300字）】從最震撼的事實開始
【2. 背景（400-600字）】介紹受害者，建立情感連結
【3. 案件經過（600-800字）】時間線還原，短句製造緊張
【4. 調查過程（500-700字）】警方行動、線索、嫌疑人

語言要求：繁體中文、台灣用語、短句、英文人名保留原文

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

    p2 = ask(f"""繼續生成後半部（4段，約 1500字）。

案件：{case_data.get('case_name', '')}
前半部摘要：{sections_context}

【5. 轉折（400-500字）】意外發展、新證據
【6. 結局（400-600字）】破案/未破案、審判結果
【7. 反思（200-300字）】社會影響、法律改變
【8. 結語（100-150字）】留下餘韻、呼籲訂閱

同時選出 2-3 個最適合截取為 Shorts 的精彩段落。

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
  ]
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
        "description": case_data.get("summary", ""),
        "hashtags": ["#真實犯罪", "#犯罪紀實", "#懸案", "#深度解析", "#台灣"],
        "shorts_candidates": p2.get("shorts_candidates", []),
        "format": "long",
    }

    total = len(full_script)
    print(f"  [Script] Complete: {total} chars, {len(all_sections)} sections, "
          f"{len(visual_scenes)} visual hints")
    return result
