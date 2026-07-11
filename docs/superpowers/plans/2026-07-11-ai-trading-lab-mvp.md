# AI 交易實驗室 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從 pikmin 模擬盤數據端到端產出第一支「實驗週報」直式短影音（60-90s），數字全程可對帳。

**Architecture:** 新增四個獨立模組（數據擷取 → 數字對帳閘門 → 圖表 → 週報腳本），由一個 orchestrator 串起，組裝端重用既有 `assemble_video(fmt="short")` + `export_reel.py` 打包。LLM 只敘述注入的結構化數據；腳本中任何對不上數據包的數字直接拒絕渲染。

**Tech Stack:** Python 3.10（專案既有 venv）、matplotlib、既有 tts_generator / video_assembler / export_reel、Gemini via `script_generator._call_claude`。

## Global Constraints（來自 spec，每個 task 隱含適用）

- 內容必須明示「模擬盤實驗」：圖表角標 + description 首行（spec §5.2）
- 禁詞 fail-closed：保證獲利、必賺、穩賺、跟單、帶單、老師（spec §5.5、§6）
- 免責聲明固定文案：「模擬盤實驗紀錄，非投資建議」（spec §6）
- v1 禁宏觀評論：prompt 明文禁止敘述外部市場事件（spec §5.3）
- 腳本一律用阿拉伯數字寫數值（對帳閘門的前提）
- 數據過期 >48 小時 → 拒跑（spec §9）
- 只讀 pikmin 專案檔案，絕不修改（spec §4）
- 所有新模組放 repo 根目錄（跟隨既有扁平結構）；測試放 `tests/`

---

### Task 1: 修復 pikmin daily_reports 斷供（ops，前置）

**Files:**
- 只讀診斷：`/Users/arlong/Projects/pikmin-command-center/trading/daily_review.py`
- 可能修改：使用者 crontab（`crontab -e` 等效操作）

**Interfaces:**
- Produces: `daily_reports/YYYY-MM-DD.json` 恢復每日產出（Task 2 的資料來源活水）

- [ ] **Step 1: 診斷為什麼 6/11 之後沒有日報**

```bash
crontab -l | grep -i "daily_review\|pikmin"
tail -20 /tmp/pikmin_*.log 2>/dev/null
cd /Users/arlong/Projects/pikmin-command-center/trading && head -30 daily_review.py
```
判讀：cron 條目消失（補回）／腳本報錯（讀 log 修根因）／bot 本體停了（回報 arlong 決定）。

- [ ] **Step 2: 依診斷結果修復並手動跑一次驗證**

```bash
cd /Users/arlong/Projects/pikmin-command-center/trading && .venv/bin/python3 daily_review.py
ls -la daily_reports/ | tail -3   # 應出現今日 JSON
```
若根因是 bot 停止且需要 arlong 決策 → 停在這裡回報，MVP 其餘 task 用既有 55 份歷史日報繼續（`build_week_pack` 的 `end_date` 參數就是為此設計）。

- [ ] **Step 3: 若改了 crontab，記錄變更內容到本 plan 的執行筆記**

---

### Task 2: `market_data_ingest.py` — 數據包生成

**Files:**
- Create: `market_data_ingest.py`
- Create: `tests/test_market_data_ingest.py`
- Create: `tests/fixtures/daily_reports/`（3 份合成日報 fixture）

**Interfaces:**
- Produces: `build_week_pack(reports_dir: str, end_date: str | None = None) -> dict`
  回傳數據包 dict（schema 見 Step 1 測試）；`StaleDataError(Exception)`。
  Task 3/4/5/6 都吃這個 dict。

- [ ] **Step 1: 寫 fixture 與失敗測試**

`tests/fixtures/daily_reports/2026-06-09.json`：
```json
{"date": "2026-06-09", "equity": 1560.0, "total_pnl": -2.0, "total_pnl_pct": -0.128, "daily_change": -1.0, "daily_change_pct": -0.064, "realized_pnl": -9.0, "total_fees": 5.0, "total_trades": 480, "daily_trades": 6, "grid_cycles": 2, "grid_pnl": -10.0, "days_running": 47}
```
`2026-06-10.json`（equity 1562.5, daily_change 2.5, daily_change_pct 0.16, total_trades 490, daily_trades 10, days_running 48）與
`2026-06-11.json`（equity 1564.15, daily_change 1.65, daily_change_pct 0.106, total_trades 500, daily_trades 10, days_running 49）同 schema。

`tests/test_market_data_ingest.py`：
```python
import pytest
from market_data_ingest import build_week_pack, StaleDataError

FIX = "tests/fixtures/daily_reports"

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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_market_data_ingest.py -v`
Expected: FAIL（ModuleNotFoundError: market_data_ingest）

- [ ] **Step 3: 實作**

`market_data_ingest.py`：
```python
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


def build_week_pack(reports_dir: str = PIKMIN_REPORTS_DIR,
                    end_date: str | None = None) -> dict:
    """組出最近 7 天（或 fixture 範圍內）的週報數據包。

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

    window = [r for r in reports if r["date"] <= end_date][-7:]
    if not window:
        raise ValueError(f"no reports on or before {end_date}")

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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_market_data_ingest.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add market_data_ingest.py tests/
git commit -m "feat(trading-lab): market data ingest — pikmin daily reports to week pack"
```

---

### Task 3: `number_gate.py` — 數字對帳閘門

**Files:**
- Create: `number_gate.py`
- Create: `tests/test_number_gate.py`

**Interfaces:**
- Consumes: Task 2 的數據包 dict（任意巢狀 dict/list/數值/字串）
- Produces: `verify_numbers(text: str, pack: dict) -> list[str]`（回傳無法對帳的數字 token，空 list = 通過）；
  `assert_numbers_ok(text: str, pack: dict) -> None`（不過就 raise `NumberMismatch`）。
  Task 6 在 LLM 生成後、TTS 前呼叫 `assert_numbers_ok`。

- [ ] **Step 1: 寫失敗測試**

`tests/test_number_gate.py`：
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_number_gate.py -v`
Expected: FAIL（ModuleNotFoundError: number_gate）

- [ ] **Step 3: 實作**

`number_gate.py`：
```python
"""數字對帳閘門 — 腳本裡每個阿拉伯數字必須能在數據包裡找到出處。

這是「假內容」的結構性解法：LLM 只能敘述我們給的數字。任何多出來的
數字（幻覺、誇大、記憶殘留）都會被逐 token 攔下，fail-closed 拒絕渲染。
0-10 的小整數放行（「3 個重點」這類結構性計數）。
"""
import re

_SMALL_INT_WHITELIST = set(range(0, 11))
_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


class NumberMismatch(Exception):
    pass


def _formats_of(v: float) -> set[str]:
    """一個數值的所有可接受書寫形（含四捨五入到 0/1/2 位、絕對值）。"""
    out = set()
    for x in {v, abs(v)}:
        for nd in (0, 1, 2, 3):
            r = round(x, nd)
            s = f"{r:.{nd}f}".rstrip("0").rstrip(".") or "0"
            out.add(s)
            out.add(f"{float(s):,.{nd}f}".rstrip("0").rstrip("."))
    return out


def _allowed_tokens(pack) -> set[str]:
    allowed = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool):
            pass
        elif isinstance(v, (int, float)):
            allowed.update(_formats_of(float(v)))
        elif isinstance(v, str):
            # 日期等字串：拆出所有數字片段（2026-06-10 → 2026/06/6/10）
            for m in _TOKEN_RE.findall(v):
                allowed.add(m)
                allowed.add(m.lstrip("0") or "0")
    walk(pack)
    return allowed


def verify_numbers(text: str, pack: dict) -> list[str]:
    allowed = _allowed_tokens(pack)
    violations = []
    for tok in _TOKEN_RE.findall(text):
        plain = tok.replace(",", "")
        if plain in allowed or tok in allowed:
            continue
        try:
            if float(plain) in _SMALL_INT_WHITELIST and "." not in plain:
                continue
        except ValueError:
            pass
        violations.append(plain)
    return violations


def assert_numbers_ok(text: str, pack: dict) -> None:
    v = verify_numbers(text, pack)
    if v:
        raise NumberMismatch(
            f"script contains numbers with no source in the data pack: {v} "
            f"— refusing to render (fail-closed)")
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_number_gate.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add number_gate.py tests/test_number_gate.py
git commit -m "feat(trading-lab): number reconciliation gate — fail-closed on unsourced numbers"
```

---

### Task 4: `equity_chart.py` — 深色權益曲線圖（9:16）

**Files:**
- Create: `equity_chart.py`
- Create: `tests/test_equity_chart.py`

**Interfaces:**
- Consumes: Task 2 數據包（`daily_equity`、`daily_dates`、`week_pnl_pct`、`best_day`、`worst_day`、`is_paper`）
- Produces: `render_equity_chart(pack: dict, out_path: str) -> str`（存 1080x1920 PNG，回傳路徑）。
  Task 6 把它丟進 clips/ 前段。

- [ ] **Step 1: 寫失敗測試**

`tests/test_equity_chart.py`：
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_equity_chart.py -v`
Expected: FAIL（ModuleNotFoundError: equity_chart）

- [ ] **Step 3: 實作**

`equity_chart.py`：
```python
"""權益曲線 → 1080x1920 深色圖（延續頻道 noir 品牌感）。

固定角標「模擬盤實驗」— spec 防線 2：這行字由程式燒進圖，不依賴 LLM。
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

_CJK = None
for _p in ("/System/Library/Fonts/PingFang.ttc",
           "/System/Library/Fonts/STHeiti Light.ttc"):
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_equity_chart.py -v`
Expected: 1 passed

- [ ] **Step 5: 目檢一張真數據的圖（不是只看測試）**

```bash
python3 -c "
from market_data_ingest import build_week_pack
from equity_chart import render_equity_chart
p=build_week_pack(end_date='2026-06-11')
print(render_equity_chart(p, '/tmp/eq_real.png'))
"
```
用 Read 工具打開 `/tmp/eq_real.png` 目檢：中文沒有變豆腐字、曲線可讀、角標在。

- [ ] **Step 6: Commit**

```bash
git add equity_chart.py tests/test_equity_chart.py
git commit -m "feat(trading-lab): dark 9:16 equity chart with paper-trading badge"
```

---

### Task 5: `trading_script.py` — 週報腳本生成（含禁詞與免責）

**Files:**
- Create: `trading_script.py`
- Create: `tests/test_trading_script.py`

**Interfaces:**
- Consumes: Task 2 數據包；`script_generator._call_claude(prompt) -> dict`（既有，回傳 JSON dict）
- Produces: `generate_weekly_script(pack: dict) -> dict`，回傳
  `{"title", "hook", "sections": [{"text", "visual"} x3-4], "cta", "description", "hashtags"}`；
  內部已跑 `assert_numbers_ok` 與禁詞檢查（`BannedWordError`）。
  `DISCLAIMER = "模擬盤實驗紀錄，非投資建議"`（Task 6 引用）。

- [ ] **Step 1: 寫失敗測試（mock LLM，不花 API）**

`tests/test_trading_script.py`：
```python
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
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python3 -m pytest tests/test_trading_script.py -v`
Expected: FAIL（ModuleNotFoundError: trading_script）

- [ ] **Step 3: 實作**

`trading_script.py`：
```python
"""週報腳本生成 — LLM 只敘述數據包，數字閘門 + 禁詞雙 fail-closed。"""
import json

from number_gate import assert_numbers_ok

DISCLAIMER = "模擬盤實驗紀錄，非投資建議"

# spec §5.5 / §6：指向「保證/帶單」語意的詞，任何欄位出現即拒絕
BANNED_WORDS = ("保證獲利", "必賺", "穩賺", "跟單", "帶單", "老師",
                "財富自由", "躺賺")


class BannedWordError(Exception):
    pass


PROMPT_WEEKLY = """你是一個 faceless 短影音頻道的編劇。頻道記錄「AI 自動交易模擬盤實驗」。

【本週數據（唯一事實來源，嚴格遵守）】
{pack_json}

【鐵則】
1. 只能使用上面數據裡出現的數字，用阿拉伯數字書寫。禁止自創或推算任何新數字
   （0-10 的結構性計數除外，如「3 個重點」）。
2. 這是「模擬盤」（虛擬資金實驗）。不可暗示真金白銀或實際獲利。
3. 禁止投資建議、禁止推薦任何標的、禁止：保證獲利/必賺/穩賺/跟單/帶單/老師。
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


def _all_text(script: dict) -> str:
    parts = [script.get("title", ""), script.get("hook", ""),
             script.get("cta", ""), script.get("description", "")]
    parts += [s.get("text", "") for s in script.get("sections", [])]
    return "\n".join(parts)


def generate_weekly_script(pack: dict) -> dict:
    sign = "+" if pack["week_pnl_pct"] >= 0 else "-"
    prompt = PROMPT_WEEKLY.format(
        pack_json=json.dumps(pack, ensure_ascii=False, indent=1),
        week_number=pack["week_number"], sign=sign)
    script = _call_llm(prompt)

    text = _all_text(script)
    hits = [w for w in BANNED_WORDS if w in text]
    if hits:
        raise BannedWordError(
            f"banned words in script: {hits} — refusing to render")
    assert_numbers_ok(text, pack)

    if DISCLAIMER not in (script.get("description") or ""):
        script["description"] = (script.get("description", "").strip()
                                 + f"\n{DISCLAIMER}").strip()
    return script
```

- [ ] **Step 4: 跑測試確認通過**

Run: `python3 -m pytest tests/test_trading_script.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add trading_script.py tests/test_trading_script.py
git commit -m "feat(trading-lab): weekly script gen — data-pack injection, number gate + banned words fail-closed"
```

---

### Task 6: `generate_trading_reel.py` — 端到端 orchestrator

**Files:**
- Create: `generate_trading_reel.py`
- Test: 端到端實跑（本 task 的驗證即實渲染，不寫 mock 測試）

**Interfaces:**
- Consumes: `build_week_pack()`、`generate_weekly_script(pack)`、`render_equity_chart(pack, path)`、
  既有 `tts_generator.generate_voiceover(text, lang, path)`、
  `illustration_generator.generate_illustration(scene, path, style_prefix, aspect)`、
  `illustration_generator._make_ken_burns_clip`（PNG→motion clip 用 `_image_to_video` 亦可）、
  `video_assembler.assemble_video(output_dir, lang="zh", fmt="short")`、
  `subtitle_generator.generate_srt`、`export_reel.package(output_dir)`
- Produces: `output/YYYYMMDD_trading/upload_package/`（video.mp4 + captions + cover）

- [ ] **Step 1: 實作 orchestrator**

`generate_trading_reel.py`：
```python
"""AI 交易實驗室 — 週報 reel 端到端。

用法：python generate_trading_reel.py [--end-date YYYY-MM-DD]
（--end-date 供回填/測試；正式跑不帶參數，吃最新數據 + 過期檢查）
"""
import argparse
import json
import os
from datetime import datetime

from market_data_ingest import build_week_pack
from trading_script import generate_weekly_script, DISCLAIMER
from equity_chart import render_equity_chart


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-date", default=None)
    args = ap.parse_args()

    print("[1/6] 數據包...")
    pack = build_week_pack(end_date=args.end_date)
    print(json.dumps(pack, ensure_ascii=False)[:200])

    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join("output", f"{date_str}_trading_w{pack['week_number']}")
    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    print("[2/6] 腳本（含數字對帳 + 禁詞閘門）...")
    script = generate_weekly_script(pack)
    print(f"  title: {script['title']}")

    # metadata.json — export_reel 打包與 QA 都吃這份
    meta = {"zh": {**script, "opening_card": script["title"][:8],
                   "pinned_comment": ""}}
    with open(os.path.join(output_dir, "metadata.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("[3/6] 視覺素材...")
    chart_png = os.path.join(output_dir, "equity_chart.png")
    render_equity_chart(pack, chart_png)
    # 場景圖：noir 桌面/機房氛圍插圖（Imagen，禁真人 prefix），hook 與 outro 用
    from illustration_generator import generate_illustration
    from agents.visual_agent import CRIME_STYLE_PREFIX
    prefix = CRIME_STYLE_PREFIX.replace("cinematic 16:9",
                                        "vertical cinematic composition")
    hook_png = os.path.join(output_dir, "hook_scene.png")
    generate_illustration(
        "glowing computer screen with trading charts in a dark room, "
        "single desk lamp", hook_png, style_prefix=prefix, aspect="9:16")

    # PNG → clips/（沿用 Ken Burns 動態；圖表用輕微 zoom 保持可讀）
    from illustration_generator import _make_ken_burns_clip
    import numpy as np
    from PIL import Image as PILImage
    for i, (png, dur) in enumerate([(hook_png, 8.0), (chart_png, 20.0),
                                    (hook_png, 8.0)]):
        img = np.array(PILImage.open(png).convert("RGB"))
        clip = _make_ken_burns_clip(img, duration=dur,
                                    target_w=1080, target_h=1920)
        clip.write_videofile(os.path.join(clips_dir, f"s{i:02d}_clip1.mp4"),
                             fps=25, codec="libx264", audio=False, logger=None)
        clip.close()

    print("[4/6] TTS + 字幕...")
    full_text = "。".join([script["hook"]]
                          + [s["text"] for s in script["sections"]]
                          + [script["cta"]])
    from tts_generator import generate_voiceover
    vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
    generate_voiceover(full_text, "zh", vo_path)
    from moviepy.editor import AudioFileClip
    a = AudioFileClip(vo_path); vo_dur = a.duration; a.close()
    from subtitle_generator import generate_srt
    generate_srt(full_text, vo_dur, os.path.join(output_dir, "subtitles_zh.srt"))

    print("[5/6] 組裝（fmt=short 9:16）...")
    from video_assembler import assemble_video
    final = assemble_video(output_dir, lang="zh", fmt="short")
    if not final:
        raise RuntimeError("assemble_video returned None")

    print("[6/6] 打包 upload_package...")
    from export_reel import package
    pkg = package(output_dir)
    print(f"完成：{pkg}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 端到端實跑（用歷史數據回填）**

Run: `python3 generate_trading_reel.py --end-date 2026-06-11`
Expected: 6 步全過，`output/*_trading_w7/upload_package/` 有 video.mp4 + caption_tiktok.txt + caption_fb.txt

- [ ] **Step 3: 視覺驗收（visual-acceptance 慣例）**

抽 frame 檢查：圖表清楚可讀、「模擬盤實驗」角標在、中文字型正常、
無禁詞、caption 首行含免責聲明。有問題先修再交。

- [ ] **Step 4: Commit**

```bash
git add generate_trading_reel.py
git commit -m "feat(trading-lab): end-to-end weekly report reel orchestrator"
```

---

### Task 7: 收尾 — memory 與交付

**Files:**
- Modify: memory `project_pivot_tiktok_fb.md`（標注 A+B 已由本方向取代）
- Create: memory `project_ai_trading_lab.md`

- [ ] **Step 1: 寫 memory（新方向狀態、四模組介面、樣片位置）**
- [ ] **Step 2: 樣片 + upload_package 交付 arlong（SendUserFile）**
- [ ] **Step 3: 回報：品牌名待定、referral 連結待 arlong 提供、下一循環（Polymarket 拆解型）排程**

## Self-Review 紀錄

- Spec 覆蓋：§2 數據源→Task 1/2；§4 架構四模組→Task 2/3/4/5+6；§5 防線 1→Task 3、
  防線 2→Task 4（角標）+Task 5（prompt）、防線 3→Task 5 prompt 鐵則 4、防線 4→prompt 鐵則 5、
  防線 5→Task 5 BANNED_WORDS；§6 法遵→DISCLAIMER+禁詞；§8 MVP 全項有對應 task ✓
- 型別一致性：pack schema（Task 2 產出）與 Task 3/4/5 測試中的 PACK 欄位一致 ✓
- 無 TBD/佔位 ✓
