"""
Detect Shorts that have crossed the upgrade threshold but haven't been
promoted to long-form yet. Sends a Telegram alert with one-liner gh
commands so the upgrade can be triggered with a single tap.

Why: 5 viral Shorts (>=300v) currently have zero long-form successor,
because the manual workflow_dispatch loop has no detection layer.
This script is the detection layer — it doesn't auto-dispatch (yet),
it surfaces candidates so arlong can pull the trigger.

Threshold (default 300v) is configurable via UPGRADE_THRESHOLD env.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VIDEO_LOG = ROOT / "video_log.json"
SHORT_DURATION_S = 90
DEFAULT_THRESHOLD = int(os.environ.get("UPGRADE_THRESHOLD", "300"))

# Mirror of topic_manager._GEO_PREFIXES — 2-char prefixes that are NOT
# proper-noun case identifiers (台灣-鐵路 and 台灣-江國慶 share '台灣'
# but are different cases).
_GEO_PREFIXES = {
    "台灣", "台北", "台南", "台中", "高雄", "桃園", "新北", "彰化",
    "嘉義", "屏東", "花蓮", "基隆", "新竹", "苗栗", "南投", "雲林",
    "宜蘭", "澎湖", "金門", "馬祖",
    "韓國", "中國", "日本", "美國", "英國", "法國", "德國", "泰國",
    "印尼", "越南", "菲律", "馬來", "柬埔", "俄羅", "加拿", "澳洲",
    "東京", "京都", "大阪", "首爾", "釜山", "北京", "上海", "香港",
    "澳門", "深圳", "廣州", "名古",
}
_GENERIC_SUFFIXES = ("案", "事件", "命案", "懸案", "冤案", "謎案", "凶案")

# Title corrections — the Short was published with a factually wrong frame.
# When surfacing the long-form dispatch command, use the corrected topic so
# the LLM script isn't seeded with the error. Keyed by Short video_id.
# Ref: feedback_absolute_truth_requirement (every topic must be verifiable).
_TITLE_CORRECTIONS = {
    # 耕讀園: Short said "四死懸案" — actual case is 3死2傷 and fully solved
    # (林明樺 suicided; 李嘉軒+紀俊毅 executed 2013). 2004-11-27 Taichung.
    "lXyGNSp3e9Y": "台中耕讀園槍擊案：2004年茶館談判破裂的黑道火拼，3死2傷、4嫌落網",
}


def _cjk_only(s: str) -> str:
    return re.sub(r"[^一-鿿]", "", s)


def _topic_head(topic: str) -> str:
    """Strip body after full-width punctuation or ASCII colon/comma.

    Keeps ASCII period — 'D.B.庫柏' must stay intact, since D.B. is part
    of the case name. Common punctuation that signals subtitle/body:
    full-width colon/comma/period and ASCII colon/comma.
    """
    head = re.split(r"[：:，,。、]", topic, maxsplit=1)[0]
    return head.strip()


def _key_windows(topic: str) -> set:
    """Build proper-noun windows for cross-matching, mirroring
    topic_manager._is_too_similar logic but tolerant of leading GEO."""
    head = _topic_head(topic)
    cjk = _cjk_only(head)
    # Strip generic suffix(es) once to expose proper-noun stem
    for suf in _GENERIC_SUFFIXES:
        if cjk.endswith(suf) and len(cjk) > len(suf):
            cjk = cjk[: -len(suf)]
            break
    if len(cjk) < 2:
        return set()
    windows = set()
    if len(cjk) >= 3:
        for i in range(len(cjk) - 2):
            windows.add(cjk[i:i + 3])
    prefix2 = cjk[:2]
    if prefix2 not in _GEO_PREFIXES:
        windows.add(prefix2)
    # Also try the slot after a GEO prefix as proper-noun anchor:
    # e.g. '台灣江國慶' → '江國' window
    if prefix2 in _GEO_PREFIXES and len(cjk) >= 4:
        windows.add(cjk[2:4])
    return windows


def _has_longform_match(short_topic: str, longform_topics: list[str]) -> bool:
    """True if any window from short_topic appears as substring in any
    long-form topic's CJK-only head."""
    short_wins = _key_windows(short_topic)
    if not short_wins:
        return False
    long_heads = [_cjk_only(_topic_head(t)) for t in longform_topics]
    for w in short_wins:
        for h in long_heads:
            if w in h:
                return True
    return False


def _latest_views(stats: list[dict]) -> int:
    if not stats:
        return 0
    return max((s.get("views", 0) for s in stats), default=0)


def find_candidates(threshold: int = DEFAULT_THRESHOLD) -> list[dict]:
    log = json.loads(VIDEO_LOG.read_text())
    videos = log.get("videos", [])

    longform_topics = [
        v.get("topic", "")
        for v in videos
        if v.get("duration_s", 0) > SHORT_DURATION_S
    ]

    candidates = []
    for v in videos:
        if v.get("duration_s", 999) > SHORT_DURATION_S:
            continue
        if v.get("source") == "shorts_upgrade":
            continue
        views = _latest_views(v.get("stats", []))
        if views < threshold:
            continue
        topic = (v.get("topic") or "").strip()
        if not topic:
            continue
        if _has_longform_match(topic, longform_topics):
            continue
        vid = v.get("video_id")
        candidates.append({
            "video_id": vid,
            "topic": topic,
            "dispatch_topic": _TITLE_CORRECTIONS.get(vid, topic),
            "views": views,
            "uploaded_at": v.get("uploaded_at", "")[:10],
        })

    candidates.sort(key=lambda c: c["views"], reverse=True)
    return candidates


def format_dispatch_cmd(topic: str) -> str:
    safe_topic = topic.replace('"', '\\"')
    return (
        f'gh workflow run longform.yml '
        f'-f topic="{safe_topic}" -f source_tag="shorts_upgrade"'
    )


def main():
    threshold = DEFAULT_THRESHOLD
    candidates = find_candidates(threshold)

    print(f"=== Shorts→Long-form Upgrade Candidates (≥{threshold}v) ===")
    if not candidates:
        print("None. All viral Shorts have been upgraded or queued.")
        return 0

    print(f"Found {len(candidates)} pending candidate(s):\n")
    for c in candidates:
        flag = " ⚠️title-corrected" if c["dispatch_topic"] != c["topic"] else ""
        print(f"  {c['views']:>5}v  {c['video_id']:11}  {c['uploaded_at']}  {c['topic'][:50]}{flag}")

    try:
        from telegram_notify import _send_raw
        lines = [
            f"🎯 <b>Shorts 升級候選</b> (≥{threshold}v 未升級)",
            f"共 {len(candidates)} 部待處理:",
            "",
        ]
        for c in candidates[:5]:
            corrected = c["dispatch_topic"] != c["topic"]
            label = c["topic"][:35] + (" ⚠️已修正標題" if corrected else "")
            lines.append(f"• {c['views']}v · {label}")
            lines.append(f"  <code>{format_dispatch_cmd(c['dispatch_topic'])}</code>")
            lines.append("")
        _send_raw("\n".join(lines))
        print("\n✓ Telegram 已通知")
    except Exception as e:
        print(f"\n  Telegram failed (non-fatal): {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
