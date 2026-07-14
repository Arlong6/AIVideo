"""pikmin 模擬盤日報 → 標準化「數據包」。只讀，絕不寫入源專案。

數據包是下游一切的唯一事實來源：腳本生成注入它、數字對帳閘門用它驗證、
圖表模組畫它。任何不在數據包裡的數字都不准出現在影片裡。
"""
import json
import math
import os
from datetime import datetime, timedelta

PIKMIN_REPORTS_DIR = os.path.expanduser(
    "~/Projects/pikmin-command-center/trading/daily_reports")
STALE_HOURS = 48


class StaleDataError(Exception):
    """最新日報超過 STALE_HOURS — 寧可不出片也不用舊數據冒充本週。"""


def _load_reports(reports_dir: str) -> list[dict]:
    reports = []
    for name in sorted(os.listdir(reports_dir)):
        if name.endswith(".json"):
            with open(os.path.join(reports_dir, name), encoding="utf-8") as f:
                reports.append(json.load(f))
    return reports


def _take_window(filtered: list[dict], max_days: int = 7) -> list[dict]:
    """從 filtered（依日期升冪排序）取最近 max_days 天，但絕不跨實驗。

    daily_reports/ 可能混有多個實驗的日報：舊實驗結束、新實驗
    days_running 從 0 重新起算。往回掃描時，一旦發現「前一天的
    days_running 大於後一天」（代表後一天是歸零重啟的斷點），就代表
    再往前已經是別的實驗，立刻停止、不把那些天數納入視窗。
    """
    window: list[dict] = []
    prev_days_running = None
    for report in reversed(filtered):
        if prev_days_running is not None and report["days_running"] > prev_days_running:
            break  # 前一天(此輪的 report) days_running 比後一天大 → 跨實驗斷點
        window.append(report)
        prev_days_running = report["days_running"]
        if len(window) == max_days:
            break
    window.reverse()
    return window


def build_week_pack(reports_dir: str = PIKMIN_REPORTS_DIR,
                    end_date: str | None = None) -> dict:
    """組出最近 7 天（或 fixture 範圍內，且不跨實驗重啟）的週報數據包。

    end_date: 'YYYY-MM-DD'，None = 今天且啟用過期檢查（>48h 拒跑）。
    """
    reports = _load_reports(reports_dir)
    if not reports:
        raise FileNotFoundError(f"no daily reports in {reports_dir}")

    if end_date is None:
        latest = datetime.strptime(reports[-1]["date"], "%Y-%m-%d")
        if datetime.now() - latest > timedelta(hours=STALE_HOURS):
            raise StaleDataError(
                f"latest report {reports[-1]['date']} is older than "
                f"{STALE_HOURS}h — fix the pikmin cron before publishing")
        end_date = reports[-1]["date"]

    filtered = [r for r in reports if r["date"] <= end_date]
    if not filtered:
        raise ValueError(f"no reports on or before {end_date}")

    window = _take_window(filtered)

    first, last = window[0], window[-1]
    week_pnl = last["equity"] - first["equity"]
    best = max(window, key=lambda r: r["daily_change_pct"])
    worst = min(window, key=lambda r: r["daily_change_pct"])

    return {
        "is_paper": True,
        "period": {"start": first["date"], "end": last["date"]},
        "week_number": math.ceil(last["days_running"] / 7),
        "days_running": last["days_running"],
        "equity_start": first["equity"],
        "equity_end": last["equity"],
        "week_pnl": week_pnl,
        "week_pnl_pct": week_pnl / first["equity"] * 100,
        "total_pnl": last["total_pnl"],
        "total_pnl_pct": last["total_pnl_pct"],
        "total_trades": last["total_trades"],
        "week_trades": sum(r["daily_trades"] for r in window),
        "total_fees": last["total_fees"],
        "best_day": {"date": best["date"],
                     "change_pct": best["daily_change_pct"]},
        "worst_day": {"date": worst["date"],
                      "change_pct": worst["daily_change_pct"]},
        "daily_equity": [r["equity"] for r in window],
        "daily_dates": [r["date"] for r in window],
    }
