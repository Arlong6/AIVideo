"""Shared LLM helper for all agents."""
import json
import time
from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

_gemini = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass


def ask(prompt: str, json_mode: bool = True) -> dict | str:
    """Call Gemini (primary) with optional JSON mode. Returns dict or str."""
    if not _gemini:
        raise RuntimeError("No LLM configured")

    config = {"response_mime_type": "application/json"} if json_mode else {}
    for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        for attempt in range(2):
            try:
                r = _gemini.models.generate_content(
                    model=model, contents=prompt, config=config)
                text = r.text.strip()
                if json_mode:
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start < 0:
                        start = text.find("[")
                        end = text.rfind("]") + 1
                    return json.loads(text[start:end])
                return text
            except Exception as e:
                if "429" in str(e):
                    time.sleep(20)
                    continue
                if attempt == 1:
                    raise
                time.sleep(5)
    raise RuntimeError("LLM call failed")
