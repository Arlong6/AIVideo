"""Batch re-upload existing videos to new AL_Story channel."""
import json, os, pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

OUTPUT = "output"
TOKEN_FILE = "youtube_token.pickle"

# Best version of each unique topic (newest/best title)
VIDEOS = [
    "20260325_泰德邦迪連環謀殺案",
    "20260326_開膛手傑克",
    "20260326_BTK連環殺手",
    "20260326_Aileen_Wuornos：美國第一位",
    "20260326_鄭捷台北捷運隨機殺人事件：四死二十四傷的",
    "20260327_Bruce_McArthur：多倫多同志",
    "20260327_Drew_Peterson：美國警察殺妻",
]

with open(TOKEN_FILE, "rb") as f:
    creds = pickle.load(f)

youtube = build("youtube", "v3", credentials=creds)

for folder in VIDEOS:
    video_path = os.path.join(OUTPUT, folder, "final_zh.mp4")
    meta_path  = os.path.join(OUTPUT, folder, "metadata.json")
    thumb_path = os.path.join(OUTPUT, folder, "thumbnail.jpg")

    if not os.path.exists(video_path):
        print(f"[SKIP] {folder} — no video file")
        continue

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    zh = meta if "title" in meta else meta.get("zh", {})
    title       = zh.get("title", folder)[:100]
    description = zh.get("description", "")
    hashtags    = zh.get("hashtags", ["#真實犯罪", "#Shorts"])
    tags        = [h.lstrip("#") for h in hashtags] + ["真實犯罪", "犯罪故事", "Shorts"]

    print(f"\n▶ 上傳：{title}")

    body = {
        "snippet": {
            "title": title,
            "description": description + "\n\n" + " ".join(hashtags),
            "tags": tags,
            "categoryId": "25",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  {int(status.progress()*100)}%", end="\r")

    video_id = response["id"]
    print(f"  ✅ https://youtu.be/{video_id}")

    # Upload thumbnail if exists
    if os.path.exists(thumb_path):
        try:
            from googleapiclient.http import MediaFileUpload as MFU
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MFU(thumb_path, mimetype="image/jpeg"),
            ).execute()
            print(f"  🖼 縮圖已上傳")
        except Exception as e:
            print(f"  [WARN] 縮圖失敗: {e}")

print("\n\n✅ 全部上傳完成！")
