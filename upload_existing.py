#!/usr/bin/env python3
"""
Upload existing finished videos to YouTube.
Usage:
  python upload_existing.py                    # upload both
  python upload_existing.py --public           # upload as public
  python upload_existing.py --dir output/xxx/  # upload single dir
"""

import argparse
import json
import os
from youtube_uploader import upload_video


VIDEOS = [
    "output/20260326_開膛手傑克",
    "output/20260326_BTK連環殺手",
]


def upload_dir(output_dir: str, privacy: str):
    video_path = os.path.join(output_dir, "final_zh.mp4")
    meta_path = os.path.join(output_dir, "metadata.json")

    if not os.path.exists(video_path):
        print(f"  [SKIP] No final_zh.mp4 in {output_dir}")
        return None

    metadata = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            metadata = data.get("zh", {})

    size_mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"\nUploading: {os.path.basename(output_dir)}")
    print(f"  Title: {metadata.get('title', '(no title)')}")
    print(f"  File:  {size_mb:.1f} MB")
    print(f"  Privacy: {privacy}")

    url = upload_video(video_path, metadata, privacy=privacy)
    return url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", action="store_true", help="Upload as public (default: private)")
    parser.add_argument("--dir", type=str, help="Upload a single output directory")
    args = parser.parse_args()

    privacy = "public" if args.public else "private"
    dirs = [args.dir] if args.dir else VIDEOS

    results = []
    for d in dirs:
        url = upload_dir(d, privacy)
        if url:
            results.append((d, url))

    print(f"\n{'='*50}")
    print(f"Upload complete: {len(results)}/{len(dirs)} videos")
    for d, url in results:
        print(f"  {os.path.basename(d)}: {url}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
