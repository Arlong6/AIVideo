"""Shared LLM helper for all agents."""
import json
import os
import time
from config import GEMINI_API_KEY, ANTHROPIC_API_KEY

_gemini = None
if GEMINI_API_KEY:
    try:
        from google import genai
        _gemini = genai.Client(api_key=GEMINI_API_KEY)
    except Exception:
        pass


class ContentBlockedError(Exception):
    """Raised when LLM refuses to generate due to safety filters."""
    pass


_claude = None
try:
    import anthropic as _anthropic
    from config import ANTHROPIC_API_KEY
    if ANTHROPIC_API_KEY:
        _claude = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
except Exception:
    pass


def check_gemini_quota() -> bool:
    """Quick check if Gemini quota is available. Returns True if ready."""
    if not _gemini:
        return False
    try:
        _gemini.models.generate_content(model="gemini-2.5-flash", contents="hi")
        return True
    except Exception:
        return False


def ask(prompt: str, json_mode: bool = True) -> dict | str:
    """Call Gemini (primary), Claude (fallback). Returns dict or str."""
    if not _gemini and not _claude:
        raise RuntimeError("No LLM configured")

    config = {"response_mime_type": "application/json"} if json_mode else {}
    for model in ["gemini-2.5-flash", "gemini-2.0-flash"]:
        for attempt in range(3):
            try:
                r = _gemini.models.generate_content(
                    model=model, contents=prompt, config=config)
                if r.text is None:
                    # Safety filter triggered — content blocked
                    reason = ""
                    if hasattr(r, "candidates") and r.candidates:
                        reason = str(getattr(r.candidates[0], "finish_reason", ""))
                    if "SAFETY" in reason.upper() or attempt >= 1:
                        raise ContentBlockedError(
                            f"Content blocked by safety filter ({reason})")
                    print(f"  [WARN] Gemini {model} returned None, retrying...")
                    time.sleep(5)
                    continue
                text = r.text.strip()
                if json_mode:
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start < 0:
                        start = text.find("[")
                        end = text.rfind("]") + 1
                    return json.loads(text[start:end])
                return text
            except ContentBlockedError:
                raise  # Don't retry, propagate immediately
            except Exception as e:
                if "429" in str(e):
                    time.sleep(20)
                    continue
                if attempt == 2:
                    raise
                time.sleep(5)
    # Gemini exhausted — check if Claude fallback is allowed today
    if _claude and _check_claude_budget():
        print("  [LLM] Gemini exhausted, using Claude (今日第1支保底)")
        return ask_claude(prompt, json_mode)

    raise RuntimeError("Gemini quota exhausted. Wait for daily reset (台灣下午3-4點).")


CLAUDE_USAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "claude_daily_usage.json")


def _check_claude_budget() -> bool:
    """Allow Claude fallback only if we haven't used it for a full video today."""
    today = time.strftime("%Y-%m-%d")
    try:
        with open(CLAUDE_USAGE_FILE, "r") as f:
            usage = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        usage = {}

    calls_today = usage.get(today, 0)
    # 1 long-form video = ~8 LLM calls, cap at 10
    if calls_today >= 10:
        print(f"  [LLM] Claude daily cap reached ({calls_today} calls today)")
        return False
    return True


def _log_claude_usage():
    """Track Claude API call count per day."""
    today = time.strftime("%Y-%m-%d")
    try:
        with open(CLAUDE_USAGE_FILE, "r") as f:
            usage = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        usage = {}
    usage[today] = usage.get(today, 0) + 1
    with open(CLAUDE_USAGE_FILE, "w") as f:
        json.dump(usage, f)


def ask_claude(prompt: str, json_mode: bool = True) -> dict | str:
    """Explicitly call Claude (paid). Use when Gemini quota is exhausted."""
    if not _claude:
        raise RuntimeError("Claude not configured")

    try:
        msg = _claude.messages.create(
            model="claude-sonnet-4-6", max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        cost = (msg.usage.input_tokens * 3 + msg.usage.output_tokens * 15) / 1_000_000
        print(f"  [LLM] Claude Sonnet (${cost:.3f})")
        _log_claude_usage()
        if json_mode:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0:
                start = text.find("[")
                end = text.rfind("]") + 1
            return json.loads(text[start:end])
        return text
    except Exception as e:
        raise RuntimeError(f"Claude failed: {e}")
