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


def _git_pull_quiet() -> tuple[bool, str]:
    """Pull latest state files from GH Actions before reading video_log.json.

    Since crime pipeline runs on GH Actions (not local), video_log.json is
    updated by GH Actions commits, not local writes. Without this pull, the
    audit reads stale local data and falsely reports 0 uploads.

    Returns (ok, msg). Audit 2026-04-30 worth-knowing #4: previously this
    silently swallowed every failure, so a stale audit (e.g. dirty tree
    blocking rebase, network down) looked identical to a healthy one.
    Now the caller can warn instead of pretending sync succeeded.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "-C", PROJECT_DIR, "pull", "--rebase", "--quiet"],
            capture_output=True, timeout=30, text=True,
        )
        if result.returncode == 0:
            return True, "ok"
        return False, (result.stderr or result.stdout or "non-zero exit").strip()[:200]
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:200]
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
    # Use PT date for quota (Google resets at PT midnight)
    try:
        from zoneinfo import ZoneInfo
        pt_today = datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    except Exception:
        pt_today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if quota.get("date") != pt_today:
        quota_count = 0
    else:
        quota_count = quota.get("count", 0)

    return {
        "free_gb": free_gb,
        "imagen_used": quota_count,
        "imagen_limit": quota.get("limit", 70),
    }


# ── Incomplete renders ────────────────────────────────────────────────────────

def pending_renders() -> list[dict]:
    """Find incomplete books renders (have metadata but no final video)."""
    output_dir = os.path.join(PROJECT_DIR, "output")
    if not os.path.exists(output_dir):
        return []
    results = []
    for name in sorted(os.listdir(output_dir)):
        if "books" not in name:
            continue
        d = os.path.join(output_dir, name)
        if not os.path.isdir(d):
            continue
        meta = os.path.join(d, "metadata.json")
        final1 = os.path.join(d, "final_zh.mp4")
        final2 = os.path.join(d, "final_zh_with_intro.mp4")
        if os.path.exists(meta) and not os.path.exists(final1) and not os.path.exists(final2):
            illust_dir = os.path.join(d, "illustrations")
            done = len(os.listdir(illust_dir)) if os.path.exists(illust_dir) else 0
            # Estimate total from metadata
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    zh = json.load(f).get("zh", {})
                script_len = len(zh.get("script", ""))
                est_total = max(script_len // 80, done + 10)  # rough estimate
            except Exception:
                est_total = done + 20
            results.append({
                "dir": name,
                "done": done,
                "est_total": est_total,
                "needed": max(0, est_total - done),
            })
    return results


# ── Recent errors ─────────────────────────────────────────────────────────────

def recent_errors() -> list[str]:
    """Scan today's log files for errors/failures."""
    log_dir = os.path.join(PROJECT_DIR, "logs")
    today_str = datetime.now().strftime("%Y%m%d")
    errors = []
    for name in os.listdir(log_dir) if os.path.exists(log_dir) else []:
        if today_str not in name and (datetime.now() - timedelta(days=1)).strftime("%Y%m%d") not in name:
            continue
        path = os.path.join(log_dir, name)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if any(kw in line.lower() for kw in ["fail", "error", "❌", "traceback"]):
                        errors.append(f"{name}: {line.strip()[:80]}")
        except Exception:
            pass
    return errors[:5]  # max 5


# ── Build the message ─────────────────────────────────────────────────────────

def build_summary(crime: dict, books: dict, system: dict,
                   pending: list, errors: list) -> str:
    now = datetime.now()
    weekday_zh = ["週一","週二","週三","週四","週五","週六","週日"][now.weekday()]
    header = f"🌅 [AIvideo 每日摘要] {now.strftime('%Y-%m-%d')} {weekday_zh}\n"

    # ── Yesterday recap ──────────────────────────────────────
    if crime["ok"]:
        crime_status = f"✅ 過去 24h: {crime['count']} 支上傳"
    else:
        crime_status = (
            f"⚠️ 過去 24h: 只有 {crime['count']} 支上傳 (預期 ≥{crime['min_count']})"
        )
    crime_lines = ["🎬 Crime（昨日）", "  " + crime_status]
    for dt, v in crime["recent"][:3]:
        topic = v.get("topic", "")[:36]
        vid = v.get("video_id", "")
        url = f"https://youtu.be/{vid}" if vid else ""
        crime_lines.append(f"  • {topic}\n    {url}")

    # ── Today's schedule ─────────────────────────────────────
    schedule_lines = [
        "📋 今日排程",
        "  02:00 Crime Shorts × 2 (GH Actions)",
        "  09:00 本摘要",
        "  14:00 Crime 長影片 (GH Actions, private)",
    ]

    # Books plan depends on pending renders
    quota_avail = system["imagen_limit"] - system["imagen_used"]
    if pending:
        p = pending[0]
        schedule_lines.append(
            f"  15:30 Books 續跑: {p['dir']}"
            f"\n        進度 {p['done']}/~{p['est_total']}，需 ~{p['needed']} 張"
        )
        remaining_after = max(0, quota_avail - p["needed"])
        if remaining_after > 20:
            schedule_lines.append(
                f"  15:30 額度剩 ~{remaining_after} → 開始新影片"
            )
    else:
        schedule_lines.append("  15:30 Books 新影片 (自動選題)")
    schedule_lines.append("  21:00 健康檢查")

    # ── Books status ─────────────────────────────────────────
    books_lines = ["📚 Books"]
    if books["completed"]:
        books_lines.append(
            f"  ✅ 今日已完成 {len(books['output_dirs'])} 支"
        )
    if pending:
        for p in pending:
            books_lines.append(
                f"  ⏳ 未完成: {p['dir']} ({p['done']}/~{p['est_total']})"
            )
    if not books["completed"] and not pending:
        books_lines.append("  📅 尚未開始，15:30 自動執行")

    # ── System ───────────────────────────────────────────────
    sys_lines = [
        "🩺 系統",
        f"  Imagen: {system['imagen_used']}/{system['imagen_limit']} 用"
        f" (可用 {quota_avail})",
        f"  磁碟: {system['free_gb']:.1f} GB free",
    ]

    # ── Errors ───────────────────────────────────────────────
    error_lines = []
    if errors:
        error_lines = ["⚠️ 近期錯誤"]
        for e in errors[:3]:
            error_lines.append(f"  • {e[:70]}")

    parts = [
        header,
        "\n".join(crime_lines),
        "",
        "\n".join(schedule_lines),
        "",
        "\n".join(books_lines),
        "",
        "\n".join(sys_lines),
    ]
    if error_lines:
        parts.append("")
        parts.append("\n".join(error_lines))

    return "\n".join(parts)


# ── Evening review ────────────────────────────────────────────────────────────

def build_evening_review(crime: dict, books: dict, system: dict,
                          pending: list, errors: list) -> str:
    """21:00 evening review — today's results, problems encountered, fixes applied."""
    now = datetime.now()
    weekday_zh = ["週一","週二","週三","週四","週五","週六","週日"][now.weekday()]
    header = f"🌙 [AIvideo 晚間回顧] {now.strftime('%Y-%m-%d')} {weekday_zh}\n"

    # ── Today's production results ───────────────────────────
    result_lines = ["📊 今日產出"]
    if crime["count"] > 0:
        result_lines.append(f"  Crime: {crime['count']} 支上傳")
        for dt, v in crime["recent"][:3]:
            topic = v.get("topic", "")[:40]
            vid = v.get("video_id", "")
            result_lines.append(f"  • {topic}\n    https://youtu.be/{vid}")
    else:
        result_lines.append("  Crime: ⚠️ 0 支上傳")

    if books["completed"]:
        result_lines.append(f"  Books: ✅ {len(books['output_dirs'])} 支完成")
        for d in books["output_dirs"][:2]:
            result_lines.append(f"  • {os.path.basename(d)}")
    else:
        result_lines.append("  Books: 未完成（見下方問題）")

    # ── Problems encountered ─────────────────────────────────
    problem_lines = ["🔍 今日問題"]
    if errors:
        for e in errors[:5]:
            problem_lines.append(f"  • {e[:70]}")
    else:
        problem_lines.append("  ✅ 無錯誤")

    # ── Pending work ─────────────────────────────────────────
    pending_lines = ["📋 待完成"]
    if pending:
        for p in pending:
            pending_lines.append(
                f"  • {p['dir']}: {p['done']}/~{p['est_total']}"
                f" (需 ~{p['needed']} 張)"
            )
    else:
        pending_lines.append("  ✅ 無待完成項目")

    # ── System status ────────────────────────────────────────
    quota_avail = system["imagen_limit"] - system["imagen_used"]
    sys_lines = [
        "🩺 系統狀態",
        f"  Imagen: {system['imagen_used']}/{system['imagen_limit']} 用"
        f" (剩 {quota_avail})",
        f"  磁碟: {system['free_gb']:.1f} GB free",
    ]

    # ── Tomorrow preview ─────────────────────────────────────
    tomorrow = now + timedelta(days=1)
    tw_zh = ["週一","週二","週三","週四","週五","週六","週日"][tomorrow.weekday()]
    preview_lines = [
        f"📅 明日預覽 ({tw_zh})",
        "  02:00 Crime Shorts × 2",
        "  14:00 Crime 長影片",
    ]
    if pending:
        p = pending[0]
        preview_lines.append(
            f"  15:30 Books 續跑: {p['dir']} ({p['needed']} 張)"
        )
    else:
        preview_lines.append("  15:30 Books 新影片")
    preview_lines.append("  21:00 晚間回顧")

    parts = [
        header,
        "\n".join(result_lines),
        "",
        "\n".join(problem_lines),
        "",
        "\n".join(pending_lines),
        "",
        "\n".join(sys_lines),
        "",
        "\n".join(preview_lines),
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

    # Sync latest GH Actions state before reading local files. Surface
    # failures so a stale audit doesn't silently report 0 uploads.
    git_ok, git_msg = _git_pull_quiet()
    if not git_ok:
        print(f"  [WARN] git pull failed — audit may show stale data: {git_msg}")

    crime = crime_audit(args.window_hours, args.min_count)
    books = books_today_status()
    system = system_health()
    pending = pending_renders()
    errors = recent_errors()

    # Detect morning (09:00) vs evening (21:00) mode
    current_hour = datetime.now().hour
    is_evening = current_hour >= 18

    if is_evening:
        msg = build_evening_review(crime, books, system, pending, errors)
    else:
        msg = build_summary(crime, books, system, pending, errors)

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
