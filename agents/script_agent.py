"""
Script Agent — generate 8-section long-form script.

Uses case data from Research Agent to write an accurate,
engaging 15-20 minute documentary script.
"""
from agents.llm import ask
from title_dna import get_title_prompt_insert


# A consistent narrator persona — the single biggest lever against the flat,
# encyclopedic "Wikipedia voice". Prepended to BOTH writing passes so the whole
# video sounds like ONE storyteller, not a summary.
NARRATOR_PERSONA = """【敘事者人格 — 整支影片必須是同一個說書人的聲音】
你是一個冷靜、克制、帶點低沉宿命感的真實犯罪說書人（不是亢奮的播報員，也不是百科條目）。
- 用「說一個真實發生過的黑暗故事」的口吻，而不是「條列資訊」。
- 多用具體的人、時間、地點、動作堆出「場景」來帶出事實；少用「根據資料顯示」「本案是…」這種百科句式。
- 短句製造節奏與壓迫感；在關鍵處停頓、留白。
- 冷靜的距離感，不煽情、不說教；讓事實本身的重量說話。
- 從開場到結語，語氣必須一致。
"""


def generate_script(case_data: dict) -> dict:
    """Generate a full long-form script based on researched case data."""
    topic = case_data.get("case_name", "")
    title_dna = get_title_prompt_insert()

    print(f"  [Script] Generating 8-section script...")

    # Pass 1: First 4 sections
    p1 = ask(f"""你是百萬訂閱犯罪紀實 YouTube 頻道的腳本作家。

{NARRATOR_PERSONA}
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

=== 檢索到的原始資料（細節來源；可用來豐富場景與血肉，讓敘事不像百科，但同樣不可超出此範圍編造）===
{(case_data.get('_grounding_corpus', '') or '')[:1800]}

=== 任務：生成前半部（4段，約 1300字 → 影片 7-8 分鐘）===
※ 2026-05-07 起改為 8-12 分鐘策略（光暗雜學館的甜蜜點），
   原 15-20 分鐘 retention 過低。短一點更易破 50% AVD。

【1. Hook（150-200字 / 影片 0-30 秒）】3-beat 結構必須遵守 — 這 30 秒決定觀眾留不留:

   ▲ Beat 1 (0-5秒, 約 25 字, 一句話)
     Cold-open punch — 一句衝擊宣言 + 直接給「最荒誕的單一事實」.
     不要鋪陳, 不要「大家好」, 不要「今天我們」開場.
     範例:
       ✓「為了一張購物卡, 媽媽把女兒交給惡魔.」
       ✓「他被關了 37 年, 然後 DNA 證明他是冤枉的.」
       ✓「39 個受過教育的大人, 集體相信糖果能治病.」
     ✗ 不要寫「在 1980 年的台北, 發生了一件…」(平鋪直敘扣分)

   ▲ Beat 2 (5-15秒, 約 60 字, 1-2 句)
     荒誕細節秀 + 具體數字 — 把案件中最不成比例的細節秀出來.
     必須包含: 數字 (人數/年數/金額) + 反差 (身份/結果) + 1 個 trigger word
     範例:
       「1996 年, 一個 21 歲的兵, 在他的軍營廁所被屍體發現. 軍方 24 小時就鎖定他, 屈打成招拿到自白. 15 年後, 真兇出來自首.」

   ▲ Beat 3 (15-30秒, 約 60 字, 2-3 句)
     承諾 + 訂閱誘餌 — 用「今天我帶你拆解…」/「接下來你會看到…」格式.
     必須具體說明影片會交代什麼 (時間線/真兇/動機/法律改變).
     結尾自然帶到「訂閱頻道」或「按鈴鐺」.
     範例:
       「今天我帶你看 1996 到 2011 這 15 年的時間線, 軍方為什麼這麼急著定罪, 真兇是怎麼跳出來的, 還有這個案子怎麼改寫了台灣的軍法. 訂閱頻道, 看完整《台灣冤案檔案》系列.」

   opening_card (≤8 字) 應該是 Beat 1 的核心字詞 (e.g.「37年冤獄」「39 個大人」),
   會以黑底大字呈現 0-1.5 秒.

   cold_open_text（15-25 字，可留空）：一句敘事感的冷開場 tagline，會在影片最開頭約 3 秒
   純黑、純靜音時出現（紀錄片式冷開場），比 opening_card 更長、更有畫面感.
   範例:「她殺了七個小孩，然後回到市場賣菜.」「血案那晚，警車來得太晚.」
   想不出夠有力的句子就回傳空字串，不要寫空泛的話.

【2. 背景（300-400字）】介紹受害者，建立情感連結
【3. 案件經過（400-500字）】時間線還原，短句製造緊張
【4. 調查過程（300-400字）】警方行動、線索、嫌疑人

【留住觀眾的「開放迴圈」規則 — 必須完全基於上方案件資料/時間線，不可編造新情節】
- 第 2 段（背景）最後一句用前導懸念收尾，暗示恐怖即將發生.
  例:「但沒有人知道，這只是噩夢的開始…」「然而那天等著她的，是她想都不敢想的事.」
- 第 3 段（案件經過）開頭第一句給一個二次鉤子：獎勵看到這裡的觀眾一個新的震撼反差事實.
- 第 4 段（調查過程）最後一句暗示轉折即將到來.
  例:「但警方在他家發現的東西，才是這案子真正可怕的地方…」

語言要求：繁體中文、台灣用語、短句、英文人名保留原文

⚠️⚠️⚠️ 事實底線（違反必須整段重寫）⚠️⚠️⚠️
1. **所有具體事實**(人名/年份/地點/數字/職業/案發過程)**只能來自上方的「案件資料」**
2. 不准自行加入 case_data 沒提供的人名、地名、年份、機構名稱
3. 不准混搭 — 不可把不同案件的細節組合成新故事
4. 若 case_data 某欄位是空 (e.g. victims=[])、模糊或不確定,**用模糊措辭**(「一名年輕人」「某縣市」),不要編造具體人名/地點
5. 寧可文采少 10%,也不要為了戲劇效果加未經查證的細節
6. 標題可以聳動但**不可虛構** — 「99%沒看懂」「真相顛覆想像」OK,「為求健康竟活活餓死親兒」必須案件確實有此情節才能用
7. 若你發現 case_data 內部矛盾或太薄弱,在 hook 第一句加一個 `[FACT_DOUBT]` 標記讓人類審查者知道

=== visual_hints 必須遵守的規則(2026-05-13 noir 升級)===
visual_hints 是 Imagen 生圖的 prompt,跟旁白文本不同要求:
1. **英文撰寫**(Imagen 中文識別差) — 每個 hint 12-25 字
2. **Oblique framing**:拍「殘留物 / 場所 / 物件」,**不要拍**「暴力動作 / 具體人物臉」
   ✓「empty tea house at night, overturned chair, police evidence markers, ceiling fan motionless」
   ✗「two men shooting each other」(safety filter 必擋)
3. **不要描述任何文字 / 招牌 / 報紙標題 / sign / marquee / billboard** — Imagen 會亂寫字產 typo
4. **不要描述特定人物**(no character, no face)— faceless 頻道 + 安全濾鏡
5. 風格已由 noir prefix 統一處理,你**不要**重複 "noir / cinematic / dark" — 只寫場景物件

回傳 JSON：
{{
  "title": "影片標題（使用標題DNA公式，30字以內）",
  "opening_card": "開場字卡（8字以內）",
  "cold_open_text": "15-25字敘事冷開場tagline（想不出就留空字串）",
  "sections": [
    {{"name": "hook", "script": "全文", "visual_hints": ["English oblique scene 1", "scene 2"]}},
    {{"name": "background", "script": "全文", "visual_hints": ["English oblique scene"]}},
    {{"name": "crime", "script": "全文", "visual_hints": ["English oblique scene"]}},
    {{"name": "investigation", "script": "全文", "visual_hints": ["English oblique scene"]}}
  ],
  "keywords_en": ["English Pexels search 1", "search 2", "...共20個"]
}}""")

    print(f"  [Script] Pass 1 done: {sum(len(s['script']) for s in p1.get('sections', []))} chars")

    # Pass 2: Last 4 sections
    sections_context = "\n".join(
        f"【{s['name']}】{s['script'][:150]}..." for s in p1.get("sections", []))

    p2 = ask(f"""{NARRATOR_PERSONA}
繼續生成後半部（4段，約 1000字）+ YouTube 描述欄。延續同一個說書人的聲音，語氣與前半部一致。

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

⚠️ visual_hints 沿用前半段規則:英文、oblique framing(物件+場所,非人物動作)、
   無文字/招牌、不描述特定人物、12-25 字/條.

回傳 JSON：
{{
  "sections": [
    {{"name": "twist", "script": "全文", "visual_hints": ["English oblique scene"]}},
    {{"name": "resolution", "script": "全文", "visual_hints": ["English oblique scene"]}},
    {{"name": "reflection", "script": "全文", "visual_hints": ["English oblique scene"]}},
    {{"name": "cta", "script": "全文", "visual_hints": ["English oblique scene"]}}
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
        "cold_open_text": p1.get("cold_open_text", ""),
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
