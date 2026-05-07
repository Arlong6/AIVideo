"""
Unlist YouTube videos by ID (set privacyStatus to "unlisted").
Reuses the same OAuth token + scope as youtube_uploader.py.

Usage:
    python3 scripts/unlist_videos.py VIDEO_ID1 VIDEO_ID2 ...
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from googleapiclient.discovery import build
from youtube_uploader import _get_credentials


def unlist(video_ids: list[str]):
    creds = _get_credentials()
    if not creds:
        print("❌ Cannot authenticate")
        return 1
    yt = build("youtube", "v3", credentials=creds)
    for vid in video_ids:
        try:
            req = yt.videos().update(
                part="status",
                body={"id": vid, "status": {"privacyStatus": "unlisted"}},
            )
            resp = req.execute()
            new = resp.get("status", {}).get("privacyStatus", "?")
            print(f"  ✓ {vid} → {new}")
        except Exception as e:
            print(f"  ❌ {vid}: {e}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/unlist_videos.py VIDEO_ID1 [VIDEO_ID2 ...]")
        sys.exit(1)
    sys.exit(unlist(sys.argv[1:]))
