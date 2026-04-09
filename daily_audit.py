#!/usr/bin/env python3
"""
Post-run audit: verify that the 02:00 launchd run actually produced and
uploaded videos in the last 24 hours.

Pre-flight health_check.py catches environment regressions.
This catches silent pipeline failures that slip past the smoke tests —
e.g. the code imports fine but generate.py crashes mid-run for a new
reason, or uploads succeed but something else silently fails.

Usage:
  python daily_audit.py                 # exit 0 if >=1 upload in last 24h
  python daily_audit.py --min-count 2   # expect at least 2 uploads
  python daily_audit.py --verbose
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_LOG = os.path.join(PROJECT_DIR, "video_log.json")


def load_videos():
    if not os.path.exists(VIDEO_LOG):
        return []
    with open(VIDEO_LOG, "r", encoding="utf-8") as f:
        return json.load(f).get("videos", [])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-count", type=int, default=2,
                        help="Minimum uploads expected in the audit window "
                             "(default 2 — slot 1 + slot 2; a single slot "
                             "failing should trigger Telegram alert)")
    parser.add_argument("--window-hours", type=int, default=24,
                        help="Audit window in hours")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-alert", action="store_true")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=args.window_hours)

    videos = load_videos()
    recent = []
    for v in videos:
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

    if args.verbose:
        print(f"=== AIvideo daily audit — window {args.window_hours}h ===")
        print(f"Cutoff: {cutoff.isoformat()}")
        print(f"Recent uploads: {len(recent)}")
        for dt, v in recent:
            print(f"  • {dt.isoformat()} — {v.get('topic', '')[:60]} ({v.get('video_id', '')})")

    if len(recent) < args.min_count:
        msg = (f"Only {len(recent)} video(s) uploaded in last {args.window_hours}h "
               f"(expected >={args.min_count}). "
               f"Check logs/daily_{now.strftime('%Y%m%d')}_run*.log")
        print(f"FAIL: {msg}", file=sys.stderr)
        if not args.no_alert:
            try:
                from telegram_notify import notify_failure
                notify_failure("daily_audit", msg, topic="pipeline audit")
            except Exception as e:
                print(f"  (could not send telegram alert: {e})", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"\nOK: {len(recent)} uploads in window")
    sys.exit(0)


if __name__ == "__main__":
    main()
