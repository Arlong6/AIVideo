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

【段落節奏】
- 段落1（背景）：建立懸疑感，讓人想繼續看
- 段落2（事件經過）：節奏加快，短句為主，製造緊張感
- 段落3（關鍵轉折）：最高潮，讓人喘不過氣
- 段落4（結尾）：低沉收尾，留下迴盪感，像夜晚一個人在想這件事

【語言要求】
- 繁體中文，台灣用語
- 短句優先（5-12字）製造節奏感
- 情緒性詞彙：「那個夜晚」「沒有人知道」「直到...」「更可怕的是」
- 關鍵停頓加「...」讓配音自然換氣
- 總字數 480-560字（3分鐘語速）
- 結尾自然感嘆，不要直接呼籲觀眾行動

=== 分鏡節奏 ===
同時為剪輯師提供 15 個分鏡的節奏標記，對應 visual_scenes 的順序：
- "slow" = 5秒（敘述、背景鋪陳）
- "medium" = 4秒（一般劇情推進）
- "fast" = 2.5秒（緊張、動作場面）
- "climax" = 1.5秒（最高潮瞬間）

請用以下 JSON 格式回傳：
{{
  "title": "影片標題（吸引人，含關鍵字，15字以內）",
  "script": "完整腳本內容",
  "keywords": ["搜尋素材用的英文關鍵字1", "關鍵字2", "關鍵字3"],
  "description": "YouTube 影片描述（60字以內，含案件名稱）",
  "hashtags": ["#真實犯罪", "#犯罪故事", "#懸案"]
}}"""

PROMPT_EN = """You are a scriptwriter for a top-tier true crime YouTube channel targeting Taiwanese audiences.

Case topic: {topic}

=== SCRIPT STRUCTURE ===

【Opening Hook — First 3 Seconds】
- The very first sentence must make viewers stop scrolling
- Lead with the most shocking fact, a chilling contrast, or an unanswered question
- Example styles: "He killed seven people and smiled through every interrogation." / "For 30 years, his neighbors had no idea they lived next to a killer."
- NEVER open with "Today we're talking about..." or generic intros

【Paragraph Pacing】
- Para 1 (Background): Build dread, make viewers lean in
- Para 2 (Events): Accelerate pace, short punchy sentences, mounting tension
- Para 3 (Turning point): The gut-punch reveal, breathless pace
- Para 4 (Ending): Quiet, haunting close — like a thought you can't shake at 3am

【Language】
- Short sentences (8-15 words) for rhythm
- Emotional anchors: "That night", "No one knew", "Until...", "What made it worse was"
- Add "..." at key dramatic pauses for TTS breathing
- Total: 400-470 words (3-minute pace)
- End with a quiet reflection, not a call-to-action

=== VISUAL SCENES (15 total, in narrative order) ===
Dark, gritty, crime-specific Pexels search queries.
At least 5 must use explicit crime imagery: blood drops, chalk outline, forensic evidence, police tape, interrogation room, handcuffs, knife detail, detective board, body bag corridor, morgue.
Remaining: moody atmospheric shots matching the case era/location.
NEVER generic happy/neutral scenes.

=== SCENE PACING (15 values matching visual_scenes order) ===
Pacing for each cut:
- "slow" = 5s (narration, background exposition)
- "medium" = 4s (story progression)
- "fast" = 2.5s (tense action moments)
- "climax" = 1.5s (peak intensity moments)

Return this exact JSON:
{{
  "title": "Catchy title with keywords (under 70 chars)",
  "script": "Full script content",
  "keywords": ["english keyword1", "keyword2", "keyword3"],
  "description": "YouTube description (under 120 chars)",
  "hashtags": ["#TrueCrime", "#CriminalMinds", "#TrueCrimeStory"],
  "visual_scenes": [
    "scene 1 dark crime-specific Pexels query",
    "... 15 total in story order ..."
  ],
  "scene_pacing": ["slow", "medium", "fast", "climax", "... 15 total ..."]
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
                if e.status_code == 529:
                    wait = 20 * (attempt + 1)
                    print(f"  [WARN] {model} overloaded, retrying in {wait}s... (attempt {attempt+1}/3)")
                    time.sleep(wait)
                else:
                    raise
        print(f"  [WARN] {model} overloaded after 3 retries, trying next model...")
    raise RuntimeError("All Claude models overloaded")
