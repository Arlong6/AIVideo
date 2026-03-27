import asyncio
import edge_tts
from config import VOICE_ZH, VOICE_EN, ELEVENLABS_API_KEY

# edge-tts settings for Chinese (dramatic true crime — TW Mandarin)
TTS_RATE_ZH = "-8%"   # slightly slower than default for gravitas
TTS_PITCH_ZH = "-5Hz" # slightly lower for dark tone


def generate_voiceover(text: str, lang: str, output_path: str):
    """
    Chinese: edge-tts (Microsoft neural voices, better Chinese intonation)
    English: ElevenLabs (more expressive, natural storytelling)
    """
    if lang == "en" and ELEVENLABS_API_KEY:
        try:
            _generate_elevenlabs(text, output_path)
            return
        except Exception as e:
            print(f"  [WARN] ElevenLabs failed ({e.__class__.__name__}), falling back to edge-tts")
    _generate_edge_tts(text, lang, output_path)


def _generate_elevenlabs(text: str, output_path: str):
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings

    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    audio = client.text_to_speech.convert(
        voice_id="cgSgspJ2msm6clMCkdW9",  # Jessica - warm storytelling
        text=text,
        model_id="eleven_multilingual_v2",
        voice_settings=VoiceSettings(
            stability=0.4,
            similarity_boost=0.8,
            style=0.5,
            use_speaker_boost=True,
        ),
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)
    print(f"  Voiceover saved (ElevenLabs EN): {output_path}")


async def _edge_tts_async(text: str, voice: str, rate: str, pitch: str, output_path: str):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def _generate_edge_tts(text: str, lang: str, output_path: str):
    if lang == "zh":
        voice, rate, pitch = VOICE_ZH, TTS_RATE_ZH, TTS_PITCH_ZH
    else:
        voice, rate, pitch = VOICE_EN, "-10%", "-2Hz"

    asyncio.run(_edge_tts_async(text, voice, rate, pitch, output_path))
    print(f"  Voiceover saved (edge-tts {lang.upper()}): {output_path}")
