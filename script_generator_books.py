"""
Script Generator — books channel (Route B: narrative-driven book storytelling).

Long-form only (books channel is long-form primary). Mirrors the structure of
script_generator._generate_long_scripts — same 8-section 2-pass pattern, same
JSON output shape — so the downstream pipeline (tts, assembler, uploader)
doesn't know it's processing a books video.

The key differences from the crime version:
- Role framing: narrative-driven book storytelling instead of true crime docs
- DNA source: title_dna_books (5 文森 hook patterns + 1 英雄 historical pattern)
- Section semantics: same 8 slots, different labels (SECTION_NAMES_BOOKS)
- Tone: dramatic retelling of book-sourced events, book as authority anchor
- Visual scenes: historical figures + book-themed Pexels stock instead of crime scenes
- CTA: book title anchor + subscribe, no "留言告訴我你的看法" forensics talk

Reuses `_call_claude` / `_call_gemini` from script_generator since LLM plumbing
is channel-agnostic.
"""
import json

# Reuse shared LLM plumbing so we have one set of retries, fallbacks, and
# token-cap logic instead of duplicating it per channel.
from script_generator import _call_claude


def generate_book_scripts(topic: str) -> dict:
    """Generate a long-form (15-20 min) book-storytelling script in 2 passes.

    Returns the same JSON shape as script_generator._generate_long_scripts
    so video_assembler, tts_generator, and youtube_uploader work unchanged.

    Parameters
    ----------
    topic : str
        Topic string, ideally formatted as "事件/人物：一句描述｜《書名》"
        (this is how topic_manager_books seeds entries).
    """
    from title_dna_books import get_title_prompt_insert, SECTION_NAMES_BOOKS

    title_dna = get_title_prompt_insert()
    S = SECTION_NAMES_BOOKS  # alias for prompt interpolation

    # ── Pass 1: Title, metadata, and first 4 sections ─────────────────────────
    prompt_p1 = f"""你是一位百萬訂閱的華語故事化說書 YouTube 頻道腳本作家，專門製作 15-20 分鐘的深度紀實影片。

這個頻道的定位特別 — 不是書評、不是書單、不是摘要。
而是挑選「一本真實存在的書 + 一個戲劇化的歷史事件/人物/事件」，
用紀錄片敘事節奏重現故事本身，把書當作權威錨點與資料來源。

你的風格參考：
- 英雄說書的「反直覺歷史揭密」敘事節奏
- 真實犯罪紀錄片的「戲劇化重現 + 懸念推進」
- 文森說書的「痛苦場景 hook + 個人情感背書」

題材：{topic}

{title_dna}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 禁止虛構（最重要的規則，違反會導致整集下架）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **書名必須 100% 使用題材中已經給定的書**（題材格式「故事描述｜《書名》by 作者」）
   禁止創造、改寫、擴充、或縮短書名。一個字都不能改。
2. **作者必須與題材給定的作者完全一致**，禁止編造共同作者或譯者名字。
3. **禁止虛構任何「直接引述」**（用「」或""標記的當事人發言）—
   除非這段話是公開歷史紀錄（例如羅斯福總統的公開演說），否則請改寫成間接描述。
   ✗ 錯誤：Rockefeller 說：「寧願錯過一點漲幅，也不願萬劫不復。」
   ✓ 正確：Rockefeller 的財務顧問後來回憶，他當時反覆強調風險管理的重要性。
4. **不確定的歷史細節一律保守處理**：
   - 若不確定某人某句話是否真的說過 → 不要引用
   - 若不確定某個事件的確切日期 → 用「那個冬天」「幾週後」代替精確日期
   - 若不確定某個人物的具體經歷 → 只描述公開紀錄中的事實
5. **不要偽造次要歷史學家、研究者、專家的名字**。如果需要引述「一位歷史學家」，
   就說「後來的歷史學家」或「後世研究者」，不要硬安一個名字上去。
6. 所有人名、地名、機構、日期、事件必須是**真實存在、可被 Google 驗證**的。

如果你不知道某個細節，**省略它、繞過它、改寫它**，絕對不要編造。
寧可敘事單薄一點，也不要出現假資訊。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

=== 任務：生成影片前半部（約 2000 字） ===

注意：這個題材的「一個事件 + 一本書」結構很重要 — 開場要從事件本身切入（不是從書開始），
把書名留到後半部的「書中洞察」段落才正式揭曉與引用。前半部書只是若隱若現的線索。

請生成以下 4 個段落，每段要有明確的敘事節奏：

【1. {S['hook']}（200-300字）】
- 從整個故事中最戲劇化的一刻開始 — 可以是關鍵決定的前一秒、重大事件發生的那個瞬間、或顛覆常識的一個事實
- 使用標題 DNA 的「痛苦場景體」或「歷史揭謊體」風格起 hook
- 不要一開始就介紹書名、作者、或「今天我們來聊...」這種平淡開場
- 結尾製造懸念：「但這個故事的真相，比任何人想像的都還要 __」

【2. {S['background']}（400-600字）】
- 鋪陳時代背景：那個年代長什麼樣子？社會氛圍是什麼？
- 介紹故事的主角 / 關鍵人物：他們是誰、過著什麼日常、他們在想什麼
- 建立「這是一個正常人 / 這是一個正常時代」的對比，讓後面的轉折有衝擊力
- 感官細節讓觀眾能「身歷其境」：顏色、氣味、聲音、天氣

【3. {S['crime']}（600-800字）】
- 還原事件經過 — 什麼時候、在哪裡、發生了什麼
- 用短句製造緊張感（5-12 字優先）
- 加入時間標記：「那是 1929 年 10 月 24 日的早上」「距離崩盤只剩 17 小時」
- 故事必須基於真實歷史，不要編造細節；若不確定就保守描述

【4. {S['investigation']}（500-700字）】
- 事件之後，人們如何揭露、調查、或理解這件事？
- 哪些證據被發現、哪些紀錄被保留、哪些當事人開口說了什麼
- 這裡可以開始「提到一份關鍵史料 / 一本正在被寫的書」當作伏筆（但還不要點出書名）
- 結尾製造「似乎快要找到答案了…但真相還有一層」的期待感

=== 語言要求 ===
- 繁體中文，台灣用語
- 短句優先（5-12 字），段落間自然過渡
- 英文人名、地名、機構名稱保留英文原文（例：寫「Rockefeller」不寫「洛克斐勒」）
- 台灣本地人名地名用中文
- 禁止學術腔、禁止列點式摘要（「以下三個重點...」）
- 每個段落結尾都要有 hook 讓觀眾想繼續看

=== visual_scenes 格式要求（非常重要）===
每個 visual_scenes 元素是一句**英文的視覺畫面描述**，會被直接餵進 AI 插圖生成器。
必須遵守：
- **只能用英文**，不要中文
- **描述畫面本身**，不是搜尋關鍵字
- **不要加「Pexels」「Wiki」「photo of」「archival footage」「stock」**這類來源標籤
- **不要寫「iconic photo of」「historical footage of」**這種會讓 AI 去生成照片的詞
- 每句 15-30 個單字，包含具體人物、場景、光線、動作
- 範例 ✓：「Winston Churchill at his desk in dim underground bunker, cigar smoke, maps spread out, 1940 London」
- 範例 ✓：「Soldiers marching through bombed European city streets, rubble and smoke, dramatic overcast sky」
- 範例 ✗：「Pexels/Wiki: Churchill photo」
- 範例 ✗：「1940 倫敦街景」（中文不行）
- 範例 ✗：「Archival footage of German tanks」（「archival footage」會讓 AI 生成照片，不是插圖）

請用 JSON 格式回傳：
{{
  "title": "影片標題（使用上方標題 DNA 公式，30 字以內，必須包含一個戲劇性 hook）",
  "opening_card": "開場字卡（8 字以內，最衝擊的一句話）",
  "sections": [
    {{"name": "hook", "script": "震撼開場全文", "visual_scenes": ["English scene description 1", "...共 6 個"]}},
    {{"name": "background", "script": "時代背景全文", "visual_scenes": ["共 6 個，全英文"]}},
    {{"name": "crime", "script": "關鍵事件全文", "visual_scenes": ["共 8 個，全英文"]}},
    {{"name": "investigation", "script": "揭密調查全文", "visual_scenes": ["共 6 個，全英文"]}}
  ],
  "keywords": ["英文搜尋關鍵字 1", "關鍵字 2", "關鍵字 3", "關鍵字 4", "關鍵字 5"],
  "description": "YouTube 影片描述（100 字以內，要提到題材 + 參考書名）",
  "hashtags": ["#說書", "#歷史故事", "#人物傳記", "#深度解析", "#台灣"]
}}"""

    print(f"  Generating books long-form script (pass 1/2: sections 1-4)...")
    p1_result = _call_claude(prompt_p1, max_tokens=6000)

    # Build context for Pass 2
    sections_context = ""
    for s in p1_result.get("sections", []):
        label = S.get(s["name"], s["name"])
        sections_context += f"\n【{label}】\n{s['script'][:200]}...\n"

    # ── Pass 2: Last 4 sections (twist → CTA) ─────────────────────────────────
    prompt_p2 = f"""你是一位百萬訂閱的華語故事化說書 YouTube 頻道腳本作家。

題材：{topic}
影片標題：{p1_result.get('title', topic)}

=== 前半部摘要（已完成）===
{sections_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 禁止虛構（再次強調）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 後半部會正式引用題材中給定的書與作者 — 必須與題材字串完全一致，禁止改寫
- 禁止虛構作者的其他著作、學歷、獎項、出版社
- 禁止虛構書中的「直接引述」段落
- 若不確定書的某個具體觀點，用「書中討論了...」這種保守描述，不要編造
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

=== 任務：生成影片後半部（約 1500-2000 字）===

請接續前半部，生成以下 4 個段落：

【5. {S['twist']}（400-500字）】
- 故事出現意外發展：新證據被發現、假線索被推翻、當事人承認了某件事、或歷史紀錄被解密
- 這是影片的最高潮，節奏要最快
- 讓觀眾感到「原來不是這樣的！」
- 此時可以提到「一位歷史學家在寫一本書時，發現了 __」作為書名伏筆

【6. {S['resolution']}（400-600字）】
- 故事的最終結局：後來怎麼樣了？當事人的命運？事件的長期影響？
- 如果是歷史事件：法律、社會、權力結構如何因此改變
- 如果是人物傳記：主角的最後歲月、身後評價、對後世的影響
- 節奏從高潮緩緩降下，語氣轉為回顧與沉澱

【7. {S['reflection']}（300-400字）— 這是本頻道的靈魂段落】
- **這裡正式引用「那本書」—** 第一次正式點出書名、作者、出版年
- 說明書中最核心的洞察（1-2 個觀點），以及這個洞察如何重新詮釋整個故事
- 為什麼這本書值得讀？它教會我們什麼連當事人都沒意識到的事？
- 留下一個讓觀眾思考的問題或金句

【8. {S['cta']}（100-150字）】
- 以書名作為錨點收尾（例：「如果你想更深入這個故事，這本書值得你花一個週末讀完」）
- 自然地引導訂閱：「如果你喜歡這種用一本書重現一段歷史的故事，別忘了訂閱」
- 禁止硬推、禁止列 call-to-action 三連

=== 同時生成 Shorts 候選片段 ===
從整部影片中挑出 2-3 個最有戲劇張力的 200 字段落，適合截取為獨立的 60 秒 Shorts。
優先挑選「hook 段落」和「轉折段落」，不要挑「書中洞察」段落（Shorts 觀眾看不完書名引用）。

=== visual_scenes 要求（再次強調）===
- 全部英文、每句 15-30 字
- 描述畫面，禁止「Pexels」「Wiki」「photo of」「archival footage」「stock」前綴
- 禁止中文
- 具體場景 + 人物動作 + 光線

請用 JSON 格式回傳：
{{
  "sections": [
    {{"name": "twist", "script": "意外轉折全文", "visual_scenes": ["English description 1", "...共 6 個"]}},
    {{"name": "resolution", "script": "結局揭曉全文", "visual_scenes": ["共 6 個，全英文"]}},
    {{"name": "reflection", "script": "書中洞察全文", "visual_scenes": ["共 4 個，全英文"]}},
    {{"name": "cta", "script": "結語書錨全文", "visual_scenes": ["共 2 個，全英文"]}}
  ],
  "shorts_candidates": [
    {{"title": "Shorts 標題", "script": "200 字以內獨立片段", "section_source": "twist"}},
    {{"title": "Shorts 標題 2", "script": "200 字以內", "section_source": "hook"}}
  ]
}}"""

    print(f"  Generating books long-form script (pass 2/2: sections 5-8)...")
    p2_result = _call_claude(prompt_p2, max_tokens=6000)

    # ── Merge both passes into the same output shape as crime _generate_long_scripts
    all_sections = p1_result.get("sections", []) + p2_result.get("sections", [])
    merged = {
        "title": p1_result.get("title", topic),
        "opening_card": p1_result.get("opening_card", ""),
        "sections": all_sections,
        "keywords": p1_result.get("keywords", []),
        "description": p1_result.get("description", ""),
        "hashtags": p1_result.get("hashtags", ["#說書", "#歷史故事", "#Shorts"]),
        "shorts_candidates": p2_result.get("shorts_candidates", []),
        "format": "long",
        "channel": "books",
    }

    # Flat fields for backward compatibility with video_assembler
    merged["script"] = "\n\n".join(s["script"] for s in all_sections)
    merged["visual_scenes"] = []
    merged["scene_pacing"] = []
    for s in all_sections:
        scenes = s.get("visual_scenes", [])
        merged["visual_scenes"].extend(scenes)
        # Pacing: book videos are more reflective than crime, so slow-medium bias
        pacing_map = {
            "hook": "fast",
            "background": "slow",
            "crime": "medium",
            "investigation": "medium",
            "twist": "fast",
            "resolution": "medium",
            "reflection": "slow",     # reflection gets the calm beat
            "cta": "slow",
        }
        default_pace = pacing_map.get(s["name"], "medium")
        merged["scene_pacing"].extend([default_pace] * len(scenes))

    total_chars = len(merged["script"])
    print(f"  Books long-form script: {total_chars} chars, "
          f"{len(all_sections)} sections, {len(merged['visual_scenes'])} scenes")

    # Same zh/en shape as crime version (en mirrors zh for now — books channel
    # is繁中-only per product decision).
    return {"zh": merged, "en": merged}
