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
    assert _has_cjk_numerals("大家一起看") is False
    assert _has_cjk_numerals("十分驚人") is False


def test_has_cjk_numerals_idiom_whitelist():
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("千萬不要相信") is False


def test_has_cjk_numerals_triggers_on_numeric_context():
    from trading_script import _has_cjk_numerals
    assert _has_cjk_numerals("八十八") is True
    assert _has_cjk_numerals("兩週") is True
    assert _has_cjk_numerals("五百筆") is True


def test_cjk_numeral_bypass_fails_closed():
    """LLM 用中文數字寫「八十八」繞過 \\d regex，數字閘門會靜默放行；
    _has_cjk_numerals 必須攔下這種以中文數字表達的幻覺數值。"""
    bad = dict(GOOD); bad["hook"] = "第 7 週，AI 大賺八十八趴！"
    with patch("trading_script._call_llm", return_value=bad):
        from trading_script import generate_weekly_script, CJKNumeralError
        with pytest.raises(CJKNumeralError):
            generate_weekly_script(PACK)


def test_disclaimer_not_duplicated_if_already_present():
    from trading_script import DISCLAIMER
    already = dict(GOOD)
    already["description"] = f"AI 自動交易模擬盤實驗第 7 週紀錄。{DISCLAIMER}"
    with patch("trading_script._call_llm", return_value=already):
        from trading_script import generate_weekly_script
        s = generate_weekly_script(PACK)
        assert s["description"].count(DISCLAIMER) == 1
