"""
B — ElevenLabs Mandarin voice swap pre-flight.

Generates ~30s samples in 3 candidate voices using a real crime-documentary
opening. arlong listens, picks one, then we wire that voice_id into
tts_generator behind a TTS_PROVIDER=elevenlabs env flag.

3 candidates chosen for sober Mandarin documentary tone:
- Daniel (onwK4e9ZLuTAKqWW03F9) — British, "Steady Broadcaster", formal
- George (JBFqnCBsd6RMA3yfX1lzcgu) — British, "Warm Storyteller", mature
- Bill   (pqHfZKP75CvOlQylNhV4)   — American, "Wise Mature", old, crisp

Cost: ~450 chars × 1 char/credit = ~0.45 credit cost. Well inside the
free 10k chars/month tier.

Output:
    data/elevenlabs_voice_test/voice_{name}.mp3
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "data" / "elevenlabs_voice_test"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 約 30s 旁白用的真實犯罪 documentary 開場（Mandarin）
# 取自典型「沉穩 narrator」風格,內容偏白描不灑狗血,測得出 voice 的低音
# 質感與停頓自然度.
SAMPLE_TEXT = (
    "一九九六年五月,一場槍響打破了台中夜晚的寧靜。"
    "茶館內三人倒下,兇手悄然離去,沒有留下指紋,也沒有目擊者願意開口。"
    "二十多年過去,警方手上的線索依然支離破碎。"
    "今天,我們要回到那個雨夜,重新檢視一個被時間幾乎掩蓋的案件。"
)

CANDIDATES = [
    ("daniel_british_broadcaster", "onwK4e9ZLuTAKqWW03F9"),
    ("george_british_storyteller", "JBFqnCBsd6RMkjVDRZzb"),
    ("bill_american_mature",       "pqHfZKP75CvOlQylNhV4"),
]


def main():
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        print("[ERROR] ELEVENLABS_API_KEY not set"); return 1

    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    client = ElevenLabs(api_key=api_key)

    # Settings tuned for sober documentary (low style = less drama, low
    # stability = monotone, high similarity = preserve original tone)
    settings = VoiceSettings(
        stability=0.55,        # higher = more monotone, less expressive
        similarity_boost=0.85,
        style=0.15,            # low = sober, not theatrical
        use_speaker_boost=True,
    )

    print(f"Sample text: {len(SAMPLE_TEXT)} chars × {len(CANDIDATES)} voices "
          f"= ~{len(SAMPLE_TEXT) * len(CANDIDATES)} credits total")
    print()

    for name, voice_id in CANDIDATES:
        out_path = OUT_DIR / f"voice_{name}.mp3"
        print(f"[gen] {name} ({voice_id[:12]}...)")
        try:
            audio = client.text_to_speech.convert(
                voice_id=voice_id,
                text=SAMPLE_TEXT,
                model_id="eleven_multilingual_v2",
                voice_settings=settings,
            )
            with open(out_path, "wb") as f:
                for chunk in audio:
                    if chunk:
                        f.write(chunk)
            sz_kb = out_path.stat().st_size // 1024
            print(f"  ✅ {out_path.name} ({sz_kb} KB)")
        except Exception as e:
            print(f"  ❌ {e}")

    print()
    print("=== Compare ===")
    for name, _ in CANDIDATES:
        print(f"  open '{OUT_DIR / f'voice_{name}.mp3'}'")
    print()
    print("Also worth comparing against the current Edge TTS baseline:")
    print(f"  open '{ROOT / 'voice_test' / 'voice_3_Yunjian.mp3'}'  (if it exists)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
