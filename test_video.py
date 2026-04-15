#!/usr/bin/env python3
"""
Video quality checker — thin wrapper around agents/qa_agent.py.

Usage:
  python test_video.py output/20260415_books_Elizabeth_Holmes__Theranos/
  python test_video.py output/20260415_books_Elizabeth_Holmes__Theranos/final_zh.mp4
"""
import sys
import os


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_video.py <video_path_or_output_dir>")
        sys.exit(1)

    target = sys.argv[1]
    output_dir = target if os.path.isdir(target) else os.path.dirname(target)

    # Auto-detect channel from directory name
    channel = "books" if "books" in os.path.basename(output_dir).lower() else "truecrime"

    from agents.qa_agent import review_video
    report = review_video(output_dir, channel=channel)

    verdict = report.get("verdict", "REJECT")
    sys.exit(0 if verdict == "PASS" else 1)


if __name__ == "__main__":
    main()
