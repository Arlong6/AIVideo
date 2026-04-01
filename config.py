import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# TTS voices — Yunjian: deep, magnetic, documentary feel
VOICE_ZH = "zh-CN-YunjianNeural"
VOICE_EN = "en-US-GuyNeural"

# Video settings — Shorts
VIDEO_DURATION_SECONDS = 180  # 3-minute video

# Video settings — Long-form
LONG_TARGET_DURATION = 1200  # ~20 min target
LONG_SCRIPT_CHARS = (3000, 5000)  # Chinese characters
LONG_SCENES_COUNT = 50  # visual scenes for footage
LONG_TARGET_W, LONG_TARGET_H = 1920, 1080  # 16:9 landscape
