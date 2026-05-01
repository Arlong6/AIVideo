#!/usr/bin/env bash
# Long-form Week-1 evaluation — fires once on 2026-05-05.
# Compares the 3 manually-triggered long-form videos' performance after ~7 days.

set -e
cd "$(dirname "$0")"
PY=/Users/arlong/.pyenv/versions/3.10.11/bin/python3

echo "=== Long-form 一週評估 — $(date) ==="

$PY <<'PYEOF'
import warnings; warnings.filterwarnings("ignore")
import sys
from youtube_uploader import _get_credentials
from googleapiclient.discovery import build

sys.path.insert(0, "/Users/arlong/Projects/shared_telegram")
from telegram_hub import get_hub, Tag

# 4 candidates: 3 long-form + their best Short for comparison
LONGFORMS = [
    ("BLr8ubLyzl4", "D.B. 庫柏 long",  "4N7z7JS_gi8", "D.B. Short (732v)"),
    ("K8GKTrNrupk", "芭提雅 long",      "yzNtfEOc2fE", "芭提雅 Short (208v)"),
    ("zpnz_Xxpw98", "陳高連葉案 long",  None, None),
]

yt = build("youtube", "v3", credentials=_get_credentials())
ids = []
for long_id, _, short_id, _ in LONGFORMS:
    ids.append(long_id)
    if short_id: ids.append(short_id)

resp = yt.videos().list(part="statistics,snippet,status", id=",".join(ids)).execute()
items = {it["id"]: it for it in resp.get("items", [])}

def stats(vid):
    if vid not in items: return None
    s = items[vid].get("statistics", {})
    return {
        "views": int(s.get("viewCount", 0)),
        "likes": int(s.get("likeCount", 0)),
        "comments": int(s.get("commentCount", 0)),
        "title": items[vid]["snippet"]["title"][:40],
    }

lines = ["📊 <b>Long-form 一週評估（4/28 → 5/5）</b>", "━" * 18, ""]
total_long_views = 0
green = 0
for long_id, long_name, short_id, short_name in LONGFORMS:
    ls = stats(long_id)
    if not ls: continue
    total_long_views += ls["views"]
    is_green = ls["views"] >= 100  # threshold for "algorithm picked up"
    if is_green: green += 1
    emoji = "🟢" if is_green else ("🟡" if ls["views"] >= 30 else "🔴")
    lines.append(f"{emoji} <b>{long_name}</b>")
    lines.append(f"  {ls['views']} views / {ls['likes']} likes / {ls['comments']} comments")
    if short_id:
        ss = stats(short_id)
        if ss:
            ratio = ss["views"] / max(ls["views"], 1)
            lines.append(f"  vs {short_name}: 比例 1:{ratio:.0f}")
    lines.append("")

verdict = "🟢 演算法開始推送 — 可以繼續做" if green >= 2 else \
          "🟡 部分起色 — 再觀察一週" if green == 1 else \
          "🔴 三支都死 — 停止做 long-form，回頭做 Shorts"

lines.append("━" * 18)
lines.append(f"<b>結論：</b>{verdict}")
lines.append(f"3 支 long 累計 {total_long_views} views（門檻：每支 ≥100v 算成功）")

msg = "\n".join(lines)
print(msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>",""))
get_hub()._post(f"[{Tag.AIVIDEO}]\n{msg}")
print("\nSent to Telegram.")
PYEOF

# Self-disable
launchctl unload ~/Library/LaunchAgents/com.aivideo.longform_week1.plist 2>/dev/null || true
mv ~/Library/LaunchAgents/com.aivideo.longform_week1.plist \
   ~/Library/LaunchAgents/com.aivideo.longform_week1.plist.fired 2>/dev/null || true
echo "=== eval done, plist disabled ==="
