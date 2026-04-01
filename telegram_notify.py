"""Telegram notifications — uploads, failures, copyright alerts."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def _send(msg: str):
    """Send a Telegram message."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as e:
        print(f"  [WARN] Telegram send failed: {e}")


def notify_upload(topic: str, youtube_url: str, slot: int, publish_time: str = ""):
    """Notify after successful YouTube upload."""
    slot_label = {1: "10:00", 2: "14:00", 3: "18:00", 4: "22:00"}.get(slot, "10:00")
    _send(
        f"🎬 *新影片已上傳！*\n\n"
        f"📌 題材：{topic}\n"
        f"🕐 排程播出：{publish_time or slot_label} (台灣時間)\n"
        f"📺 連結：{youtube_url}"
    )
    print("  ✅ Telegram notification sent")


def notify_failure(step: str, error: str, topic: str = ""):
    """Alert when video generation or upload fails."""
    _send(
        f"❌ *影片生成失敗！*\n\n"
        f"📌 題材：{topic or '未知'}\n"
        f"🔧 失敗步驟：{step}\n"
        f"💥 錯誤：`{error[:200]}`\n\n"
        f"請檢查 GitHub Actions 日誌"
    )
    print(f"  ❌ Telegram failure alert sent: {step}")


def notify_copyright(video_id: str, title: str, issue: str):
    """Alert when a video has copyright/block issues."""
    _send(
        f"⚠️ *版權警報！*\n\n"
        f"📺 影片：{title}\n"
        f"🔗 https://youtu.be/{video_id}\n"
        f"🚫 問題：{issue}\n\n"
        f"請盡快處理，避免頻道受到處罰"
    )
    print(f"  ⚠️ Copyright alert sent: {video_id}")


def notify_qa_fail(topic: str, issues: list):
    """Alert when QA Agent rejects a video."""
    issues_text = "\n".join(f"  • {i.get('check', '')}: {i.get('detail', '')}"
                            for i in issues if i.get('status') == 'FAIL')
    _send(
        f"🔎 *QA 未通過*\n\n"
        f"📌 題材：{topic}\n"
        f"❌ 問題：\n{issues_text}\n\n"
        f"影片未上傳，需要修正"
    )
