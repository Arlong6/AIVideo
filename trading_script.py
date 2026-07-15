"""週報腳本生成 — LLM 只敘述數據包，數字閘門 + 禁詞雙 fail-closed。"""
import json

from number_gate import assert_numbers_ok

DISCLAIMER = "模擬盤實驗紀錄，非投資建議"

# spec §5.5 / §6：指向「保證/帶單」語意的詞，任何欄位出現即拒絕
BANNED_WORDS = ("保證獲利", "必賺", "穩賺", "跟單", "帶單", "老師",
                "財富自由", "躺賺")


class BannedWordError(Exception):
    pass


class CJKNumeralError(Exception):
    pass


PROMPT_WEEKLY = """你是一個 faceless 短影音頻道的編劇。頻道記錄「AI 自動交易模擬盤實驗」。

【本週數據（唯一事實來源，嚴格遵守）】
{pack_json}

【鐵則】
1. 只能使用上面數據裡出現的數字，用阿拉伯數字書寫。禁止自創或推算任何新數字
   （0-10 的結構性計數除外，如「3 個重點」）。
2. 這是「模擬盤」（虛擬資金實驗）。不可暗示真金白銀或實際獲利。
3. 禁止投資建議、禁止推薦任何標的、禁止使用以下詞彙：{banned_words}。
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


# 觀眾可見文字裡的中文數字字元。「一起/一樣/十分」這類慣用語僅含單一
# 中文數字字元，不落在「數值語境」規則內，不會誤觸發。
_CJK_NUMERAL_CHARS = "零一二三四五六七八九十百千萬億兆兩"
# 注意：「天」故意不放進單字元後綴 —— 「最好的一天」是常見的敘述性慣用語
# （=「the day」），不是數量宣告；多位數的天數（如「四十九天」）仍會被
# 上面的「連續 ≥2 個中文數字字元」規則攔下，不受影響。
_CJK_NUMERAL_UNIT_SUFFIXES = ("%", "週", "筆", "元", "美元")
# 「千萬不要/千萬別」是常用慣用語（=絕對不要），不是數值 —— 即使「千」「萬」
# 兩個中文數字字元相鄰，也必須排除在偵測之外。
_CJK_NUMERAL_IDIOM_EXCEPTIONS = ("千萬不要", "千萬別")


def _has_cjk_numerals(text: str) -> bool:
    """偵測文字中以中文數字書寫、落在數值語境的片段（繞過 \\d regex 的幻覺數字）。

    觸發條件：連續 ≥2 個中文數字字元，或中文數字字元後緊接單位（%／週／筆／元／美元）。
    """
    for idiom in _CJK_NUMERAL_IDIOM_EXCEPTIONS:
        text = text.replace(idiom, "")

    n = len(text)
    for i, ch in enumerate(text):
        if ch not in _CJK_NUMERAL_CHARS:
            continue
        if i + 1 < n and text[i + 1] in _CJK_NUMERAL_CHARS:
            return True
        for suf in _CJK_NUMERAL_UNIT_SUFFIXES:
            if text[i + 1:i + 1 + len(suf)] == suf:
                return True
    return False


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
        week_number=pack["week_number"], sign=sign,
        banned_words="、".join(BANNED_WORDS))
    script = _call_llm(prompt)

    text = _all_text(script)
    hits = [w for w in BANNED_WORDS if w in text]
    if hits:
        raise BannedWordError(
            f"banned words in script: {hits} — refusing to render")
    if _has_cjk_numerals(text):
        raise CJKNumeralError(
            "script contains a Chinese-numeral value with no arabic-digit "
            "source in the data pack — refusing to render (fail-closed)")
    assert_numbers_ok(text, pack)

    if DISCLAIMER not in (script.get("description") or ""):
        script["description"] = (script.get("description", "").strip()
                                 + f"\n{DISCLAIMER}").strip()
    return script
