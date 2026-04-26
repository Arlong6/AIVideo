"""Rank Shorts by views for long-form upgrade queue.

Phase 1 (bootstrap): Manual override picks the top N by views.
Phase 4 (auto): Scheduled job will detect when a Short crosses 500 views
and notify Telegram for user approval.

Usage:
  python shorts_to_longform_queue.py --top 5          # show top 5
  python shorts_to_longform_queue.py --top 5 --queue  # also write longform_queue.json
  python shorts_to_longform_queue.py --threshold 500  # show only Shorts ≥500 views
"""
import argparse
import json
import os
import pickle
import re
from datetime import datetime, timezone

from googleapiclient.discovery import build


QUEUE_PATH = "longform_queue.json"


def _topic_key(topic: str) -> str:
    """Strip subtitles + descriptors so '陳金火案：駭人聽聞...' matches '陳金火案'."""
    if not topic:
        return ""
    # Drop everything after first separator
    core = re.split(r"[：:｜|（(\-—–]", topic, maxsplit=1)[0].strip()
    return core


def _existing_long_topics(videos: list[dict]) -> set[str]:
    """Return normalized topic keys that already have a long-form video."""
    out = set()
    for v in videos:
        if v.get("duration_s", 0) > 120:
            out.add(_topic_key(v.get("topic", "")))
    return out


def scan(top_n: int | None = None,
         threshold: int | None = None,
         write_queue: bool = False) -> list[dict]:
    """Return ranked list of Shorts eligible for long-form upgrade."""
    log = json.load(open("video_log.json"))
    videos = log.get("videos", [])
    if not videos:
        print("No videos in log.")
        return []

    # Fetch fresh view counts
    with open("youtube_token.pickle", "rb") as f:
        creds = pickle.load(f)
    yt = build("youtube", "v3", credentials=creds)

    shorts = [v for v in videos if 0 < v.get("duration_s", 0) <= 120]
    short_ids = [v["video_id"] for v in shorts]

    fresh_stats = {}
    for i in range(0, len(short_ids), 50):
        chunk = short_ids[i:i + 50]
        r = yt.videos().list(
            part="statistics,snippet",
            id=",".join(chunk),
        ).execute()
        for item in r.get("items", []):
            fresh_stats[item["id"]] = {
                "views": int(item["statistics"].get("viewCount", 0)),
                "title": item["snippet"]["title"],
                "published_at": item["snippet"]["publishedAt"],
            }

    long_topics = _existing_long_topics(videos)

    enriched = []
    for v in shorts:
        vid = v["video_id"]
        s = fresh_stats.get(vid, {})
        topic = v.get("topic", "")
        topic_key = _topic_key(topic)
        enriched.append({
            "video_id": vid,
            "topic": topic,
            "topic_key": topic_key,
            "title": s.get("title", ""),
            "views": s.get("views", 0),
            "published_at": s.get("published_at", ""),
            "uploaded_at": v.get("uploaded_at", ""),
            "has_longform": topic_key in long_topics,
        })

    # Sort by views desc
    enriched.sort(key=lambda x: -x["views"])

    # Filter
    eligible = [e for e in enriched if not e["has_longform"]]
    if threshold is not None:
        eligible = [e for e in eligible if e["views"] >= threshold]
    if top_n is not None:
        eligible = eligible[:top_n]

    if write_queue:
        out = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "threshold": threshold,
            "top_n": top_n,
            "queue": eligible,
        }
        json.dump(out, open(QUEUE_PATH, "w"), ensure_ascii=False, indent=2)
        print(f"\n→ Wrote queue: {QUEUE_PATH}")

    return eligible


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--top", type=int, default=None,
                   help="Show top N Shorts (manual bootstrap mode)")
    p.add_argument("--threshold", type=int, default=None,
                   help="Filter Shorts with views >= threshold (auto-trigger mode)")
    p.add_argument("--queue", action="store_true",
                   help="Write longform_queue.json")
    args = p.parse_args()

    if args.top is None and args.threshold is None:
        args.top = 10  # default

    results = scan(top_n=args.top, threshold=args.threshold,
                   write_queue=args.queue)

    if not results:
        print("No eligible Shorts found.")
        return

    print(f"\n{'#':>3}  {'Views':>5}  {'Topic':<50}  {'Has long':<8}")
    print("-" * 80)
    for i, e in enumerate(results, 1):
        topic = e["topic"][:48]
        print(f"{i:>3}  {e['views']:>5}  {topic:<50}  {'yes' if e['has_longform'] else '—':<8}")


if __name__ == "__main__":
    main()
