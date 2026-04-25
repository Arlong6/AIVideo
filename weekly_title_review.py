"""Weekly Title DNA review — analyzes last 7 days of video titles for
formula/trigger-word coverage and performance, posts to Telegram.

Runs on GitHub Actions every Sunday 02:00 UTC (10:00 TW).
"""
import json
import os
import pickle
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from googleapiclient.discovery import build

from telegram_notify import _send_raw
from title_dna import POWER_WORDS, TITLE_DNA

load_dotenv()


def _load_titles_and_views(days: int = 7) -> list[dict]:
    """Return list of {video_id, title, views, uploaded_at, is_short} for
    videos uploaded in the last N days."""
    log = json.load(open("video_log.json"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    recent = []
    for v in log["videos"]:
        ts = v.get("uploaded_at", "")
        if not ts:
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if t < cutoff:
            continue
        recent.append(v)

    if not recent:
        return []

    # Fetch fresh titles + view counts via YouTube API
    with open("youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    yt = build("youtube", "v3", credentials=creds)

    out = []
    ids = [v["video_id"] for v in recent]
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        r = yt.videos().list(
            part="snippet,statistics,contentDetails", id=",".join(chunk)
        ).execute()
        for item in r.get("items", []):
            vid = item["id"]
            src = next((v for v in recent if v["video_id"] == vid), {})
            out.append({
                "video_id": vid,
                "title": item["snippet"]["title"],
                "views": int(item["statistics"].get("viewCount", 0)),
                "uploaded_at": src.get("uploaded_at", ""),
                "is_short": src.get("duration_s", 0) <= 120,
            })
    return out


def _flat_trigger_words() -> dict[str, list[str]]:
    """Return {power_word: [variant_strings]} — splits "竟/竟然" into ["竟", "竟然"]."""
    out = {}
    for word in POWER_WORDS:
        out[word] = [w.strip() for w in word.split("/") if w.strip()]
    # Special case: "年份數字" — match any 4-digit year 19xx/20xx
    out["年份數字"] = ["__YEAR_REGEX__"]
    return out


def _title_uses_word(title: str, variants: list[str]) -> bool:
    if variants == ["__YEAR_REGEX__"]:
        import re
        return bool(re.search(r"(19|20)\d{2}", title))
    return any(v in title for v in variants)


def _formula_matches(title: str) -> list[str]:
    """Return list of formula names whose trigger_words appear in title."""
    matched = []
    for name, data in TITLE_DNA.items():
        words = data.get("trigger_words", [])
        if any(w in title for w in words):
            matched.append(name)
    return matched


def _check_self_check(title: str) -> dict:
    """Apply 6-point self-check. Return dict of pass/fail per rule."""
    trigger_map = _flat_trigger_words()
    has_trigger = any(_title_uses_word(title, v) for v in trigger_map.values())
    return {
        "trigger_word": has_trigger,
        "length_ok": len(title) <= 25,
        "no_colon": "：" not in title and ":" not in title,
        "has_specific": any(c.isdigit() for c in title)
            or any(t in title for t in ["歲", "年", "人", "天"]),
        "no_shocking_start": not title.startswith("震驚"),
    }


def _build_report(videos: list[dict]) -> str:
    if not videos:
        return "📊 <b>Weekly Title DNA Review</b>\n\n過去 7 天無新影片。"

    trigger_map = _flat_trigger_words()
    formula_stats = defaultdict(lambda: {"count": 0, "views": 0, "titles": []})
    word_stats = defaultdict(lambda: {"count": 0, "views": 0})
    no_formula = []
    self_check_fails = []

    for v in videos:
        title = v["title"]
        views = v["views"]
        formulas = _formula_matches(title)
        if not formulas:
            no_formula.append(v)
        for f in formulas:
            formula_stats[f]["count"] += 1
            formula_stats[f]["views"] += views
            formula_stats[f]["titles"].append((title, views))
        for word, variants in trigger_map.items():
            if _title_uses_word(title, variants):
                word_stats[word]["count"] += 1
                word_stats[word]["views"] += views

        sc = _check_self_check(title)
        failed = [k for k, ok in sc.items() if not ok]
        if failed:
            self_check_fails.append((title, failed, views))

    # Sort formulas by avg views desc
    formula_avg = sorted(
        [(name, s["count"], s["views"] / max(s["count"], 1))
         for name, s in formula_stats.items()],
        key=lambda x: -x[2],
    )
    # Sort words by avg views desc (only words actually used)
    word_avg = sorted(
        [(w, s["count"], s["views"] / max(s["count"], 1))
         for w, s in word_stats.items() if s["count"] > 0],
        key=lambda x: -x[2],
    )

    n = len(videos)
    total_views = sum(v["views"] for v in videos)
    avg_views = total_views / n
    n_short = sum(1 for v in videos if v["is_short"])

    lines = [
        f"📊 <b>Weekly Title DNA Review</b>",
        f"區間：過去 7 天",
        f"影片數：{n} ({n_short} shorts / {n - n_short} long)",
        f"總觀看：{total_views:,} ｜ 平均：{avg_views:.1f}",
        "",
        "<b>📐 標題公式表現（按平均觀看排序）</b>",
    ]
    if formula_avg:
        for name, cnt, avg in formula_avg:
            lines.append(f"  {name}: {cnt}部 / 平均 {avg:.0f} views")
    else:
        lines.append("  (無影片匹配任何公式)")

    no_match_pct = len(no_formula) / n * 100
    lines.append(f"  ⚠️ 無公式匹配：{len(no_formula)}部 ({no_match_pct:.0f}%)")

    lines.append("")
    lines.append("<b>🔥 觸發詞使用 TOP 5（按平均觀看）</b>")
    if word_avg:
        for w, cnt, avg in word_avg[:5]:
            lines.append(f"  「{w}」x{cnt} → 平均 {avg:.0f} views")
    else:
        lines.append("  (無高效觸發詞使用)")

    unused = [w for w in POWER_WORDS if w not in {x[0] for x in word_avg}]
    if unused:
        lines.append("")
        lines.append(f"<b>❌ 未使用的觸發詞 ({len(unused)}/{len(POWER_WORDS)})</b>")
        lines.append("  " + "、".join(unused[:8]))

    if self_check_fails:
        lines.append("")
        lines.append(f"<b>⚠️ 自檢未通過 ({len(self_check_fails)}/{n})</b>")
        for title, failed, views in self_check_fails[:5]:
            short = title[:30] + ("…" if len(title) > 30 else "")
            lines.append(f"  「{short}」views={views}")
            lines.append(f"     缺：{', '.join(failed)}")

    # Top + bottom title examples
    sorted_v = sorted(videos, key=lambda x: -x["views"])
    lines.append("")
    lines.append("<b>🏆 Top 3 標題</b>")
    for v in sorted_v[:3]:
        t = v["title"][:40] + ("…" if len(v["title"]) > 40 else "")
        lines.append(f"  {v['views']:>4} | {t}")
    if len(sorted_v) > 3:
        lines.append("<b>📉 Bottom 3 標題</b>")
        for v in sorted_v[-3:]:
            t = v["title"][:40] + ("…" if len(v["title"]) > 40 else "")
            lines.append(f"  {v['views']:>4} | {t}")

    return "\n".join(lines)


def main():
    videos = _load_titles_and_views(days=7)
    msg = _build_report(videos)
    print(msg)
    _send_raw(msg)


if __name__ == "__main__":
    main()
