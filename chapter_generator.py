"""Generate YouTube chapter markers from section timing data.

Each channel uses different section label vocabularies (crime uses
「案件開場」「調查過程」「案件反思」, books uses 「震撼開場」「揭密調查」
「書中洞察」). Callers pass the appropriate section_names dict to avoid
mismatch. Default is crime's SECTION_NAMES for backward compatibility.
"""

from title_dna import SECTION_NAMES as _CRIME_SECTION_NAMES


def generate_chapters(
    section_timings: list[tuple[str, float]],
    section_names: dict | None = None,
) -> str:
    """
    Generate YouTube chapter markers text.

    section_timings: list of (section_name, start_seconds)
    section_names: dict mapping section key → display label (defaults to crime)
    Returns: chapter text for YouTube description.
    """
    labels = section_names or _CRIME_SECTION_NAMES
    lines = []
    for name, start_sec in section_timings:
        mins = int(start_sec) // 60
        secs = int(start_sec) % 60
        label = labels.get(name, name)
        lines.append(f"{mins}:{secs:02d} {label}")
    return "\n".join(lines)
