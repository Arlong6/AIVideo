#!/usr/bin/env python3
"""
One-off scan for the three books-channel competitors. Produces
`books_channel_analysis.json` which Phase 3 will feed to Opus for
DNA pattern extraction (the equivalent of title_dna.py for crime).

Reuses trend_engine.scan_competitor_channels by temporarily injecting
the book channels into its name-lookup map.

Usage:
    python scan_book_channels.py
"""
import json
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/opt/homebrew/bin/ffmpeg")

import trend_engine

# Three target channels (with metadata for context).
BOOK_CHANNELS = {
    "文森說書": {
        "channel_id": "UCPgGtH2PxZ9xR0ehzQ27FHw",
        "handle": "@vincent_reading",
        "subscribers": 947_000,
        "role": "primary",  # biggest pure booktuber, DNA source
    },
    "英雄說書": {
        "channel_id": "UCIpRQFB5af6be62BpQyWbuA",
        "handle": "@Herostory",
        "subscribers": 340_000,
        "role": "route_b_exemplar",  # narrative history, closest to Route B
    },
    "啾啾鞋": {
        "channel_id": "UCIF_gt4BfsWyM_2GOcKXyEQ",
        "handle": "@chuchushoeTW",
        "subscribers": 1_600_000,
        "role": "scale_reference",  # biggest, mixed content — filter 啾讀 in post
    },
}


def main():
    # Inject channel names into trend_engine's name map so logs show the
    # handle-friendly name instead of raw UC... IDs.
    for name, meta in BOOK_CHANNELS.items():
        trend_engine.DEFAULT_COMPETITOR_CHANNELS[name] = meta["channel_id"]

    channel_ids = [meta["channel_id"] for meta in BOOK_CHANNELS.values()]

    print("=== Scanning book-channel competitors ===")
    for name, meta in BOOK_CHANNELS.items():
        print(f"  • {name} ({meta['handle']}) — {meta['subscribers']:,} subs — role={meta['role']}")
    print()

    result = trend_engine.scan_competitor_channels(channel_ids=channel_ids)

    # Enrich with our metadata
    for name, meta in BOOK_CHANNELS.items():
        if name in result["channels"]:
            result["channels"][name].update({
                "channel_id": meta["channel_id"],
                "handle": meta["handle"],
                "subscribers": meta["subscribers"],
                "role": meta["role"],
            })

    # Save output
    out_path = "books_channel_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n=== Scan complete ===")
    print(f"Total channels scanned: {len(result['channels'])}")
    print(f"Total outliers found: {len(result['all_outliers'])}")
    print(f"Saved to: {out_path}")

    # Print top 10 outliers as a quick sanity check
    print("\n=== Top 10 outliers by views ===")
    for i, o in enumerate(result["all_outliers"][:10], 1):
        ch = o.get("channel", "?")
        title = o.get("title", "?")
        views = o.get("views", 0)
        print(f"  {i:2d}. [{ch}] {title[:60]} — {views:,} views")


if __name__ == "__main__":
    main()
