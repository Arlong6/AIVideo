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
