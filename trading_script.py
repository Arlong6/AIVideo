"""週報腳本生成 — LLM 只敘述數據包，數字閘門 + 禁詞雙 fail-closed。"""
import json

from number_gate import assert_numbers_ok

DISCLAIMER = "模擬盤實驗紀錄，非投資建議"

# spec §5.5 / §6：指向「保證/帶單」語意的詞，任何欄位出現即拒絕
BANNED_WORDS = ("保證獲利", "必賺", "穩賺", "跟單", "帶單", "老師",
                "財富自由", "躺賺")


class BannedWordError(Exception):
    pass


PROMPT_WEEKLY = """你是一個 faceless 短影音頻道的編劇。頻道記錄「AI 自動交易模擬盤實驗」。

【本週數據（唯一事實來源，嚴格遵守）】
{pack_json}

【鐵則】
1. 只能使用上面數據裡出現的數字，用阿拉伯數字書寫。禁止自創或推算任何新數字
   （0-10 的結構性計數除外，如「3 個重點」）。
2. 這是「模擬盤」（虛擬資金實驗）。不可暗示真金白銀或實際獲利。
3. 禁止投資建議、禁止推薦任何標的、禁止：保證獲利/必賺/穩賺/跟單/帶單/老師。
4. 禁止敘述任何外部市場事件（不談 Fed、不談新聞、不談大盤）。只講這個帳戶的數據。
5. 虧損就照實講虧損 — 誠實是這個頻道的賣點。
6. 語氣：好奇的實驗記錄者，不是理財專家。繁體中文，台灣用語，短句。

【回傳 JSON（不要其他文字）】
{{
  "title": "≤20字，格式參考「AI 操盤第 {week_number} 週：{sign}X%」",
  "hook": "≤30字開場，建立「這是一個進行中的實驗」的懸念",
  "sections": [
    {{"text": "≤40字：本週權益變化", "visual": "equity chart"}},
    {{"text": "≤40字：本週交易亮點（最佳/最差日）", "visual": "trades"}},
    {{"text": "≤40字：累積狀態（天數/總筆數）", "visual": "summary"}}
  ],
  "cta": "≤20字，下集懸念式收尾，禁止任何行動呼籲以外的承諾",
  "description": "≤50字影片描述",
  "hashtags": ["#AI交易", "#量化交易", "#自動交易", "#模擬盤"]
}}"""


def _call_llm(prompt: str) -> dict:
    from script_generator import _call_claude
    return _call_claude(prompt)


def _all_text(script: dict) -> str:
    parts = [script.get("title", ""), script.get("hook", ""),
             script.get("cta", ""), script.get("description", "")]
    parts += [s.get("text", "") for s in script.get("sections", [])]
    # Include hashtags (viewer-visible in YouTube metadata)
    hashtags = script.get("hashtags", [])
    if hashtags:
        parts.append(" ".join(hashtags))
    return "\n".join(parts)


def generate_weekly_script(pack: dict) -> dict:
    sign = "+" if pack["week_pnl_pct"] >= 0 else "-"
    prompt = PROMPT_WEEKLY.format(
        pack_json=json.dumps(pack, ensure_ascii=False, indent=1),
        week_number=pack["week_number"], sign=sign)
    script = _call_llm(prompt)

    text = _all_text(script)
    hits = [w for w in BANNED_WORDS if w in text]
    if hits:
        raise BannedWordError(
            f"banned words in script: {hits} — refusing to render")
    assert_numbers_ok(text, pack)

    if DISCLAIMER not in (script.get("description") or ""):
        script["description"] = (script.get("description", "").strip()
                                 + f"\n{DISCLAIMER}").strip()
    return script
