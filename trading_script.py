"""週報腳本生成 — LLM 只敘述數據包，數字閘門 + 禁詞雙 fail-closed。"""
import json
import re

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
   金額單位一律是「美元」：寫「1000 美元」，絕對禁止寫「1000 元」（會被誤解為台幣）。
2. 這是「模擬盤」（虛擬資金實驗）。不可暗示真金白銀或實際獲利。
3. 禁止投資建議、禁止推薦任何標的、禁止使用以下詞彙：{banned_words}。
4. 禁止敘述任何外部市場事件（不談 Fed、不談新聞、不談大盤）。只講這個帳戶的數據。
5. 虧損就照實講虧損 — 誠實是這個頻道的賣點。
5b. 若數據 btc_bearish 為 true 且本週交易為 0：本週敘事核心是「AI 判定 BTC 空頭，
   風控自動暫停買入」— 這是系統在避險，不是沒事發生。禁止寫成「市場很安靜」。
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


def _display_pack(pack: dict):
    """遞迴複製 pack，把所有 float 四捨五入到 2 位小數 —— 只用於 prompt 注入。

    根因：原始 pack 裡的長浮點（如 0.26601456）會被 LLM 複誦或亂捨入成
    閘門不認得的形式，導致合法輸出被 number gate 誤攔。閘門本身仍驗證
    against 原始 pack（`_formats_of` 白名單本來就涵蓋 0-3 位捨入形，
    含 2 位），所以這裡的捨入不會放寬閘門、只是讓 LLM 看到的數字跟它
    被鼓勵書寫的形式一致。int 與字串（日期等）原樣保留。
    """
    if isinstance(pack, dict):
        return {k: _display_pack(v) for k, v in pack.items()}
    if isinstance(pack, list):
        return [_display_pack(v) for v in pack]
    if isinstance(pack, tuple):
        return tuple(_display_pack(v) for v in pack)
    if isinstance(pack, bool):
        return pack
    if isinstance(pack, float):
        return round(pack, 2)
    return pack


# ===== 「第X週」確定性正規化 =====
# 根因：LLM 天然會寫「第一週」「第十二週」而非阿拉伯數字 —— 這是合法內容，
# 但會被下面的 _has_cjk_numerals 中文數字閘門攔下（fail-closed 攔錯）。
# 在跑任何閘門之前，先把「第[中文數字]週」這一種固定模式確定性轉成
# 「第 N 週」寫回 script（TTS 唸的就是轉換後的版本），閘門看到的是已經
# 阿拉伯數字化的文字，不會誤攔合法的週數表達。只處理這一種模式 ——
# 「[中文數字]週年」等其他語境不受影響。
_CJK_DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_WEEK_CJK_RE = re.compile(r"第([零一二三四五六七八九十]+)週")


def _cjk_num_to_int(s: str) -> int:
    """把中文數字字串（支援 0-99：零一二三四五六七八九十 組合）轉成 int。"""
    if s == "十":
        return 10
    if "十" in s:
        tens_part, _, ones_part = s.partition("十")
        tens = _CJK_DIGIT[tens_part] if tens_part else 1
        ones = _CJK_DIGIT[ones_part] if ones_part else 0
        return tens * 10 + ones
    value = 0
    for ch in s:
        value = value * 10 + _CJK_DIGIT[ch]
    return value


def _normalize_cjk_week_numbers(text: str) -> str:
    """把「第[中文數字]週」確定性轉成「第 N 週」（N 為阿拉伯數字）。

    已是阿拉伯數字的「第 3 週」不受影響（regex 只匹配中文數字字元）。
    """
    def repl(m: "re.Match[str]") -> str:
        try:
            n = _cjk_num_to_int(m.group(1))
        except KeyError:
            return m.group(0)
        return f"第 {n} 週"
    return _WEEK_CJK_RE.sub(repl, text)


def _normalize_script_cjk_weeks(script: dict) -> None:
    """對 script 的所有觀眾可見欄位套用 _normalize_cjk_week_numbers，就地寫回。"""
    for key in ("title", "hook", "cta", "description"):
        val = script.get(key)
        if isinstance(val, str):
            script[key] = _normalize_cjk_week_numbers(val)
    for section in script.get("sections", []) or []:
        if isinstance(section, dict) and isinstance(section.get("text"), str):
            section["text"] = _normalize_cjk_week_numbers(section["text"])
    hashtags = script.get("hashtags")
    if isinstance(hashtags, list):
        script["hashtags"] = [
            _normalize_cjk_week_numbers(h) if isinstance(h, str) else h
            for h in hashtags
        ]


# 觀眾可見文字裡的中文數字字元。「一起/一樣/十分」這類慣用語僅含單一
# 中文數字字元，不落在「數值語境」規則內，不會誤觸發。
_CJK_NUMERAL_CHARS = "零一二三四五六七八九十百千萬億兆兩"
# 注意：「天」故意不放進單字元後綴 —— 「最好的一天」是常見的敘述性慣用語
# （=「the day」），不是數量宣告；多位數的天數（如「四十九天」）仍會被
# 上面的「連續 ≥2 個中文數字字元」規則攔下，不受影響。
_CJK_NUMERAL_UNIT_SUFFIXES = ("%", "週", "筆", "元", "美元", "倍", "成")
# 「千萬不要/千萬別」是常用慣用語（=絕對不要），不是數值 —— 即使「千」「萬」
# 兩個中文數字字元相鄰，也必須排除在偵測之外。
# 「萬一」(if/in case of) 、「千萬要」(absolutely must)、「千萬記得」(absolutely remember)
# 都是常用的非數值慣用語。
_CJK_NUMERAL_IDIOM_EXCEPTIONS = ("千萬不要", "千萬別", "萬一", "千萬要", "千萬記得")


def _context_snippet(text: str, start: int, end: int, radius: int = 10) -> str:
    """回傳 [start, end] 命中片段（含）前後各 radius 字的上下文，供錯誤訊息使用。"""
    lo = max(0, start - radius)
    hi = min(len(text), end + 1 + radius)
    return text[lo:hi]


def _has_cjk_numerals(text: str):
    """偵測文字中以中文數字書寫、落在數值語境的片段（繞過 \\d regex 的幻覺數字）。

    觸發條件：連續 ≥2 個中文數字字元，或中文數字字元後緊接單位（%／週／筆／元／美元／倍／成）。
    回傳命中片段的原文上下文（前後各 10 字）；沒有命中回傳 None。

    Mask escape guard: Idiom exceptions are only masked if NOT preceded by a CJK numeral character.
    This prevents false negatives when numerals precede idioms (e.g., 五千萬不要).
    """
    # Build masked text: remove idioms only if not preceded by CJK numeral.
    # idx_map[j] tracks which original-text index masked_text[j] came from,
    # so a hit found in masked_text can be reported with original-text context.
    result = []
    idx_map = []
    i = 0
    while i < len(text):
        matched = False
        for idiom in _CJK_NUMERAL_IDIOM_EXCEPTIONS:
            if text[i:i+len(idiom)] == idiom:
                # Check if preceded by CJK numeral (mask escape guard)
                if i == 0 or text[i-1] not in _CJK_NUMERAL_CHARS:
                    # Safe to mask this idiom
                    i += len(idiom)
                    matched = True
                    break
        if not matched:
            result.append(text[i])
            idx_map.append(i)
            i += 1

    masked_text = "".join(result)

    n = len(masked_text)
    for i, ch in enumerate(masked_text):
        if ch not in _CJK_NUMERAL_CHARS:
            continue
        if i + 1 < n and masked_text[i + 1] in _CJK_NUMERAL_CHARS:
            return _context_snippet(text, idx_map[i], idx_map[i + 1])
        for suf in _CJK_NUMERAL_UNIT_SUFFIXES:
            if masked_text[i + 1:i + 1 + len(suf)] == suf:
                end = i + len(suf)
                return _context_snippet(text, idx_map[i], idx_map[end])
    return None


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
        pack_json=json.dumps(_display_pack(pack), ensure_ascii=False, indent=1),
        week_number=pack["week_number"], sign=sign,
        banned_words="、".join(BANNED_WORDS))
    script = _call_llm(prompt)
    # 確定性正規化「第X週」（中文數字）→「第 N 週」（阿拉伯數字），寫回 script
    # （TTS 唸的就是正規化後的版本），再跑任何 fail-closed 閘門 —— 這樣
    # LLM 天然寫的「第一週」不會被中文數字閘門誤攔。
    _normalize_script_cjk_weeks(script)

    text = _all_text(script)
    hits = [w for w in BANNED_WORDS if w in text]
    if hits:
        raise BannedWordError(
            f"banned words in script: {hits} — refusing to render")
    # 幣別防線：本金是美元，「1000 元」會被台灣觀眾讀成台幣（差 32 倍），
    # 跟捏造數字同級的真實性錯誤。裸「元」（前面不是「美」）接在數字後 → 拒絕。
    bare_yuan = re.search(r"\d\s?(?<!美)元", text)
    if bare_yuan:
        raise BannedWordError(
            f"bare 「元」 as currency (is USD, reads as TWD): "
            f"{bare_yuan.group()!r} — refusing to render")
    cjk_hit = _has_cjk_numerals(text)
    if cjk_hit:
        raise CJKNumeralError(
            "script contains a Chinese-numeral value with no arabic-digit "
            "source in the data pack — refusing to render (fail-closed). "
            f"offending snippet: ...{cjk_hit}...")
    assert_numbers_ok(text, pack)

    if DISCLAIMER not in (script.get("description") or ""):
        script["description"] = (script.get("description", "").strip()
                                 + f"\n{DISCLAIMER}").strip()
    return script
