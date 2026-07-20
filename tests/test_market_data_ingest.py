import pytest
from market_data_ingest import build_week_pack, StaleDataError

FIX = "tests/fixtures/daily_reports"
FIX_BOUNDARY = "tests/fixtures/daily_reports_boundary"


def test_week_pack_schema_and_values():
    pack = build_week_pack(FIX, end_date="2026-06-11")
    assert pack["is_paper"] is True
    assert pack["period"]["end"] == "2026-06-11"
    assert pack["period"]["start"] == "2026-06-09"   # fixture 只有 3 天
    assert pack["equity_end"] == 1564.15
    assert pack["equity_start"] == 1560.0
    assert round(pack["week_pnl"], 2) == 4.15
    assert round(pack["week_pnl_pct"], 2) == 0.27    # 4.15/1560*100
    assert pack["total_trades"] == 500
    assert pack["week_trades"] == 26                  # 6+10+10
    assert pack["days_running"] == 49
    assert pack["week_number"] == 7                   # ceil(49/7)
    assert pack["best_day"]["date"] == "2026-06-10"
    assert pack["worst_day"]["date"] == "2026-06-09"
    assert pack["daily_equity"] == [1560.0, 1562.5, 1564.15]


def test_stale_data_raises():
    # end_date=None → 以今天為準，fixture 是 2026-06 的 → 必過期
    with pytest.raises(StaleDataError):
        build_week_pack(FIX)


def test_week_pack_never_crosses_experiment_restart():
    # daily_reports_boundary/ 混有舊實驗(days_running 48/49，到 2026-06-11)
    # 與新實驗(days_running 0/1，從 2026-07-14 重新起算)。
    # 從 end_date=2026-07-15 往回取 7 天視窗時，遇到 days_running 歸零重啟
    # 的斷點（前一天 49 > 後一天 0）就必須停，絕不把舊實驗的天數也算進來。
    pack = build_week_pack(FIX_BOUNDARY, end_date="2026-07-15")
    assert pack["period"]["start"] == "2026-07-14"
    assert pack["period"]["end"] == "2026-07-15"
    assert pack["daily_dates"] == ["2026-07-14", "2026-07-15"]
    assert pack["daily_equity"] == [1000.0, 1008.0]
    assert pack["days_running"] == 1
    assert pack["week_number"] == 1   # ceil(1/7)，用新實驗的 days_running 算


def test_week_number_floors_at_one_on_experiment_day_zero():
    # 實驗第一天（days_running=0），week_number 應該最低是 1 而非 0
    # end_date="2026-07-14" 的視窗只含一天（2026-07-14），
    # days_running=0，math.ceil(0/7)=0 但應該被改為 max(1, ...) = 1
    pack = build_week_pack(FIX_BOUNDARY, end_date="2026-07-14")
    assert pack["period"]["start"] == "2026-07-14"
    assert pack["period"]["end"] == "2026-07-14"
    assert pack["daily_dates"] == ["2026-07-14"]
    assert pack["days_running"] == 0
    assert pack["week_number"] == 1  # max(1, ceil(0/7)) = 1，不是 0


def test_health_fields_passthrough(tmp_path):
    """2026-07-20 健康欄位透傳；舊日報缺欄位時給安全預設。"""
    import json as _json
    new = {"date": "2026-07-20", "equity": 1000.0, "total_pnl": 0.0,
           "total_pnl_pct": 0.0, "daily_change": 0.0, "daily_change_pct": 0.0,
           "realized_pnl": 0, "total_fees": 0, "total_trades": 0,
           "daily_trades": 0, "grid_cycles": 0, "grid_pnl": 0.0,
           "days_running": 6, "btc_bearish": True, "open_orders": 0,
           "grids": {"LINK": {"low": 7.47, "high": 8.69, "price": 8.46}}}
    (tmp_path / "2026-07-20.json").write_text(_json.dumps(new))
    pack = build_week_pack(str(tmp_path), end_date="2026-07-20")
    assert pack["btc_bearish"] is True
    assert pack["open_orders"] == 0
    assert pack["grids"]["LINK"]["low"] == 7.47

    # 舊日報（無健康欄位）→ 安全預設
    old_pack = build_week_pack(FIX, end_date="2026-06-11")
    assert old_pack["btc_bearish"] is None
    assert old_pack["open_orders"] == 0
    assert old_pack["grids"] == {}
