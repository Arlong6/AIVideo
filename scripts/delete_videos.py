"""
Permanently delete YouTube videos by ID.
⚠️ Irreversible — verify list before run.

Usage: python3 scripts/delete_videos.py VIDEO_ID1 VIDEO_ID2 ...
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build
from youtube_uploader import _get_credentials


def delete(video_ids: list[str]):
    creds = _get_credentials()
    if not creds:
        print("❌ Cannot authenticate")
        return 1
    yt = build("youtube", "v3", credentials=creds)
    for vid in video_ids:
        try:
            yt.videos().delete(id=vid).execute()
            print(f"  ✓ Deleted {vid}")
        except Exception as e:
            print(f"  ❌ {vid}: {e}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/delete_videos.py VIDEO_ID1 [VIDEO_ID2 ...]")
        sys.exit(1)
    sys.exit(delete(sys.argv[1:]))
