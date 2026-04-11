#!/usr/bin/env python3
"""
Daily morning summary + audit for the AIvideo pipeline.

Replaces the original "audit only on failure" behavior with a comprehensive
once-per-day summary covering both crime and books channels. Always sends
a Telegram message so the user has a single morning checkpoint.

Sections in the summary:
  - Crime: upload count in last 24h, list of new videos, slot coverage
  - Books: today's render status (only fires Tue/Fri), local mp4 path
  - System: health check pass/fail, Imagen quota left, disk space

Triggered by `com.aivideo.audit` launchd at 09:00 Taiwan daily — chosen to
fire AFTER the 08:30 books run completes (Tue/Fri), so books status is
included in the same notification.

Usage:
  python daily_audit.py                 # full summary, alert on issues
  python daily_audit.py --verbose       # verbose stdout
  python daily_audit.py --no-telegram   # don't send Telegram (for testing)
  python daily_audit.py --min-count 2   # min crime uploads to count as OK
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_LOG = os.path.join(PROJECT_DIR, "video_log.json")


def _git_pull_quiet():
    """Pull latest state files from GH Actions before reading video_log.json.

    Since crime pipeline runs on GH Actions (not local), video_log.json is
    updated by GH Actions commits, not local writes. Without this pull, the
    audit reads stale local data and falsely reports 0 uploads.
    Added 2026-04-11 after discovering the local-only audit missed all
    GH Actions uploads.
    """
    import subprocess
    try:
        subprocess.run(
            ["git", "-C", PROJECT_DIR, "pull", "--rebase", "--quiet"],
            capture_output=True, timeout=30,
        )
    except Exception:
        pass  # Non-critical — proceed with whatever local state we have
BOOKS_USED_TOPICS = os.path.join(PROJECT_DIR, "data", "books", "used_topics.json")
IMAGEN_QUOTA_FILE = os.path.join(PROJECT_DIR, "data", "imagen_quota.json")


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ── Crime upload audit ────────────────────────────────────────────────────────

def crime_audit(window_hours: int, min_count: int) -> dict:
    """Returns {ok, count, recent (list of (dt, video))}."""
    data = _load_json(VIDEO_LOG, {"videos": []})
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    recent = []
    for v in data.get("videos", []):
        ts = v.get("uploaded_at", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt >= cutoff:
            recent.append((dt, v))

    recent.sort(key=lambda x: x[0], reverse=True)
    return {
        "ok": len(recent) >= min_count,
        "count": len(recent),
        "min_count": min_count,
        "recent": recent,
    }


# ── Books today audit ─────────────────────────────────────────────────────────

def books_today_status() -> dict:
    """Check whether today is a books-scheduled day (Tue/Fri) and whether
    a books output dir was created today."""
    today_local = datetime.now()
    weekday = today_local.weekday()  # Mon=0..Sun=6
    is_books_day = weekday in (1, 4)  # Tue or Fri

    today_str = today_local.strftime("%Y%m%d")
    output_dir = os.path.join(PROJECT_DIR, "output")
    today_books_dirs = []
    if os.path.exists(output_dir):
        for name in os.listdir(output_dir):
            if name.startswith(f"{today_str}_books") and os.path.isdir(
                os.path.join(output_dir, name)
            ):
                full = os.path.join(output_dir, name)
                final_mp4 = os.path.join(full, "final_zh.mp4")
                if os.path.exists(final_mp4):
                    today_books_dirs.append(full)

    return {
        "is_books_day": is_books_day,
        "weekday_name": ["週一","週二","週三","週四","週五","週六","週日"][weekday],
        "completed": len(today_books_dirs) > 0,
        "output_dirs": today_books_dirs,
    }


# ── System health ─────────────────────────────────────────────────────────────

def system_health() -> dict:
    """Quick local checks for the morning summary."""
    free_gb = shutil.disk_usage(PROJECT_DIR).free / (1024 ** 3)

    quota = _load_json(IMAGEN_QUOTA_FILE, {"count": 0, "limit": 70})
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if quota.get("date") != today_utc:
        # Tracker is for a previous UTC day → assume reset
        quota_count = 0
    else:
        quota_count = quota.get("count", 0)

    return {
        "free_gb": free_gb,
        "imagen_used": quota_count,
        "imagen_limit": quota.get("limit", 70),
    }


# ── Build the message ─────────────────────────────────────────────────────────

def build_summary(crime: dict, books: dict, system: dict) -> str:
    now = datetime.now()
    weekday_zh = ["週一","週二","週三","週四","週五","週六","週日"][now.weekday()]
    header = f"🌅 [AIvideo 每日摘要] {now.strftime('%Y-%m-%d')} {weekday_zh}\n"

    # Crime section
    if crime["ok"]:
        crime_status = f"✅ 過去 24h: {crime['count']} 支上傳"
    else:
        crime_status = (
            f"⚠️ 過去 24h: 只有 {crime['count']} 支上傳 (預期 ≥{crime['min_count']})"
        )
    crime_lines = ["🎬 Crime", "  " + crime_status]
    for dt, v in crime["recent"][:5]:
        topic = v.get("topic", "")[:36]
        vid = v.get("video_id", "")
        url = f"https://youtu.be/{vid}" if vid else "(no id)"
        crime_lines.append(f"  • {topic}\n    {url}")

    # Books section
    if books["is_books_day"]:
        if books["completed"]:
            books_status = (
                f"✅ {books['weekday_name']}的 v5 已完成 — {len(books['output_dirs'])} 支"
            )
            for d in books["output_dirs"][:2]:
                books_status += f"\n  • {os.path.basename(d)}"
        else:
            books_status = f"⏳ {books['weekday_name']}的 v5 還沒完成或失敗"
    else:
        books_status = f"📅 {books['weekday_name']}非排程日（Tue/Fri 才跑）"
    books_lines = ["📚 Books", "  " + books_status]

    # System section
    sys_lines = [
        "🩺 系統",
        f"  Imagen quota: {system['imagen_used']}/{system['imagen_limit']} 用",
        f"  磁碟: {system['free_gb']:.1f} GB free",
    ]

    parts = [
        header,
        "\n".join(crime_lines),
        "",
        "\n".join(books_lines),
        "",
        "\n".join(sys_lines),
    ]
    return "\n".join(parts)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum crime uploads in window before flagging")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-telegram", action="store_true",
                        help="Skip Telegram send (for local testing)")
    args = parser.parse_args()

    # Sync latest GH Actions state before reading local files
    _git_pull_quiet()

    crime = crime_audit(args.window_hours, args.min_count)
    books = books_today_status()
    system = system_health()

    msg = build_summary(crime, books, system)

    if args.verbose:
        print(msg)
        print()
        print(f"Crime ok: {crime['ok']}, Books day: {books['is_books_day']}")

    if not args.no_telegram:
        try:
            from telegram_notify import _send_raw
            _send_raw(msg)
            if args.verbose:
                print("\n[Telegram sent]")
        except Exception as e:
            print(f"  [WARN] Telegram send failed: {e}", file=sys.stderr)

    # Exit code reflects whether crime audit passed (for launchd visibility)
    sys.exit(0 if crime["ok"] else 1)


if __name__ == "__main__":
    main()
