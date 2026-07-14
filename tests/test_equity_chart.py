import os
from PIL import Image
from equity_chart import render_equity_chart

PACK = {
    "is_paper": True, "week_number": 7,
    "daily_equity": [1560.0, 1562.5, 1561.0, 1563.0, 1564.15],
    "daily_dates": ["2026-06-07", "2026-06-08", "2026-06-09",
                     "2026-06-10", "2026-06-11"],
    "week_pnl_pct": 0.266,
    "best_day": {"date": "2026-06-10", "change_pct": 0.16},
    "worst_day": {"date": "2026-06-09", "change_pct": -0.096},
}

def test_chart_renders_9_16_png(tmp_path):
    out = str(tmp_path / "chart.png")
    assert render_equity_chart(PACK, out) == out
    img = Image.open(out)
    assert img.size == (1080, 1920)
    # 不是全黑（有畫東西）
    assert img.convert("L").getextrema()[1] > 60
