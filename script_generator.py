import anthropic
import json
import time
from config import ANTHROPIC_API_KEY, GEMINI_API_KEY

# Gemini (primary — free) + Claude (fallback — paid)
_gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        print("  [INFO] Gemini API ready (primary)")
    except Exception:
        pass

_claude_client = None
if ANTHROPIC_API_KEY:
    _claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT_ZH = """你是一位頂尖真實犯罪 YouTube 頻道的腳本作家，專門為繁體中文觀眾創作。

案件主題：{topic}

{title_dna}

⚠️ 真實性規則（最重要，違反會導致整集下架）
1. 所有人名、地名、日期、機構名必須是**真實存在、可被查證**的。不確定就不要寫。
2. **禁止捏造任何「引述」**（用「」或 "" 標記的當事人/警方/法官發言）— 除非是廣為流傳的公開紀錄原文。如果不確定原話，改用間接敘述：「據報導，警方表示...」
3. **禁止編造案件細節**：受害者人數、死因、兇器、判決結果必須準確。不確定就用模糊語氣（「據傳」「疑似」）。
4. **禁止混淆不同案件**的細節。每個案件獨立描述。
5. 數字（年份、人數、金額）必須準確。不確定就不要給具體數字。
6. 禁止為了戲劇效果而誇大或扭曲事實。震撼感應來自真實事件本身，不是編造。

=== 腳本結構要求 ===

【第一句：黃金3秒鐘 Hook】
- 必須在第一句話就讓觀眾停下來
- 用最震撼的事實、反差、或懸念開場
- 範例風格：「他殺了七個人，卻在每次審訊中都面帶微笑。」「這個城市沒有人知道，他們的鄰居已經是個殺人犯超過三十年了。」
- 禁止用「今天我們來聊聊...」「相信很多人都聽過...」等平淡開場

【段落節奏】（總長度 45-60 秒，字數控制在 180-220 字）
- 開場 hook（1-2句）：最震撼的事實，讓人無法滑走
- 核心事件（3-4句）：快節奏帶出案件經過，短句，每句最多10字
- 反轉/揭露（1-2句）：最高潮的一刻，讓觀眾屏氣
- 結尾（1句）：低沉有力，留下餘韻

【語言要求】
- 繁體中文，台灣用語
- 極短句（5-10字）製造節奏感，像在講緊張的故事
- 情緒性詞彙：「那個夜晚」「沒有人知道」「直到...」「更可怕的是」
- 關鍵停頓加「...」讓配音自然換氣
- 總字數 **180-220字**（60秒語速），絕對不能超過 230字
- 結尾自然感嘆，不要直接呼籲觀眾行動
- 【重要】英文人名、地名、機構名稱一律保留英文原文，不要音譯成中文
  例：寫「Ted Bundy」不寫「泰德邦迪」；「FBI」不寫「聯邦調查局」
  台灣本地人名地名用中文（如：鄭捷、台北捷運）
- 【重要】同時生成 opening_card：一句話（8字以內），比 title 更衝擊，
  用於影片開場前2秒的全黑字卡，要讓人看了立刻停止滑動
  範例：「他殺了30個女孩」「沒有人活著出來」「真相比你想的更可怕」

=== 分鏡節奏 ===
同時為剪輯師提供 8 個分鏡的節奏標記：
- "slow" = 4秒（背景鋪陳）
- "medium" = 3秒（一般劇情）
- "fast" = 2秒（緊張場面）
- "climax" = 1秒（最高潮瞬間）

請用以下 JSON 格式回傳：
{{
  "title": "影片標題：≤25字，必須是【hook句型】，製造好奇缺口。禁止冒號格式「案件名：說明」。範例：「她毒殺三任丈夫」「他預謀殺人六年」「這個孩子讓台灣沉默了」",
  "opening_card": "開場字卡文字（8字以內，比標題更衝擊，用於影片前2秒全黑字卡）",
  "script": "完整腳本內容（180-220字）",
  "ending_question": "結尾討論問題：一個具體的二選一或道德兩難問題，讓觀眾想留言回答。例：「你覺得她是含冤入獄，還是罪有應得？」不要用「大家怎麼看」這種空泛問法。",
  "pinned_comment": "置頂留言：一則補充案件冷知識或投票問題（50字以內），例：「這個案件其實還有一個從未公開的細節...你們想知道嗎？」",
  "keywords": ["搜尋素材用的英文關鍵字1", "關鍵字2", "關鍵字3"],
  "description": "YouTube 影片描述（60字以內，含案件名稱）",
  "hashtags": ["#真實犯罪", "#犯罪故事", "#懸案", "#Shorts", "#台灣"]
}}"""

PROMPT_EN = """You are a scriptwriter for a top-tier true crime YouTube channel targeting Taiwanese audiences.

Case topic: {topic}

=== SCRIPT STRUCTURE ===

【Opening Hook — First 3 Seconds】
- The very first sentence must make viewers stop scrolling
- Lead with the most shocking fact, a chilling contrast, or an unanswered question
- Example styles: "He killed seven people and smiled through every interrogation." / "For 30 years, his neighbors had no idea they lived next to a killer."
- NEVER open with "Today we're talking about..." or generic intros

【Paragraph Pacing】(Total 45-60 seconds, 150-180 words)
- Hook (1-2 sentences): Most shocking fact — stop the scroll
- Core events (3-4 sentences): Fast pace, max 10 words per sentence
- Reveal/twist (1-2 sentences): Peak moment, breathless
- Ending (1 sentence): Quiet, haunting

【Language】
- Very short sentences (5-10 words) for rhythm
- Emotional anchors: "That night", "No one knew", "Until...", "What made it worse"
- Add "..." at dramatic pauses for TTS breathing
- Total: **150-180 words** (60-second pace), never exceed 190 words
- End with quiet reflection, not a call-to-action

=== VISUAL SCENES (8 total, in narrative order) ===
Dark, crime-specific Pexels search queries.
At least 3 must use explicit crime imagery: blood drops, forensic evidence, police tape, interrogation, handcuffs, detective board.
Remaining: moody atmospheric shots matching the case location/era.
NEVER generic happy/neutral scenes.

=== SCENE PACING (8 values matching visual_scenes order) ===
- "slow" = 4s, "medium" = 3s, "fast" = 2s, "climax" = 1s

Return this exact JSON:
{{
  "title": "Catchy hook-style title (under 70 chars)",
  "opening_card": "Ultra-short shock phrase for opening title card (under 20 chars)",
  "script": "Full script (150-180 words)",
  "keywords": ["english keyword1", "keyword2", "keyword3"],
  "description": "YouTube description (under 120 chars)",
  "hashtags": ["#TrueCrime", "#CriminalMinds", "#TrueCrimeStory", "#Shorts"],
  "visual_scenes": ["scene 1", "... 8 total ..."],
  "scene_pacing": ["slow", "medium", "fast", "climax", "... 8 total ..."]
}}"""


PROMPT_ZH_REMOTION = """你是一位頂尖真實犯罪 YouTube 頻道的腳本作家，專門為繁體中文觀眾創作。
本次影片將由 Remotion 視覺引擎渲染，請直接產出結構化 Case JSON（非單段敘事）。

案件主題：{topic}

{title_dna}

⚠️ 真實性規則（最重要，違反會導致整集下架）
1. 所有人名、地名、日期、機構名必須是**真實存在、可被查證**的。不確定就不要寫。
2. **禁止捏造任何「引述」**（用「」或 "" 標記的當事人/警方/法官發言）— 除非是廣為流傳的公開紀錄原文。如果不確定原話，改用間接敘述：「據報導，警方表示...」
3. **禁止編造案件細節**：受害者人數、死因、兇器、判決結果必須準確。不確定就用模糊語氣（「據傳」「疑似」）。
4. **禁止混淆不同案件**的細節。每個案件獨立描述。
5. 數字（年份、人數、金額）必須準確。不確定就不要給具體數字。
6. 禁止為了戲劇效果而誇大或扭曲事實。震撼感應來自真實事件本身，不是編造。

=== 結構要求 ===
本案件將拆成 9 幕，每一幕獨立 TTS + 獨立靜態圖片：
  hook（震撼開場）/ setup（時空背景）/ events[固定 4 個] / twist（反轉揭露）/ aftermath（後續影響）/ cta（結尾呼籲）

【字數預算（繁體中文含標點）— 嚴格執行，超標會被系統退回重跑】
  hook      : 25–40 字（絕對上限 40）
  setup     : 20–35 字（絕對上限 35）
  每個 event: 15–30 字（絕對上限 30）
  twist     : 30–50 字（絕對上限 50）
  aftermath : 35–55 字（絕對上限 55）
  cta       : 8–15 字（絕對上限 15）
總計 **200–270 字**（≈50–65 秒語速 + 10秒呼吸間隔 = 60–75 秒成品）。
⚠️ 超過 280 字的稿件會被自動退回。寧可少一句也不要超標。精簡是力量。

【語言要求】
- 繁體中文、台灣用語。
- 短句為主（5–12 字），段落內節奏緊湊。
- 英文人名、地名、機構保留原文（Ted Bundy 不寫泰德邦迪；FBI 不寫聯邦調查局）。
- 台灣本地人名、地名用中文。
- 結尾自然收束，不要口號式呼籲。

【image_query 要求】
每一幕要配一個 English Pexels 搜尋詞（3-6 個字），用於抓靜態照片。
- 必須是犯罪相關或時代氛圍（例：`dark alley night rain`、`vintage crime scene photo`、`detective interrogation room 1960s`、`police tape forensic evidence`）。
- 禁止一般中性/快樂/自然風景（例：`beautiful sunset`、`happy family`）。
- 盡量對應本幕的具體場景。

【wiki_search_term】
1-3 個英文關鍵字，用於 Wikimedia Commons 歷史圖片備援（例：`Tokyo 1968 bank`、`Peng Wanru`）。

=== JSON 格式（請嚴格依此回傳，不要其他文字） ===
{{
  "id": "slug-格式（小寫英數+連字符），≤40 字，例：'tokyo-300m-yen'、'peng-wanru-case'",
  "title": "影片標題 ≤25 字。必須用以下 6 種 hook 句型之一（每次隨機選一種，避免重複）：A) 反差句「她救了全村的命，卻親手殺了自己的孩子」 B) 數字句「30年追查，0嫌犯」 C) 禁忌句「警察不敢公開的真相」 D) 倒敘句「他死後，秘密才被翻出來」 E) 質問句「冤案？還是完美犯罪？」 F) 身份句「鄰居眼中的好人，警方檔案裡的惡魔」。禁止用「案件名：說明」這種平鋪直敘格式。",
  "titleZh": "中文副標（畫面上顯示；不確定就跟 title 一樣）",
  "opening_card": "≤8 字衝擊字卡",
  "date": "案件主要日期，例：'1968年12月10日' 或 '1996年11月' 或 '1990年代'",
  "location": "案件地點，例：'東京都府中市' 或 '台北市' 或 '美國洛杉磯'",
  "status": "必須是 'unsolved' 或 'solved' 之一",
  "statusLabel": "中文狀態標籤：'未偵破' / '已破案' / '已伏法' / '冤案平反' 等",

  "hook": "25–40 字（上限 40 字！），**必須是觸發留言的爭議性問題**。目的：讓觀眾忍不住留言回答。模板（每次擇一）：A) 道德兩難「他活活燒死整家人，但被害者曾欺負他10年——你覺得他是兇手還是受害者？」 B) 共鳴提問「如果是你，敢替親人復仇嗎？」 C) 立場對立「這是冤案還是罪有應得？」 D) 預測題「兇手是A還是B？」 E) 假設題「如果你是法官，你會判他死刑嗎？」。禁止「今天我們來聊聊」這種平淡開場，禁止單純陳述事實不問問題。",
  "hook_image_query": "English Pexels query for hook",

  "setup": "20–35 字（上限 35 字！），時空背景與人物介紹",
  "setup_image_query": "English Pexels query for setup",

  "events": [
    {{"text": "15–30 字（上限 30 字！），事件 1", "image_query": "English query"}},
    {{"text": "15–30 字（上限 30 字！），事件 2", "image_query": "English query"}},
    {{"text": "15–30 字（上限 30 字！），事件 3", "image_query": "English query"}},
    {{"text": "15–30 字（上限 30 字！），事件 4", "image_query": "English query"}}
  ],

  "twist": "30–50 字（上限 50 字！），最高潮揭露",
  "twist_image_query": "English Pexels query for twist",

  "aftermath": "35–55 字（上限 55 字！），後續、調查結果、社會影響",
  "aftermath_image_query": "English Pexels query for aftermath",

  "cta": "**強制二元選擇格式**，必須符合「1：[選項A] 2：[選項B] 你選？」結構，**讓觀眾打 1 或 2** 即可留言（降低門檻）。例：「1：冤枉 2：活該 你選？」或「1：兇手 2：被陷害 留言1或2」或「1：贊成死刑 2：反對 你呢？」。字數 12-18 字。禁止開放式問題、禁止「追蹤看更多」。",

  "wiki_search_term": "Wikimedia 備援關鍵字（1-3 個英文字）",

  "ending_question": "跟案件直接相關的二選一或道德兩難問題，能引發爭論的最好。例：'你支持廢死嗎？' '這算正當防衛還是蓄意謀殺？'",
  "pinned_comment": "置頂留言（50字以內）：用投票式問題或補充冷知識引發討論。例：'你覺得兇手是A還是B？' '這個案件其實還有一個從未公開的細節...'",
  "keywords": ["english keyword1", "keyword2", "keyword3"],
  "description": "YouTube 描述 ≤60 字，含案件名稱",
  "hashtags": ["#真實犯罪", "#犯罪故事", "#懸案", "#Shorts", "#台灣"],
  "sources": ["此案件的 Wikipedia 頁面標題", "相關新聞報導或書籍（真實存在可查證的）"]
}}"""


def _validate_case_shape(result: dict) -> None:
    """Validate that a Claude/Gemini response matches the Case schema shape.

    Raises ValueError with a specific field description on any failure.
    Used by the Remotion engine path — MoviePy path uses _normalize_script_field.
    """
    import re as _re
    if not isinstance(result, dict):
        raise ValueError(f"Case must be dict, got {type(result).__name__}")

    required_strs = [
        "id", "title", "date", "location", "status", "statusLabel",
        "hook", "hook_image_query", "setup", "setup_image_query",
        "twist", "twist_image_query", "aftermath", "aftermath_image_query",
        "cta", "wiki_search_term",
    ]
    for k in required_strs:
        v = result.get(k, "")
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"Case field {k!r} missing or empty")

    if result["status"] not in ("unsolved", "solved"):
        raise ValueError(f"Case status must be 'unsolved' or 'solved', got {result['status']!r}")

    raw_id = result["id"]
    cleaned_id = _re.sub(r"[^a-z0-9-]+", "-", raw_id.lower()).strip("-")
    if len(cleaned_id) > 40:
        cleaned_id = cleaned_id[:40].rstrip("-")
    if not cleaned_id:
        raise ValueError(f"Case id is empty after sanitization, got {raw_id!r}")
    if cleaned_id != raw_id:
        print(f"  [INFO] Sanitized case id: {raw_id!r} -> {cleaned_id!r}")
    result["id"] = cleaned_id

    events = result.get("events")
    if not isinstance(events, list) or len(events) != 4:
        raise ValueError(f"Case events must be a 4-element list, got {type(events).__name__} len={len(events) if isinstance(events, list) else 'n/a'}")
    for i, ev in enumerate(events):
        if not isinstance(ev, dict):
            raise ValueError(f"events[{i}] must be dict")
        if not isinstance(ev.get("text"), str) or not ev["text"].strip():
            raise ValueError(f"events[{i}].text missing or empty")
        if not isinstance(ev.get("image_query"), str) or not ev["image_query"].strip():
            raise ValueError(f"events[{i}].image_query missing or empty")


# ── Character budget enforcement ─────────────────────────────────────────────

# Per-section hard limits (chars). Anything over → trim or retry.
_SECTION_CHAR_LIMITS = {
    "hook": 40, "setup": 35, "twist": 50, "aftermath": 55, "cta": 22,
    "event": 30,  # per event
}
_TOTAL_CHAR_HARD_CAP = 300  # absolute maximum across all sections


def _count_case_chars(case: dict) -> tuple[int, dict]:
    """Count Chinese characters per section. Returns (total, {section: count})."""
    counts = {}
    for sec in ("hook", "setup", "twist", "aftermath", "cta"):
        counts[sec] = len(case.get(sec, ""))
    for i, ev in enumerate(case.get("events", [])):
        counts[f"event-{i+1}"] = len(ev.get("text", ""))
    return sum(counts.values()), counts


def _trim_case_sections(case: dict) -> dict:
    """Trim overlong sections to their hard caps by cutting at the last
    sentence boundary (。！？…) within the limit. Mutates and returns case."""
    import re as _re

    def _trim(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        truncated = text[:limit]
        # Prefer sentence-ending punctuation
        m = list(_re.finditer(r'[。！？…）」]', truncated))
        if m:
            return truncated[:m[-1].end()]
        # Fall back to comma/semicolon boundary
        m = list(_re.finditer(r'[，；、]', truncated))
        if m:
            return truncated[:m[-1].end()]
        return truncated

    for sec in ("hook", "setup", "twist", "aftermath", "cta"):
        limit = _SECTION_CHAR_LIMITS.get(sec, 50)
        if sec in case:
            case[sec] = _trim(case[sec], limit)

    for ev in case.get("events", []):
        ev["text"] = _trim(ev["text"], _SECTION_CHAR_LIMITS["event"])

    return case


def _verify_sources(sources: list) -> list:
    """Verify LLM-provided sources are real. Check Wikipedia pages exist.

    Returns only the sources that could be verified, plus Wikipedia URLs
    for confirmed pages. Unverifiable sources are kept but marked.
    """
    import requests as _req

    if not sources:
        return []

    verified = []
    for src in sources:
        if not isinstance(src, str) or len(src) < 5:
            continue

        # Try to find it as a Wikipedia article
        try:
            resp = _req.get(
                "https://zh.wikipedia.org/w/api.php",
                params={"action": "query", "titles": src, "format": "json"},
                headers={"User-Agent": "AIvideoBot/1.0 (YouTube educational content)"},
                timeout=8,
            )
            if resp.status_code == 200:
                pages = resp.json().get("query", {}).get("pages", {})
                # Page ID > 0 means it exists; -1 means not found
                for pid, page in pages.items():
                    if int(pid) > 0:
                        title = page.get("title", src)
                        url = f"https://zh.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        verified.append(f"{title} — {url}")
                        print(f"  [source] ✓ Wikipedia: {title}")
                        break
                else:
                    # Not a Wikipedia page title — keep as-is
                    verified.append(src)
                    print(f"  [source] ~ Not on Wikipedia: {src[:40]}")
        except Exception:
            verified.append(src)

    return verified


def _get_recent_titles(days: int = 14) -> list[str]:
    """Load recent video titles from YouTube API to avoid duplicates."""
    import os
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from youtube_uploader import _get_credentials
        from googleapiclient.discovery import build
        creds = _get_credentials()
        if not creds:
            return []
        yt = build('youtube', 'v3', credentials=creds)
        # Get recent uploads from video_log
        if not os.path.exists("video_log.json"):
            return []
        with open("video_log.json") as f:
            data = json.load(f)
        recent_ids = [v["video_id"] for v in data.get("videos", [])[-30:]]
        if not recent_ids:
            return []
        resp = yt.videos().list(part="snippet", id=",".join(recent_ids[-50:])).execute()
        return [item["snippet"]["title"] for item in resp.get("items", [])]
    except Exception as e:
        print(f"  [WARN] Could not load recent titles: {e}")
        return []


def _normalize_script_field(result: dict) -> dict:
    """Gemini/Claude occasionally return the `script` field as a list of
    sentences instead of a single string (observed 2026-04-09 after DNA
    injection). Coerce to string so downstream file writes / TTS calls work.
    Same for `visual_scenes` and `scene_pacing` (should always be list, but
    be defensive)."""
    if not isinstance(result, dict):
        return result
    script = result.get("script", "")
    if isinstance(script, list):
        result["script"] = "\n".join(str(s) for s in script)
    elif not isinstance(script, str):
        result["script"] = str(script)
    return result


def generate_scripts(topic: str, fmt: str = "short", engine: str = "moviepy") -> dict:
    """Generate scripts.

    fmt='short' for Shorts, 'long' for 15-20 min videos.
    engine='moviepy' (default) uses the classic narrative prompt.
    engine='remotion' uses PROMPT_ZH_REMOTION to produce a Case-shaped JSON
      directly (see crime_reel_adapter.build_crime_reel).
    """
    if fmt == "long":
        return _generate_long_scripts(topic)

    from title_dna import get_title_prompt_insert
    title_dna = get_title_prompt_insert()

    if engine == "remotion":
        # Inject recent titles so LLM avoids duplicates
        recent_titles = _get_recent_titles(days=14)
        title_avoid = ""
        if recent_titles:
            titles_list = "、".join(f"「{t}」" for t in recent_titles[:15])
            title_avoid = f"\n⚠️ 以下標題已經用過，絕對不能重複或相似：{titles_list}\n"
        prompt = PROMPT_ZH_REMOTION.format(topic=topic, title_dna=title_dna + title_avoid)

        for attempt in range(2):
            label = "(retry) " if attempt else ""
            print(f"  {label}Generating Chinese script (Remotion Case schema)...")
            zh_result = _call_claude(prompt)
            _validate_case_shape(zh_result)

            total, counts = _count_case_chars(zh_result)
            print(f"  Character count: {total} ({', '.join(f'{k}={v}' for k, v in counts.items())})")

            if total <= _TOTAL_CHAR_HARD_CAP:
                break

            if attempt == 0:
                print(f"  [WARN] {total} chars exceeds cap {_TOTAL_CHAR_HARD_CAP}, retrying...")
                continue

            # Second attempt still over — trim to fit
            print(f"  [WARN] Still {total} chars after retry, trimming sections...")
            zh_result = _trim_case_sections(zh_result)
            total, counts = _count_case_chars(zh_result)
            print(f"  After trim: {total} chars ({', '.join(f'{k}={v}' for k, v in counts.items())})")

        print(f"  Generating English metadata...")
        en_result = _call_claude(PROMPT_EN.format(topic=topic))

        return {"zh": zh_result,
                "en": _normalize_script_field(en_result)}

    # MoviePy (classic narrative) path — unchanged.
    print(f"  Generating Chinese script...")
    zh_result = _call_claude(PROMPT_ZH.format(topic=topic, title_dna=title_dna))

    print(f"  Generating English script...")
    en_result = _call_claude(PROMPT_EN.format(topic=topic))

    return {"zh": _normalize_script_field(zh_result),
            "en": _normalize_script_field(en_result)}


def _generate_long_scripts(topic: str) -> dict:
    """Generate long-form 15-20 min script in 2 passes to stay within token limits."""
    from title_dna import get_title_prompt_insert, SECTION_NAMES

    title_dna = get_title_prompt_insert()

    # Pass 1: Title, metadata, and first 4 sections (hook → investigation)
    anti_fabrication = """
⚠️ 真實性規則（最重要，違反會導致整集下架）
1. 所有人名、地名、日期、機構名必須是**真實存在、可被查證**的。不確定就不要寫。
2. **禁止捏造任何「引述」**— 除非是廣為流傳的公開紀錄原文。不確定原話就用間接敘述（「據報導」「警方表示」）。
3. **禁止編造案件細節**：受害者人數、死因、兇器、判決結果必須準確。不確定就用模糊語氣（「據傳」「疑似」）。
4. **禁止混淆不同案件**的細節。
5. 數字（年份、人數、金額）必須準確。不確定就不要給具體數字。
6. 禁止為了戲劇效果而誇大或扭曲事實。震撼感應來自真實事件本身。"""

    prompt_p1 = f"""你是一位百萬訂閱的真實犯罪 YouTube 頻道腳本作家，專門製作 15-20 分鐘的深度犯罪紀實影片。

案件主題：{topic}

{title_dna}
{anti_fabrication}

=== 任務：生成影片前半部（約 2000 字） ===

請生成以下 4 個段落，每段要有明確的敘事節奏：

【1. 案件開場 Hook（200-300字）】
- 從最震撼的一刻開始，讓觀眾無法離開
- 可以從案件的結局倒敘，或從發現屍體的那一刻開始
- 製造懸念：「但沒有人知道，這只是恐怖的開始...」

【2. 人物背景（400-600字）】
- 介紹受害者的人生、家庭、性格，讓觀眾產生情感連結
- 介紹案件發生的時代背景和地點
- 建立「這是一個正常人」的印象，讓之後的悲劇更有衝擊力
- ⚠️ 段落最後一句必須是 **open loop（前導懸念）**：用一句話暗示接下來會發生可怕的事，讓觀眾不敢離開。
  範例：「但沒有人知道，這只是噩夢的開始...」「然而，那天晚上等待她的，是她想都不敢想的事。」「一切看似正常——直到那通電話響起。」

【3. 案件經過（600-800字）】
- 詳細的時間線還原：什麼時候、在哪裡、發生了什麼
- 用短句製造緊張感
- 加入感官細節（天氣、時間、聲音）讓觀眾身歷其境
- 開頭第一句要是一個 **secondary hook（二次鉤子）**：獎勵看到這裡的觀眾，給他們一個新的震撼事實或反差，而不是平淡的「接下來發生了什麼」

【4. 調查過程（500-700字）】
- 警方怎麼介入的、初步發現了什麼
- 有哪些嫌疑人、哪些線索
- 在這裡製造「似乎快要破案了...」的期待感
- 在段落中間加一句互動引導：「看到這裡，你覺得兇手會是誰？」
- ⚠️ 段落最後一句必須是 **open loop（前導懸念）**：暗示轉折即將來臨。
  範例：「但警方在他家發現的東西，才是這起案件真正可怕的地方...」「所有人都以為真相已經揭曉——直到那份報告出爐。」

=== 語言要求 ===
- 繁體中文，台灣用語
- 短句優先（5-12字），段落間自然過渡
- 英文人名地名保留原文（Ted Bundy 不寫泰德邦迪）
- 台灣本地人名地名用中文
- 每個段落結尾都要有 hook 讓觀眾想繼續看

=== 分鏡節奏（每段不同，製造動態感）===
每段的 visual_scenes 必須搭配 scene_pacing 陣列。不同段落用不同預設節奏：
  - hook: 大多 "fast"+"climax"（衝擊感）
  - background: 大多 "slow"+"medium"（鋪陳）
  - crime: 混合 "fast"+"medium"+"climax"（緊張推進）
  - investigation: "medium"+"slow"（沉穩偵查）

請用 JSON 格式回傳：
{{
  "title": "影片標題（使用上方標題 DNA 公式，≤25字，絕對不超過30字）",
  "opening_card": "開場字卡（8字以內，最衝擊的一句話）",
  "date": "案件主要日期，例：'1968年12月10日' 或 '1996年11月'",
  "location": "案件地點，例：'台北市' 或 '東京都'",
  "sections": [
    {{"name": "hook", "script": "案件開場全文", "visual_scenes": ["Pexels搜尋1", "搜尋2", "...共6個"], "scene_pacing": ["fast","climax","fast","medium","fast","climax"]}},
    {{"name": "background", "script": "人物背景全文", "visual_scenes": ["共6個"], "scene_pacing": ["slow","medium","slow","medium","slow","medium"]}},
    {{"name": "crime", "script": "案件經過全文", "visual_scenes": ["共8個"], "scene_pacing": ["medium","fast","fast","climax","fast","medium","fast","climax"]}},
    {{"name": "investigation", "script": "調查過程全文", "visual_scenes": ["共6個"], "scene_pacing": ["medium","slow","medium","slow","medium","slow"]}}
  ],
  "thumbnail_visual_hint": "縮圖背景場景描述（英文，30字以內）。描述一個跟案件相關的具體視覺：人物剪影、關鍵物品、犯罪現場氛圍。例：'blurry silhouette of woman in dark alley with red phone booth' 或 'abandoned warehouse at night with police car lights'。不要寫文字/標題，只描述畫面。",
  "keywords": ["英文搜尋關鍵字1", "關鍵字2", "關鍵字3", "關鍵字4", "關鍵字5"],
  "description": "YouTube 影片描述（100字以內）",
  "hashtags": ["#真實犯罪", "#犯罪紀實", "#懸案", "#深度解析", "#台灣"],
  "sources": [
    "此案件的 Wikipedia 頁面標題（中文或英文皆可，必須是真實存在的頁面）",
    "相關新聞報導或書籍名稱（必須是真實存在、可被 Google 搜尋到的）",
    "其他參考資料（法院判決書、紀錄片名稱等）"
  ]
}}"""

    print(f"  Generating long-form script (pass 1/2: sections 1-4)...")
    p1_result = _call_claude(prompt_p1, max_tokens=6000)

    # Extract first 4 sections for context
    sections_context = ""
    for s in p1_result.get("sections", []):
        sections_context += f"\n【{SECTION_NAMES.get(s['name'], s['name'])}】\n{s['script'][:200]}...\n"

    # Pass 2: Last 4 sections (twist → CTA)
    prompt_p2 = f"""你是一位百萬訂閱的真實犯罪 YouTube 頻道腳本作家。

案件主題：{topic}
影片標題：{p1_result.get('title', topic)}
{anti_fabrication}

=== 前半部摘要（已完成）===
{sections_context}

=== 任務：生成影片後半部（約 1500-2000 字）===

請接續前半部，生成以下 4 個段落：

【5. 關鍵轉折（400-500字）】
- 案件出現意外發展：新證據、假線索被推翻、意外目擊者
- 這是影片的最高潮，節奏要最快
- 讓觀眾感到「原來不是這樣的！」

【6. 結局揭曉（400-600字）】
- 如果破案：兇手是誰、怎麼被抓到、審判結果
- 如果未破案：目前最有力的理論、為什麼破不了
- 揭露動機：兇手為什麼這樣做

【7. 案件反思（200-300字）】
- 這個案件對社會造成了什麼影響
- 法律有因此改變嗎
- 留下一個讓觀眾思考的問題

【8. 結語（100-150字）】
- 結尾用一個具體的「二選一」或「道德兩難」問題收尾，讓觀眾想留言
- 例：「你覺得他是真兇，還是被冤枉的？」「如果你是法官，你會判死刑嗎？」
- 不要用「大家怎麼看」這種空泛收尾
- 然後自然帶出「訂閱頻道看更多案件」

=== 同時生成 Shorts 候選片段 ===
從整部影片中挑出 2-3 個最有戲劇張力的 200 字段落，適合截取為獨立的 60 秒 Shorts。

請用 JSON 格式回傳：
{{
  "sections": [
    {{"name": "twist", "script": "關鍵轉折全文", "visual_scenes": ["共6個"], "scene_pacing": ["fast","fast","climax","fast","medium","climax"]}},
    {{"name": "resolution", "script": "結局揭曉全文", "visual_scenes": ["共6個"], "scene_pacing": ["medium","slow","medium","slow","medium","slow"]}},
    {{"name": "reflection", "script": "案件反思全文", "visual_scenes": ["共4個"], "scene_pacing": ["slow","medium","slow","medium"]}},
    {{"name": "cta", "script": "結語全文", "visual_scenes": ["共2個"], "scene_pacing": ["slow","slow"]}}
  ],
  "ending_question": "結尾討論問題：一個具體的二選一或道德兩難問題。例：「你覺得她是含冤入獄，還是罪有應得？」",
  "pinned_comment": "置頂留言：補充一個案件冷知識或投票問題（50字以內）",
  "shorts_candidates": [
    {{"title": "Shorts標題", "script": "200字以內的獨立片段", "section_source": "twist"}},
    {{"title": "Shorts標題2", "script": "200字以內", "section_source": "hook"}}
  ]
}}"""

    print(f"  Generating long-form script (pass 2/2: sections 5-8)...")
    p2_result = _call_claude(prompt_p2, max_tokens=6000)

    # Merge results
    all_sections = p1_result.get("sections", []) + p2_result.get("sections", [])
    # Verify sources — check if cited Wikipedia pages exist
    sources = p1_result.get("sources", [])
    verified_sources = _verify_sources(sources)

    merged = {
        "title": p1_result.get("title", topic),
        "opening_card": p1_result.get("opening_card", ""),
        "sections": all_sections,
        "keywords": p1_result.get("keywords", []),
        "description": p1_result.get("description", ""),
        "hashtags": p1_result.get("hashtags", []),
        "shorts_candidates": p2_result.get("shorts_candidates", []),
        "sources": verified_sources,
        "format": "long",
    }

    # Build flat script and visual_scenes for backward compatibility.
    # Coerce each section's script to string first in case Gemini returned
    # list-of-sentences (observed 2026-04-09 after DNA injection).
    def _as_str(x):
        if isinstance(x, list):
            return "\n".join(str(s) for s in x)
        return str(x) if not isinstance(x, str) else x
    merged["script"] = "\n\n".join(_as_str(s.get("script", "")) for s in all_sections)
    for s in all_sections:
        s["script"] = _as_str(s.get("script", ""))
    merged["visual_scenes"] = []
    merged["scene_pacing"] = []
    for s in all_sections:
        scenes = s.get("visual_scenes", [])
        merged["visual_scenes"].extend(scenes)
        # Use per-section scene_pacing if Claude provided it; fallback to
        # section-type defaults for backward compatibility.
        section_pacing = s.get("scene_pacing", [])
        if len(section_pacing) >= len(scenes):
            merged["scene_pacing"].extend(section_pacing[:len(scenes)])
        else:
            pacing_defaults = {
                "hook": "fast", "background": "slow",
                "crime": "fast", "investigation": "medium",
                "twist": "fast", "resolution": "medium",
                "reflection": "slow", "cta": "slow",
            }
            default_pace = pacing_defaults.get(s["name"], "medium")
            merged["scene_pacing"].extend([default_pace] * len(scenes))

    total_chars = len(merged["script"])
    print(f"  Long-form script: {total_chars} chars, {len(all_sections)} sections, "
          f"{len(merged['visual_scenes'])} scenes")

    return {"zh": merged, "en": merged}  # en = same as zh for now


def _call_claude(prompt: str, max_tokens: int = 2500) -> dict:
    """Call LLM: try Gemini first (free), fallback to Claude (paid)."""
    # Try Gemini first
    if _gemini_client:
        try:
            return _call_gemini(prompt)
        except Exception as e:
            print(f"  [WARN] Gemini failed: {e}, falling back to Claude...")

    # Fallback to Claude
    if not _claude_client:
        raise RuntimeError("No LLM available (Gemini failed, Claude not configured)")

    models = ["claude-sonnet-4-6", "claude-opus-4-6"]
    for model in models:
        for attempt in range(3):
            try:
                message = _claude_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                print(f"  [INFO] Used Claude {model}")
                content = message.content[0].text
                start = content.find("{")
                end = content.rfind("}") + 1
                return json.loads(content[start:end])
            except anthropic.APIStatusError as e:
                if e.status_code in (400, 500, 529):
                    wait = 20 * (attempt + 1)
                    print(f"  [WARN] {model} error {e.status_code}, retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        print(f"  [WARN] {model} failed after 3 retries, trying next...")
    raise RuntimeError("All LLM models failed")


def _call_gemini(prompt: str) -> dict:
    """Call Gemini API and parse JSON response."""
    gemini_models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    for model in gemini_models:
        for attempt in range(2):
            try:
                # Bug #4 fix: Gemini has no built-in request timeout.
                # Use config.http_options or wrap with signal alarm.
                response = _gemini_client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "http_options": {"timeout": 120_000},  # 120s max
                    },
                )
                content = response.text
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(content[start:end])
                    print(f"  [INFO] Used Gemini {model}")
                    return result
                raise ValueError("No JSON found in Gemini response")
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    print(f"  [WARN] Gemini {model} rate limited, waiting 20s...")
                    time.sleep(20)
                    continue
                if attempt == 1:
                    raise
                print(f"  [WARN] Gemini {model} error: {e}, retrying...")
                time.sleep(5)
    raise RuntimeError("All Gemini models failed")
