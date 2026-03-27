import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

# TTS voices — Taiwan Mandarin male for ZH (deep, dramatic, correct accent)
VOICE_ZH = "zh-TW-YunJheNeural"
VOICE_EN = "en-US-GuyNeural"

# Video settings
VIDEO_DURATION_SECONDS = 180  # 3-minute video
