import re
import pytest
from unittest.mock import patch

GOOD = {
    "title": "AI 操盤第 7 週：+0.27%",
    "hook": "我讓 AI 管一個模擬帳戶，第 7 週了。",
    "sections": [
        {"text": "本週權益從 1560 來到 1564，+0.27%。", "visual": "equity chart"},
        {"text": "這週 26 筆交易，最好的一天 6月10日 +0.16%。", "visual": "trades"},
        {"text": "累積 49 天，總共 500 筆。", "visual": "summary"},
    ],
    "cta": "下週它會怎麼樣？追蹤看下集。",
    "description": "AI 自動交易模擬盤實驗第 7 週紀錄。",
    "hashtags": ["#AI交易", "#量化"],
}
PACK = {
    "is_paper": True, "week_number": 7, "days_running": 49,
    "equity_start": 1560.0, "equity_end": 1564.15,
    "week_pnl": 4.15, "week_pnl_pct": 0.266,
    "total_trades": 500, "week_trades": 26,
    "best_day": {"date": "2026-06-10", "change_pct": 0.16},
    "worst_day": {"date": "2026-06-09", "change_pct": -0.096},
    "daily_equity": [1560.0, 1564.15], "daily_dates": ["2026-06-09", "2026-06-11"],
}

def test_good_script_passes_and_gets_disclaimer():
    with patch("trading_script._call_llm", return_value=dict(GOOD)):
        from trading_script import generate_weekly_script, DISCLAIMER
        s = generate_weekly_script(PACK)
        assert s["title"] == GOOD["title"]
        assert DISCLAIMER in s["description"]

def test_hallucinated_number_fails_closed():
    bad = dict(GOOD); bad["hook"] = "第 7 週，AI 大賺 88%！"
    with patch("trading_script._call_llm", return_value=bad):
        from trading_script import generate_weekly_script
        from number_gate import NumberMismatch
        with pytest.raises(NumberMismatch):
            generate_weekly_script(PACK)

def test_banned_word_fails_closed():
    bad = dict(GOOD); bad["cta"] = "跟單保證獲利！"
    with patch("trading_script._call_llm", return_value=bad):
        from trading_script import generate_weekly_script, BannedWordError
        with pytest.raises(BannedWordError):
            generate_weekly_script(PACK)


def test_prompt_interpolates_full_banned_word_list():
    """PROMPT_WEEKLY 鐵則 3 過去手寫了 6/8 禁詞，改漏的 2 個永遠不會被 LLM 看見。
    改為動態內插後，組出的 prompt 必須包含全部 8 個 BANNED_WORDS。"""
    captured = {}

    def fake_call(prompt):
        captured["prompt"] = prompt
        return dict(GOOD)

    with patch("trading_script._call_llm", side_effect=fake_call):
        from trading_script import generate_weekly_script, BANNED_WORDS
        generate_weekly_script(PACK)

    assert len(BANNED_WORDS) == 8
    for word in BANNED_WORDS:
        assert word in captured["prompt"], f"missing banned word in prompt: {word}"


def test_has_cjk_numerals_whitelist_no_false_positive():
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("大家一起看") is None
    assert _has_cjk_numerals("十分驚人") is None


def test_has_cjk_numerals_idiom_whitelist():
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("千萬不要相信") is None


def test_has_cjk_numerals_triggers_on_numeric_context():
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("八十八") is not None
    assert _has_cjk_numerals("兩週") is not None
    assert _has_cjk_numerals("五百筆") is not None


def test_has_cjk_numerals_returns_offending_snippet_with_context():
    """_has_cjk_numerals 現在回傳命中片段的原文上下文（供錯誤訊息使用），
    而非單純的 True/False。"""
    from trading_script import _has_cjk_numerals
    snippet = _has_cjk_numerals("AI 大賺八十八趴，太扯了")
    assert snippet is not None
    assert "八十八" in snippet


def test_cjk_numeral_bypass_fails_closed():
    """LLM 用中文數字寫「八十八」繞過 \\d regex，數字閘門會靜默放行；
    _has_cjk_numerals 必須攔下這種以中文數字表達的幻覺數值，且錯誤訊息
    必須帶上踩到的原文片段，方便除錯。"""
    bad = dict(GOOD); bad["hook"] = "第 7 週，AI 大賺八十八趴！"
    with patch("trading_script._call_llm", return_value=bad):
        from trading_script import generate_weekly_script, CJKNumeralError
        with pytest.raises(CJKNumeralError) as exc_info:
            generate_weekly_script(PACK)
        assert "八十八" in str(exc_info.value)


def test_disclaimer_not_duplicated_if_already_present():
    from trading_script import DISCLAIMER
    already = dict(GOOD)
    already["description"] = f"AI 自動交易模擬盤實驗第 7 週紀錄。{DISCLAIMER}"
    with patch("trading_script._call_llm", return_value=already):
        from trading_script import generate_weekly_script
        s = generate_weekly_script(PACK)
        assert s["description"].count(DISCLAIMER) == 1


# ===== Fix 1: Idiom exceptions for 萬一/千萬要/千萬記得 =====
def test_has_cjk_numerals_idiom_exception_wanyiyao():
    """「萬一」as idiom (if) should not trigger CJK numeral detection."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("萬一虧損怎麼辦") is None


def test_has_cjk_numerals_idiom_exception_qianyao_mid_sentence():
    """「千萬要」in middle of sentence should not trigger."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("千萬要記得追蹤") is None


def test_has_cjk_numerals_idiom_exception_wanyao_mid_clause():
    """「萬一」in middle of clause like「但萬一下週繼續虧」should not trigger."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("但萬一下週繼續虧損") is None


def test_has_cjk_numerals_idiom_exception_qianwan_jiede():
    """「千萬記得」as idiom (absolutely remember) should not trigger."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("千萬記得查看結果") is None


# ===== Fix 2: Unit suffixes for 倍/成 =====
def test_has_cjk_numerals_suffix_bei_multiple():
    """「百倍」(hundredfold) should trigger with 倍 suffix."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("翻了百倍") is not None


def test_has_cjk_numerals_suffix_cheng_percentage():
    """「八成八」(88%) should trigger with 成 suffix."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("賺了八成八") is not None


def test_has_cjk_numerals_suffix_cheng_no_false_positive():
    """「完成」(completed) with 成 should NOT trigger as 完 is not CJK numeral."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("完成任務") is None


def test_has_cjk_numerals_suffix_cheng_achieve():
    """「達成」(achieved) should NOT trigger as 達 is not CJK numeral."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("達成目標") is None


def test_has_cjk_numerals_suffix_cheng_form():
    """「形成」(formed) should NOT trigger as 形 is not CJK numeral."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("形成趨勢") is None


# ===== Fix 3: Mask escape guard =====
def test_has_cjk_numerals_mask_escape_continuous_numeral():
    """「賺到五千萬不要懷疑」: 五千萬 should be caught by continuous rule,
    even though idiom 「不要」is adjacent."""
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("賺到五千萬不要懷疑") is not None


# ===== Fix: display-rounded pack injection (gate-calibration) =====
# 根因重現：真實數據包裡的浮點常帶長尾精度（如 0.26601456180048），
# 舊版把這種原始值直接塞進 prompt，LLM 會複誦或亂捨入成閘門認不得的形式，
# 導致 16/16 次真實呼叫全被 number gate 攔下。修法是 prompt 注入前先把
# 所有 float 四捨五入到 2 位小數（_display_pack），閘門驗證仍對照原始 pack。
LONG_FLOAT_PACK = {
    "is_paper": True, "week_number": 7, "days_running": 49,
    "equity_start": 1560.0, "equity_end": 1564.1499999999999,
    "week_pnl": 4.149999999999977, "week_pnl_pct": 0.26601456180048,
    "total_trades": 500, "week_trades": 26,
    "best_day": {"date": "2026-06-10", "change_pct": 0.15999999999999998},
    "worst_day": {"date": "2026-06-09", "change_pct": -0.09600000000000002},
    "daily_equity": [1560.0, 1564.1499999999999],
    "daily_dates": ["2026-06-09", "2026-06-11"],
}

_LONG_DECIMAL_RE = re.compile(r"\d+\.\d{3,}")


def test_display_pack_rounds_floats_only():
    from trading_script import _display_pack
    disp = _display_pack(LONG_FLOAT_PACK)
    assert disp["equity_end"] == 1564.15
    assert disp["week_pnl_pct"] == 0.27
    assert disp["best_day"]["change_pct"] == 0.16
    # int / str fields must stay untouched
    assert disp["week_number"] == 7
    assert disp["total_trades"] == 500
    assert disp["best_day"]["date"] == "2026-06-10"


def test_prompt_never_contains_long_decimal_raw_pack_values():
    """Prompt injection must use the display-rounded pack — no float with
    3+ decimal digits should ever reach the LLM, even when the real data
    pack carries long floating-point tails."""
    captured = {}

    def fake_call(prompt):
        captured["prompt"] = prompt
        return dict(GOOD)

    with patch("trading_script._call_llm", side_effect=fake_call):
        from trading_script import generate_weekly_script
        generate_weekly_script(LONG_FLOAT_PACK)

    long_decimals = _LONG_DECIMAL_RE.findall(captured["prompt"])
    assert long_decimals == [], (
        f"prompt leaked raw long-decimal numbers: {long_decimals}")


def test_display_rounded_recital_passes_all_gates():
    """A script that recites the *display* (2-decimal-rounded) values of a
    long-float pack — exactly what the calibrated prompt now encourages —
    must clear the number gate, banned-word gate and CJK-numeral gate."""
    recited = {
        "title": "AI 操盤第 7 週：+0.27%",
        "hook": "我讓 AI 管一個模擬帳戶，第 7 週了。",
        "sections": [
            {"text": "本週權益從 1560 來到 1564.15，+0.27%。",
             "visual": "equity chart"},
            {"text": "這週 26 筆交易，最好的一天 6月10日 +0.16%。",
             "visual": "trades"},
            {"text": "累積 49 天，總共 500 筆。", "visual": "summary"},
        ],
        "cta": "下週它會怎麼樣？追蹤看下集。",
        "description": "AI 自動交易模擬盤實驗第 7 週紀錄。",
        "hashtags": ["#AI交易", "#量化"],
    }
    with patch("trading_script._call_llm", return_value=dict(recited)):
        from trading_script import generate_weekly_script, DISCLAIMER
        s = generate_weekly_script(LONG_FLOAT_PACK)
        assert s["title"] == recited["title"]
        assert DISCLAIMER in s["description"]


# ===== Fix: deterministic 「第X週」(CJK numeral) normalizer =====
# 根因重現：e2e 實跑被 CJKNumeralError 攔兩次 —— LLM 天然寫「第一週」，
# 中文數字閘門正確觸發（這本是合法內容），但 retry 救不了同一個模式。
# 修法：在跑任何閘門之前，先確定性把「第[中文數字]週」轉成「第 N 週」
# 寫回 script（TTS 唸的就是轉換後的版本）。
def test_normalizer_converts_cjk_week():
    from trading_script import _normalize_cjk_week_numbers as norm
    assert norm("AI 操盤第一週總結") == "AI 操盤第 1 週總結"
    assert norm("第十二週的實驗") == "第 12 週的實驗"
    assert norm("已經第 3 週了") == "已經第 3 週了"   # 已是阿拉伯不動


def test_normalizer_handles_various_cjk_week_forms():
    from trading_script import _normalize_cjk_week_numbers as norm
    assert norm("第十週") == "第 10 週"
    assert norm("第二十週") == "第 20 週"
    assert norm("第九十九週") == "第 99 週"
    assert norm("沒有週數的句子") == "沒有週數的句子"


def test_normalizer_does_not_touch_unrelated_cjk_numerals():
    """規格只處理「第X週」這一種模式 —— 其他語境（如「兩週年」「八十八」）
    不受影響，仍留給 _has_cjk_numerals 的 fail-closed 閘門處理。"""
    from trading_script import _normalize_cjk_week_numbers as norm
    assert norm("三週年慶") == "三週年慶"
    assert norm("大賺八十八趴") == "大賺八十八趴"


def test_normalize_script_cjk_weeks_writes_back_all_visible_fields():
    from trading_script import _normalize_script_cjk_weeks
    script = {
        "title": "AI 操盤第一週：+0.27%",
        "hook": "我讓 AI 管一個模擬帳戶，第一週了。",
        "sections": [
            {"text": "第一週的權益變化", "visual": "equity chart"},
        ],
        "cta": "第一週先看到這裡。",
        "description": "第一週紀錄。",
        "hashtags": ["#第一週紀錄"],
    }
    _normalize_script_cjk_weeks(script)
    assert script["title"] == "AI 操盤第 1 週：+0.27%"
    assert script["hook"] == "我讓 AI 管一個模擬帳戶，第 1 週了。"
    assert script["sections"][0]["text"] == "第 1 週的權益變化"
    assert script["cta"] == "第 1 週先看到這裡。"
    assert script["description"] == "第 1 週紀錄。"
    assert script["hashtags"] == ["#第 1 週紀錄"]
    # 確認沒有殘留任何中文數字寫法的「第X週」
    for value in [script["title"], script["hook"],
                  script["sections"][0]["text"], script["cta"],
                  script["description"], script["hashtags"][0]]:
        assert "第一週" not in value


WEEK1_PACK = {
    "is_paper": True, "week_number": 1, "days_running": 7,
    "equity_start": 1500.0, "equity_end": 1504.0,
    "week_pnl": 4.0, "week_pnl_pct": 0.27,
    "total_trades": 20, "week_trades": 20,
    "best_day": {"date": "2026-06-10", "change_pct": 0.16},
    "worst_day": {"date": "2026-06-09", "change_pct": -0.10},
    "daily_equity": [1500.0, 1504.0], "daily_dates": ["2026-06-09", "2026-06-11"],
}


def test_generate_weekly_script_normalizes_llm_written_cjk_week_number():
    """整合測試：mock LLM 回傳 title/hook 含「第一週」（LLM 天然行為），
    pack week_number=1 —— generate_weekly_script 必須成功回傳（不再被
    CJKNumeralError 攔下），且輸出的 title 含「第 1 週」不含「第一週」。"""
    week1_good = {
        "title": "AI 操盤第一週：+0.27%",
        "hook": "我讓 AI 管一個模擬帳戶，第一週了。",
        "sections": [
            {"text": "本週權益從 1500 來到 1504，+0.27%。", "visual": "equity chart"},
            {"text": "這週 20 筆交易，最好的一天 6月10日 +0.16%。", "visual": "trades"},
            {"text": "累積 7 天，總共 20 筆。", "visual": "summary"},
        ],
        "cta": "下週它會怎麼樣？追蹤看下集。",
        "description": "AI 自動交易模擬盤實驗第一週紀錄。",
        "hashtags": ["#AI交易", "#量化"],
    }
    with patch("trading_script._call_llm", return_value=dict(week1_good)):
        from trading_script import generate_weekly_script
        s = generate_weekly_script(WEEK1_PACK)
        assert "第 1 週" in s["title"]
        assert "第一週" not in s["title"]


def test_bare_yuan_currency_fails_closed():
    """本金是美元 — 裸「元」會被讀成台幣（差 32 倍），必須攔下。"""
    bad = dict(GOOD)
    bad["sections"] = [{"text": "初始資金 1000 元。", "visual": "equity chart"}]
    with patch("trading_script._call_llm", return_value=bad):
        from trading_script import generate_weekly_script, BannedWordError
        with pytest.raises(BannedWordError, match="元"):
            generate_weekly_script(PACK)


def test_usd_currency_passes():
    ok = dict(GOOD)
    ok["sections"] = [{"text": "本週權益 1564.15 美元，+0.27%。", "visual": "equity chart"},
                      {"text": "這週 26 筆。", "visual": "trades"},
                      {"text": "累積 49 天，500 筆。", "visual": "summary"}]
    with patch("trading_script._call_llm", return_value=ok):
        from trading_script import generate_weekly_script
        s = generate_weekly_script(PACK)
        assert "美元" in s["sections"][0]["text"]
