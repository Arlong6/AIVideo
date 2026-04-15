import os
import json
import pickle
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

def _sanitize_description(text: str) -> str:
    """Clean description for YouTube API compliance.

    YouTube rejects descriptions that contain HTML-like tags (<...>), exceed
    5000 chars, or have certain special Unicode. Observed 2026-04-11 when a
    long-form crime video's Gemini-generated description caused a 400
    'invalidDescription' error from the YouTube API.
    """
    import re
    # Strip HTML-like angle bracket content (Gemini sometimes outputs <tags>)
    text = re.sub(r"<[^>]{1,50}>", "", text)
    # Strip zero-width chars and other invisible Unicode
    text = re.sub(r"[\u200b-\u200f\u2028-\u202f\ufeff]", "", text)
    # Collapse excessive newlines
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    # YouTube max description = 5000 chars
    if len(text) > 4900:
        text = text[:4900] + "\n\n(... 更多資訊請見留言區)"
    return text


def _build_full_description(desc: str, hashtags: list, metadata: dict,
                            video_path: str) -> str:
    """Build YouTube description with proper attribution and disclosures."""
    parts = [desc]

    # Ending discussion question
    ending_q = metadata.get("ending_question", "")
    if ending_q:
        parts.append(f"💬 {ending_q}")

    # Chapter markers (if included in metadata)
    chapters = metadata.get("chapters_text", "")
    if chapters:
        parts.append(f"\n📑 章節\n{chapters}")

    # Hashtags
    if hashtags:
        parts.append(" ".join(hashtags))

    # Wikimedia attribution (from sources.txt next to video)
    if video_path:
        sources_path = os.path.join(os.path.dirname(video_path), "sources.txt")
        if os.path.exists(sources_path):
            with open(sources_path, "r", encoding="utf-8") as f:
                parts.append(f.read().strip())

    # Standard attribution block
    parts.append("""━━━━━━━━━━━━━━━━━
📸 影片素材：Pexels (https://www.pexels.com) — 免費授權素材
🎤 語音：AI 文字轉語音技術生成
📝 腳本：基於公開新聞報導及司法紀錄，AI 輔助撰寫

⚠️ 免責聲明：本影片內容基於公開新聞報導、司法紀錄及書籍整理，
僅供教育及資訊分享用途，不代表對任何當事人之定論。
部分細節可能因資料來源不同而有出入，如有錯誤歡迎留言指正。
━━━━━━━━━━━━━━━━━""")

    result = "\n\n".join(parts)
    return _sanitize_description(result)


def _ensure_youtube_compatible(video_path: str) -> str:
    """
    Re-encode video to guaranteed YouTube-compatible format.
    Fixes stuck processing caused by incompatible codecs/containers.
    """
    import subprocess

    # Check codec, pixel format, and FPS
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries",
         "stream=codec_name,pix_fmt,r_frame_rate", "-of", "csv=p=0", video_path],
        capture_output=True, text=True)
    info = result.stdout.strip()

    # Check FPS — must be standard (24, 25, 30, 60)
    needs_reencode = False
    try:
        for line in info.split("\n"):
            parts = line.split(",")
            if len(parts) >= 3 and "/" in parts[2]:
                num, den = parts[2].split("/")
                fps = int(num) / int(den) if int(den) > 0 else 0
                if fps not in (24, 25, 30, 60) and fps < 23:
                    print(f"  Non-standard FPS detected: {fps:.1f}")
                    needs_reencode = True
    except:
        pass

    if not needs_reencode and "h264" in info and "yuv420p" in info:
        return video_path

    print("  Re-encoding for YouTube compatibility...")
    safe_path = video_path.replace(".mp4", "_yt.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        safe_path,
    ], capture_output=True, timeout=1200)

    if os.path.exists(safe_path) and os.path.getsize(safe_path) > 1000:
        print(f"  Re-encoded: {os.path.getsize(safe_path)/1024/1024:.0f} MB")
        return safe_path
    return video_path


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
    tags = [h.lstrip("#") for h in hashtags] + ["真實犯罪", "犯罪故事", "懸案", "Shorts", "shorts"]

    # Build full YouTube description with attribution and disclosures
    full_desc = _build_full_description(description, hashtags, metadata, video_path)

    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title[:100],
            "description": full_desc,
            "tags": tags,
            "categoryId": "25",  # News & Politics (fits true crime)
        },
        "status": status,
    }

    # Force re-encode to YouTube-safe format before upload
    video_path = _ensure_youtube_compatible(video_path)

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

    # Upload SRT subtitle file
    srt_path = video_path.replace("final_zh.mp4", "subtitles_zh.srt")
    if os.path.exists(srt_path):
        _upload_subtitles(youtube, video_id, srt_path, lang="zh-Hant")

    # Post pinned comment if provided
    pinned = metadata.get("pinned_comment", "")
    if pinned:
        _post_pinned_comment(youtube, video_id, pinned)

    return url


def _post_pinned_comment(youtube, video_id: str, text: str):
    """Post a comment and pin it to the top of the video."""
    try:
        print(f"  Posting pinned comment...")
        resp = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {"textOriginal": text}
                    },
                }
            },
        ).execute()
        comment_id = resp["snippet"]["topLevelComment"]["id"]
        # Pin it — requires setting as moderation held then approving
        # Actually, YouTube API doesn't have a direct "pin" endpoint.
        # But the channel owner's first comment appears prominently.
        # We'll just post it — manual pin if needed.
        print(f"  ✅ Comment posted (pin manually in Studio if needed)")
    except Exception as e:
        print(f"  [WARN] Comment post failed: {e}")


def _upload_transcript_autosync(youtube, video_id: str, script_path: str,
                                lang: str = "zh-Hant"):
    """Upload plain text transcript — YouTube auto-syncs timing with audio."""
    try:
        print(f"  Uploading transcript for auto-sync ({lang})...")
        youtube.captions().insert(
            part="snippet",
            sync=True,  # Let YouTube auto-sync
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": lang,
                    "name": "繁體中文",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(script_path, mimetype="text/plain"),
        ).execute()
        print(f"  ✅ Transcript uploaded — YouTube will auto-sync subtitles")
    except Exception as e:
        print(f"  [WARN] Transcript auto-sync upload failed: {e}")
        # Fallback: try SRT
        srt_path = script_path.replace("script_zh.txt", "subtitles_zh.srt")
        if os.path.exists(srt_path):
            _upload_subtitles(youtube, video_id, srt_path, lang=lang)


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
