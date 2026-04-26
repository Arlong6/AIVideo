import re

MAX_CHARS_PER_CARD = 32   # max chars per subtitle card (2 lines × 16 chars)

# Paired brackets that must not be split across cards
BRACKET_PAIRS = [("『", "』"), ("「", "」"), (""", """), ("(", ")"), ("（", "）")]


def _format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _brackets_balanced(text: str) -> bool:
    for open_ch, close_ch in BRACKET_PAIRS:
        if text.count(open_ch) != text.count(close_ch):
            return False
    return True


def _find_safe_split(text: str, max_chars: int) -> int:
    for i in range(min(max_chars, len(text)) - 1, max_chars // 2, -1):
        if text[i] in "，、；" and _brackets_balanced(text[:i + 1]):
            return i + 1
    for i in range(min(max_chars, len(text)), max_chars // 2, -1):
        if _brackets_balanced(text[:i]):
            return i
    extended_limit = min(len(text), max_chars * 2)
    for i in range(max_chars + 1, extended_limit + 1):
        if _brackets_balanced(text[:i]):
            if i >= len(text) or text[i - 1] in "，、；。！？」』":
                return i
    return max_chars


def _split_to_cards(sentence: str) -> list[str]:
    sentence = sentence.strip()
    if len(sentence) <= MAX_CHARS_PER_CARD:
        return [sentence]
    cards = []
    remaining = sentence
    while len(remaining) > MAX_CHARS_PER_CARD:
        pos = _find_safe_split(remaining, MAX_CHARS_PER_CARD)
        cards.append(remaining[:pos].strip())
        remaining = remaining[pos:].strip()
    if remaining:
        cards.append(remaining)
    return [c for c in cards if c]


def generate_srt(script: str, duration_seconds: float, output_path: str):
    """
    Proportional timing fallback — used when real TTS timing is unavailable.
    """
    clean = re.sub(r"\.\.\.", "，", script.strip())
    clean = re.sub(r"\n+", "\n", clean)
    # Remove pacing tags that LLM sometimes puts in the script
    clean = re.sub(r"\[(?:slow|medium|fast|climax)\]\s*", "", clean, flags=re.IGNORECASE)
    # Strip dialogue role markers (audio handles role switching, subtitles stay neutral)
    clean = re.sub(r"\[/?ALT\]\s*", "", clean)

    sentences = re.split(r"(?<=[。！？])\s*", clean)
    sentences = [s.strip().replace("\n", " ") for s in sentences if s.strip()]
    if not sentences:
        return

    cards = []
    for sentence in sentences:
        cards.extend(_split_to_cards(sentence))
    if not cards:
        return

    weights = [len(card) for card in cards]
    total_weight = sum(weights)

    srt_entries = []
    t = 0.0
    for i, (card, w) in enumerate(zip(cards, weights)):
        card_dur = (w / total_weight) * duration_seconds
        start = t
        end = min(t + card_dur - 0.05, duration_seconds - 0.05)
        srt_entries.append(
            f"{i + 1}\n{_format_time(start)} --> {_format_time(end)}\n{card}\n"
        )
        t += card_dur

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    print(f"  Subtitles saved: {output_path} ({len(srt_entries)} cards)")


def generate_srt_from_boundaries(boundaries: list[dict], output_path: str):
    """
    Generate SRT from edge-tts SentenceBoundary events — precise audio sync.

    boundaries: list of {"offset": int, "duration": int, "text": str}
      offset/duration are in 100-nanosecond units (divide by 10_000_000 for seconds)
    """
    srt_entries = []
    idx = 1

    for b in boundaries:
        text = b["text"].strip()
        if not text:
            continue

        start_sec = b["offset"] / 10_000_000
        dur_sec = b["duration"] / 10_000_000
        end_sec = start_sec + dur_sec

        # Split long sentences into subtitle cards
        cards = _split_to_cards(text)
        n_cards = len(cards)

        # Distribute sentence duration across its cards proportionally
        card_weights = [len(c) for c in cards]
        total_w = sum(card_weights)
        card_t = start_sec

        for card, cw in zip(cards, card_weights):
            card_dur = (cw / total_w) * dur_sec
            card_end = min(card_t + card_dur - 0.05, end_sec)
            srt_entries.append(
                f"{idx}\n{_format_time(card_t)} --> {_format_time(card_end)}\n{card}\n"
            )
            card_t += card_dur
            idx += 1

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    print(f"  Subtitles saved (synced): {output_path} ({len(srt_entries)} cards)")


def generate_srt_from_case(case_json_path: str, output_path: str) -> None:
    """Build SRT from a Remotion case.json's section texts + timings.

    Scene layout matches the Remotion renderer:
      each section scene = audio_duration + breath pad
      breath pad = 1.2s for hook/setup/events/twist/aftermath, 0.5s for cta.

    Within each scene, split text into cards via _split_to_cards and
    distribute the audio-window time proportionally to card char-length.
    """
    import json as _json
    with open(case_json_path, "r", encoding="utf-8") as f:
        case = _json.load(f)

    timings = case["timings"]
    BREATH = 1.2
    CTA_BREATH = 0.5

    # (text, audio_duration, scene_pad) in playback order
    scenes = [
        (case["hook"],      timings["hook"],      BREATH),
        (case["setup"],     timings["setup"],     BREATH),
    ]
    for i, ev in enumerate(case["events"]):
        scenes.append((ev["text"], timings["events"][i], BREATH))
    scenes += [
        (case["twist"],     timings["twist"],     BREATH),
        (case["aftermath"], timings["aftermath"], BREATH),
        (case["cta"],       timings["cta"],       CTA_BREATH),
    ]

    srt_entries = []
    idx = 1
    cursor = 0.0
    for text, audio_dur, pad in scenes:
        cards = _split_to_cards(text.strip())
        if not cards:
            cursor += audio_dur + pad
            continue

        # Distribute the audio duration (NOT pad) by char-length weight.
        # Captions disappear during the breath pad — that's intentional.
        weights = [len(c) for c in cards] or [1]
        total_w = sum(weights)

        t = cursor
        for card, w in zip(cards, weights):
            card_dur = (w / total_w) * audio_dur
            start = t
            end = min(t + card_dur - 0.05, cursor + audio_dur - 0.05)
            if end <= start:
                end = start + 0.5
            srt_entries.append(
                f"{idx}\n{_format_time(start)} --> {_format_time(end)}\n{card}\n"
            )
            idx += 1
            t += card_dur

        cursor += audio_dur + pad

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_entries))
    print(f"  Subtitles saved (case-derived): {output_path} "
          f"({len(srt_entries)} cards, {cursor:.1f}s total)")
