"""Telegram notifications for AIvideo.

2026-04-09: User has only one Telegram chat for this project. The shared
`telegram_hub` package may route AIVIDEO tag to a different chat than the
one in .env, so we explicitly DISABLE the hub path here. All notifications
flow through `_send_raw()` to TELEGRAM_CHAT_ID. See
memory/feedback_telegram_single_chat.md for context.
"""
import os

# Hub path explicitly disabled — see module docstring.
_hub = None

# Load chat token from .env
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def _send_raw(msg: str):
    """Fallback send if hub not available."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import requests
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception:
        pass


def notify_upload(topic: str, youtube_url: str, slot: int, publish_time: str = ""):
    """Notify after successful YouTube upload."""
    slot_label = {1: "10:00", 2: "14:00", 3: "18:00", 4: "22:00"}.get(slot, "10:00")
    if _hub:
        _hub.send(Tag.AIVIDEO, "新影片已上傳", fields={
            "題材": topic,
            "排程播出": f"{publish_time or slot_label} (台灣時間)",
            "連結": youtube_url,
        })
    else:
        _send_raw(f"🎬 [AIvideo] 新影片：{topic}\n{youtube_url}")
    print("  ✅ Telegram notification sent")


def notify_failure(step: str, error: str, topic: str = ""):
    """Alert when video generation or upload fails."""
    if _hub:
        _hub.alert(Tag.AIVIDEO, "影片生成失敗", error=error, fields={
            "題材": topic or "未知",
            "失敗步驟": step,
        })
    else:
        _send_raw(f"❌ [AIvideo] 失敗：{step}\n{error[:200]}")
    print(f"  ❌ Telegram failure alert sent: {step}")


def notify_copyright(video_id: str, title: str, issue: str):
    """Alert when a video has copyright/block issues."""
    if _hub:
        _hub.alert(Tag.AIVIDEO, "版權警報", fields={
            "影片": title,
            "連結": f"https://youtu.be/{video_id}",
            "問題": issue,
        })
    else:
        _send_raw(f"⚠️ [AIvideo] 版權：{title}\n{issue}")
    print(f"  ⚠️ Copyright alert sent: {video_id}")


def notify_qa_fail(topic: str, issues: list):
    """Alert when QA Agent rejects a video."""
    issues_text = "\n".join(f"  • {i.get('check', '')}: {i.get('detail', '')}"
                            for i in issues if i.get('status') == 'FAIL')
    if _hub:
        _hub.alert(Tag.AIVIDEO, "QA 未通過", fields={"題材": topic}, error=issues_text)
    else:
        _send_raw(f"🔎 [AIvideo] QA 未通過：{topic}\n{issues_text}")
