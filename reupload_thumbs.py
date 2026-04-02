"""Upload thumbnails to already-uploaded videos."""
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

TOKEN_FILE = "youtube_token.pickle"

# video_id → thumbnail path
VIDEOS = [
    ("EKhfKTZ0nzE",  "output/20260325_泰德邦迪連環謀殺案/thumbnail.jpg"),
    ("ogk-C3jZ7Sg",  "output/20260326_開膛手傑克/thumbnail.jpg"),
    ("4_7k3WmxV0Y",  "output/20260326_BTK連環殺手/thumbnail.jpg"),
    ("FE7mPsyw0JM",  "output/20260326_Aileen_Wuornos：美國第一位/thumbnail.jpg"),
    ("zVNLRrR-koE",  "output/20260326_鄭捷台北捷運隨機殺人事件：四死二十四傷的/thumbnail.jpg"),
    ("gI5INBYo2kk",  "output/20260327_Bruce_McArthur：多倫多同志/thumbnail.jpg"),
    ("S_rrudWRB8s",  "output/20260327_Drew_Peterson：美國警察殺妻/thumbnail.jpg"),
]

with open(TOKEN_FILE, "rb") as f:
    creds = pickle.load(f)
youtube = build("youtube", "v3", credentials=creds)

for video_id, thumb_path in VIDEOS:
    if not os.path.exists(thumb_path):
        print(f"[SKIP] {video_id} — no thumbnail file")
        continue
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumb_path, mimetype="image/jpeg"),
        ).execute()
        print(f"✅ {video_id} 縮圖上傳成功")
    except Exception as e:
        print(f"❌ {video_id} 失敗: {e}")
