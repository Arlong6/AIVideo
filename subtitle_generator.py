import re

MAX_CHARS_PER_CARD = 32   # max chars per subtitle card (2 lines × 16 chars)
CHAR_WEIGHT = 1.0
PAUSE_WEIGHT = 0.6        # sentence-ending punctuation (。！？)
COMMA_WEIGHT = 0.2        # mid-sentence pause (，、)

# Paired brackets that must not be split across cards
BRACKET_PAIRS = [("『", "』"), ("「", "」"), (""", """), ("(", ")"), ("（", "）")]


def _format_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _char_weight(text: str) -> float:
    w = 0.0
    for ch in text:
        w += CHAR_WEIGHT
        if ch in "。！？":
            w += PAUSE_WEIGHT
        elif ch in "，、":
            w += COMMA_WEIGHT
    return max(w, 0.1)


def _brackets_balanced(text: str) -> bool:
    """Return True if all bracket pairs in text are balanced."""
    for open_ch, close_ch in BRACKET_PAIRS:
        if text.count(open_ch) != text.count(close_ch):
            return False
    return True


def _find_safe_split(text: str, max_chars: int) -> int:
    """
    Find a split position that keeps bracket pairs balanced.
    Prefers positions ≤ max_chars at natural break points.
    If no balanced split exists within max_chars (e.g. a very long quote),
    extends beyond max_chars until the bracket closes — up to 2× max_chars.
    """
    # First pass: natural break (comma/pause) within limit with balanced brackets
    for i in range(min(max_chars, len(text)) - 1, max_chars // 2, -1):
        if text[i] in "，、；" and _brackets_balanced(text[:i + 1]):
            return i + 1

    # Second pass: any position ≤ max_chars with balanced brackets
    for i in range(min(max_chars, len(text)), max_chars // 2, -1):
        if _brackets_balanced(text[:i]):
            return i

    # Third pass: bracket pair spans beyond max_chars — extend until it closes
    # (prevents 「 on one card and 」 on another)
    extended_limit = min(len(text), max_chars * 2)
    for i in range(max_chars + 1, extended_limit + 1):
        if _brackets_balanced(text[:i]):
            # Found closing bracket — split here if at natural break, else continue
            if i >= len(text) or text[i - 1] in "，、；。！？」』":
                return i

    # Last resort: hard cut at max_chars
    return max_chars


def _split_to_cards(sentence: str) -> list[str]:
    """
    Split a sentence into subtitle cards of at most MAX_CHARS_PER_CARD chars.
    Never splits inside a 『』「」"" pair.
    """
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
    Split script into subtitle cards and generate .srt file.
    - Timing proportional to character count (matches TTS speech pace)
    - Cards ≤ MAX_CHARS_PER_CARD chars, never split inside bracket pairs
    """
    clean = re.sub(r"\.\.\.", "，", script.strip())
    clean = re.sub(r"\n+", "\n", clean)

    # Split into sentences at sentence-ending punctuation
    sentences = re.split(r"(?<=[。！？])\s*", clean)
    sentences = [s.strip().replace("\n", " ") for s in sentences if s.strip()]

    if not sentences:
        return

    # Split long sentences into short cards
    cards = []
    for sentence in sentences:
        cards.extend(_split_to_cards(sentence))

    if not cards:
        return

    # Distribute time proportionally by character weight
    weights = [_char_weight(card) for card in cards]
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
