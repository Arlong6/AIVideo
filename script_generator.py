import anthropic
import json
import time
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PROMPT_ZH = """你是一位頂尖真實犯罪 YouTube 頻道的腳本作家，專門為繁體中文觀眾創作。

案件主題：{topic}

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
  "title": "影片標題：必須是【hook句型】，製造好奇缺口讓觀眾忍不住點進來，12字以內。句型範例：「她毒殺三任丈夫，沒人懷疑她」「他預謀殺人六年，警察卻先找到他」「FBI追了30年，兇手竟然是...」「這個孩子，讓整個台灣沉默了」禁止使用冒號格式如「案件名：說明」",
  "opening_card": "開場字卡文字（8字以內，比標題更衝擊，用於影片前2秒全黑字卡）",
  "script": "完整腳本內容（180-220字）",
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


def generate_scripts(topic: str) -> dict:
    """Generate both Chinese and English scripts for a given topic."""
    print(f"  Generating Chinese script...")
    zh_result = _call_claude(PROMPT_ZH.format(topic=topic))

    print(f"  Generating English script...")
    en_result = _call_claude(PROMPT_EN.format(topic=topic))

    return {"zh": zh_result, "en": en_result}


def _call_claude(prompt: str) -> dict:
    models = ["claude-opus-4-6", "claude-sonnet-4-6"]
    for model in models:
        for attempt in range(3):
            try:
                message = client.messages.create(
                    model=model,
                    max_tokens=2500,
                    messages=[{"role": "user", "content": prompt}],
                )
                if model != "claude-opus-4-6":
                    print(f"  [INFO] Used fallback model: {model}")
                content = message.content[0].text
                start = content.find("{")
                end = content.rfind("}") + 1
                return json.loads(content[start:end])
            except anthropic.APIStatusError as e:
                if e.status_code in (500, 529):
                    wait = 20 * (attempt + 1)
                    print(f"  [WARN] {model} error {e.status_code}, retrying in {wait}s... (attempt {attempt+1}/3)")
                    time.sleep(wait)
                else:
                    raise
        print(f"  [WARN] {model} failed after 3 retries, trying next model...")
    raise RuntimeError("All Claude models overloaded")
