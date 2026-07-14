"""權益曲線 → 1080x1920 深色圖（延續頻道 noir 品牌感）。

固定角標「模擬盤實驗」— spec 防線 2：這行字由程式燒進圖，不依賴 LLM。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

import os

_CJK = None
for _p in ("/System/Library/Fonts/PingFang.ttc",
           "/System/Library/Fonts/STHeiti Light.ttc"):
    if os.path.exists(_p):
        try:
            _CJK = font_manager.FontProperties(fname=_p)
            break
        except Exception:
            continue

BG, FG, ACCENT, UP, DOWN = "#0d0f14", "#d8d8d8", "#e0b34a", "#4ac26b", "#e05555"


def render_equity_chart(pack: dict, out_path: str) -> str:
    eq, dates = pack["daily_equity"], pack["daily_dates"]
    up = eq[-1] >= eq[0]
    line = UP if up else DOWN

    fig = plt.figure(figsize=(10.8, 19.2), dpi=100, facecolor=BG)
    ax = fig.add_axes([0.12, 0.30, 0.80, 0.36], facecolor=BG)
    ax.plot(range(len(eq)), eq, color=line, linewidth=4)
    ax.fill_between(range(len(eq)), eq, min(eq), color=line, alpha=0.12)
    for spine in ax.spines.values():
        spine.set_color("#333")
    ax.tick_params(colors="#888", labelsize=16)
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels([d[5:].replace("-", "/") for d in dates], rotation=0)

    sign = "+" if pack["week_pnl_pct"] >= 0 else ""
    fig.text(0.5, 0.78, f"AI 操盤第 {pack['week_number']} 週",
             ha="center", color=FG, fontsize=44, fontproperties=_CJK)
    fig.text(0.5, 0.71, f"{sign}{pack['week_pnl_pct']:.2f}%",
             ha="center", color=line, fontsize=90, fontweight="bold")
    fig.text(0.5, 0.24,
             f"最佳 {pack['best_day']['date'][5:]} "
             f"{pack['best_day']['change_pct']:+.2f}%   "
             f"最差 {pack['worst_day']['date'][5:]} "
             f"{pack['worst_day']['change_pct']:+.2f}%",
             ha="center", color="#999", fontsize=22, fontproperties=_CJK)
    # 防線 2：模擬盤角標，程式燒入，非 LLM 可省略
    fig.text(0.97, 0.975, "模擬盤實驗", ha="right", va="top",
             color=ACCENT, fontsize=26, fontproperties=_CJK)
    fig.text(0.5, 0.03, "實驗紀錄，非投資建議", ha="center",
             color="#666", fontsize=18, fontproperties=_CJK)

    fig.savefig(out_path, facecolor=BG)
    plt.close(fig)
    return out_path
