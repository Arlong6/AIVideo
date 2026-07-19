import pytest
from number_gate import verify_numbers, assert_numbers_ok, NumberMismatch

PACK = {
    "week_number": 7, "days_running": 49,
    "equity_end": 1564.15, "week_pnl": 4.15, "week_pnl_pct": 0.266,
    "total_trades": 500, "week_trades": 26,
    "best_day": {"date": "2026-06-10", "change_pct": 0.16},
}

def test_exact_and_rounded_matches_pass():
    text = "第7週結束，AI 帳戶來到 1564 美元，本週 +0.27%，累積 500 筆交易。"
    assert verify_numbers(text, PACK) == []

def test_thousand_separator_and_decimals_pass():
    assert verify_numbers("權益 1,564.15，49 天", PACK) == []

def test_date_fragments_pass():
    assert verify_numbers("6月10日 是本週最好的一天，+0.16%", PACK) == []

def test_small_structural_ints_allowed():
    assert verify_numbers("3 個重點", PACK) == []   # 0-10 白名單

def test_unknown_number_caught():
    bad = "本週大賺 12%，帳戶衝上 9999 美元"
    violations = verify_numbers(bad, PACK)
    assert "12" in violations and "9999" in violations

def test_assert_raises():
    with pytest.raises(NumberMismatch):
        assert_numbers_ok("獲利 777%", PACK)

def test_round_number_does_not_leak_short_token():
    pack = dict(PACK, total_trades=1200)
    v = verify_numbers("本週大賺 12%，帳戶正常", pack)
    assert "12" in v

def test_round_equity_does_not_leak():
    pack = dict(PACK); pack["equity_end"] = 1500.0
    assert "15" in verify_numbers("帳戶漲了15%", pack)

def test_descriptive_string_field_not_scanned_for_digits():
    pack = dict(PACK, note="temp 999 test")
    assert "999" in verify_numbers("今天測試 999 次", pack)

def test_fixed_decimal_trailing_zero_matches():
    """Equity chart formats worst_day as {:+.2f}%, e.g. "-0.10%" for -0.096.
    The whitelist must accept both unstripped "-0.10" and stripped "-0.1" forms."""
    pack = {"worst_pct": -0.096}
    assert verify_numbers("最差 -0.10%", pack) == []
    assert verify_numbers("最差 0.10%", pack) == []


def test_small_int_with_unit_not_whitelisted():
    v = verify_numbers("本週大賺 8%，翻了 5 倍，賺 3 成", PACK)
    assert "8" in v and "5" in v and "3" in v


def test_small_int_bare_count_still_whitelisted():
    assert verify_numbers("3 個重點，我們一一來看", PACK) == []


def test_sourced_small_int_with_unit_passes():
    pack = dict(PACK); pack["week_pnl_pct"] = 3.0
    assert verify_numbers("本週 +3%", pack) == []
