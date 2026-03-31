"""
Visual Agent — footage sourcing and content-matching.

Responsibilities:
- Search Wikimedia for real case photos (primary visual)
- Search Pexels for atmospheric transition footage (secondary)
- Generate info cards per Design Agent's direction
- Ensure footage matches the script content
- Minimize repetition
"""
import os


def source_visuals(case_data: dict, script_data: dict,
                   visual_plan: dict, output_dir: str) -> dict:
    """
    Source all visual materials based on Design Agent's plan.
    Returns paths to all generated/downloaded materials.
    """
    print("  [Visual] Sourcing materials...")

    results = {
        "wiki_clips": [],
        "pexels_clips_dir": "",
        "info_cards": {},
    }

    # 1. Wikimedia real photos — use design plan's queries + case data keywords
    wiki_queries = []
    for section in visual_plan.get("sections", []):
        wiki_queries.extend(section.get("wiki_search_queries", []))
    # Add case data keywords
    wiki_queries.extend(case_data.get("search_keywords_en", []))
    wiki_queries.extend(case_data.get("search_keywords_zh", []))

    # Deduplicate
    seen = set()
    unique_queries = []
    for q in wiki_queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique_queries.append(q)

    print(f"  [Visual] Wikimedia: {len(unique_queries)} search queries")
    from wiki_footage import get_wiki_clips
    results["wiki_clips"] = get_wiki_clips(
        " ".join(unique_queries[:5]),  # main topic for search
        output_dir, max_images=25
    )

    # 2. Pexels atmospheric footage — use design plan's queries
    pexels_queries = []
    for section in visual_plan.get("sections", []):
        pexels_queries.extend(section.get("pexels_queries", []))

    # Also add script's visual_scenes
    pexels_queries.extend(script_data.get("visual_scenes", []))

    # Deduplicate
    seen = set()
    unique_pexels = []
    for q in pexels_queries:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique_pexels.append(q)

    print(f"  [Visual] Pexels: {len(unique_pexels)} search queries")
    from footage_downloader import download_footage
    download_footage(unique_pexels[:50], output_dir, fmt="long")
    results["pexels_clips_dir"] = os.path.join(output_dir, "clips")

    # 3. Info cards — based on design plan
    print("  [Visual] Generating info cards...")
    from info_cards import generate_info_cards
    results["info_cards"] = generate_info_cards(script_data, output_dir)

    wiki_count = len(results["wiki_clips"])
    pexels_count = len(os.listdir(results["pexels_clips_dir"])) if os.path.exists(results["pexels_clips_dir"]) else 0
    card_count = len(results["info_cards"])
    print(f"  [Visual] Complete: {wiki_count} wiki, {pexels_count} Pexels, {card_count} info cards")

    return results
