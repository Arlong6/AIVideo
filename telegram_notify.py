"""Send Telegram notification after video upload."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def notify_upload(topic: str, youtube_url: str, slot: int, publish_time: str = ""):
    """Send Telegram message after successful YouTube upload."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [INFO] Telegram not configured, skipping notification")
        return

    slot_label = {1: "10:00", 2: "14:00", 3: "18:00", 4: "22:00"}.get(slot, "10:00")
    msg = (
        f"🎬 *新影片已上傳！*\n\n"
        f"📌 題材：{topic}\n"
        f"🕐 排程播出：{publish_time or slot_label} (台灣時間)\n"
        f"📺 連結：{youtube_url}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": msg,
            "parse_mode": "Markdown",
        }, timeout=10)
        resp.raise_for_status()
        print("  ✅ Telegram notification sent")
    except Exception as e:
        print(f"  [WARN] Telegram notification failed: {e}")
