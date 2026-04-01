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
