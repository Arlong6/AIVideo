"""Generate YouTube chapter markers from section timing data."""

from title_dna import SECTION_NAMES


def generate_chapters(section_timings: list[tuple[str, float]]) -> str:
    """
    Generate YouTube chapter markers text.

    section_timings: list of (section_name, start_seconds)
    Returns: chapter text for YouTube description.
    """
    lines = []
    for name, start_sec in section_timings:
        mins = int(start_sec) // 60
        secs = int(start_sec) % 60
        label = SECTION_NAMES.get(name, name)
        lines.append(f"{mins}:{secs:02d} {label}")
    return "\n".join(lines)
