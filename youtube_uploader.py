import os
import json
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
TOKEN_FILE = "youtube_token.pickle"
SECRETS_FILE = "client_secrets.json"


def _get_credentials():
    """Get or refresh YouTube OAuth credentials."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(SECRETS_FILE):
                print(f"  [ERROR] Missing {SECRETS_FILE}")
                print("  → 請參考 README 設定 YouTube API")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return creds


def upload_video(video_path: str, metadata: dict, privacy: str = "private",
                 thumb_path: str | None = None,
                 publish_at: str | None = None) -> str | None:
    """
    Upload video to YouTube.
    privacy: 'private', 'unlisted', or 'public'
    publish_at: ISO 8601 datetime string e.g. '2026-03-28T10:00:00+08:00'
                If set, video is uploaded as private and auto-published at that time.
    Returns YouTube video URL if successful.
    """
    if not os.path.exists(video_path):
        print(f"  [ERROR] Video file not found: {video_path}")
        return None

    print("  Authenticating with YouTube...")
    creds = _get_credentials()
    if not creds:
        return None

    youtube = build("youtube", "v3", credentials=creds)

    title = metadata.get("title", "True Crime Story")
    description = metadata.get("description", "")
    hashtags = metadata.get("hashtags", [])
    tags = [h.lstrip("#") for h in hashtags] + ["真實犯罪", "犯罪故事", "懸案"]

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        # Schedule: upload as private, auto-publish at specified time
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title[:100],
            "description": description + "\n\n" + " ".join(hashtags),
            "tags": tags,
            "categoryId": "25",  # News & Politics (fits true crime)
        },
        "status": status,
    }

    print(f"  Uploading: {os.path.basename(video_path)}...")
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part=",".join(body.keys()), body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Uploading... {pct}%", end="\r")

    video_id = response["id"]
    url = f"https://youtu.be/{video_id}"
    print(f"\n  ✅ Uploaded: {url}")

    # Upload thumbnail if provided
    if thumb_path and os.path.exists(thumb_path):
        from thumbnail_generator import upload_thumbnail
        upload_thumbnail(youtube, video_id, thumb_path)

    # Upload subtitle file if exists
    srt_path = video_path.replace("final_zh.mp4", "subtitles_zh.srt")
    if os.path.exists(srt_path):
        _upload_subtitles(youtube, video_id, srt_path, lang="zh-Hant")

    return url


def _upload_subtitles(youtube, video_id: str, srt_path: str, lang: str = "zh-Hant"):
    """Upload SRT subtitle file to YouTube video."""
    try:
        print(f"  Uploading subtitles ({lang})...")
        youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": lang,
                    "name": "繁體中文",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream"),
        ).execute()
        print(f"  ✅ Subtitles uploaded")
    except Exception as e:
        print(f"  [WARN] Subtitle upload failed: {e}")
