"""
Multi-channel configuration.

Defines each YouTube channel's content personality, data paths, and upload
settings. The daily pipeline dispatches behavior based on the selected
channel so the shared engine (TTS, video assembly, upload) stays one copy
while content generation forks.

To add a new channel:
  1. Add an entry to CHANNELS below
  2. Create the matching script/title_dna/topic_manager modules
  3. Run reauth.py for that channel's YouTube account, save token to
     the path listed in `token_file`
  4. Pass --channel <name> to generate.py

Design principle: no channel field = behave exactly like single-channel
truecrime did. All new code paths default to "truecrime" to keep existing
callers working.
"""
from __future__ import annotations

DEFAULT_CHANNEL = "truecrime"

CHANNELS = {
    "truecrime": {
        "display_name": "真實犯罪頻道",
        # Current single-channel layout — nothing moves in Phase 1.
        "data_dir": ".",
        "token_file": "youtube_token.pickle",
        # Modules that own content generation for this channel.
        "script_module": "script_generator",
        "title_dna_module": "title_dna",
        "topic_module": "topic_manager",
        # Creative direction.
        "tone": "dramatic, investigative, suspenseful",
        "topic_axis": "fear",   # fear / aspiration / mixed (per Razvan P1)
        "hashtags_short": ["#真實犯罪", "#犯罪故事", "#懸案", "#Shorts", "#台灣"],
        "hashtags_long": ["#真實犯罪", "#犯罪紀實", "#懸案", "#深度解析", "#台灣"],
        # State file names (within data_dir).
        "video_log": "video_log.json",
        "used_topics": "used_topics.json",
        "topics_bank": "topics.json",
        "today_topics": "today_topics.json",
        "pexels_seen_ids": "pexels_seen_ids.json",
    },

    # Phase 3 will fill this in. Stub declared now so channel_config has a
    # complete map and code can detect "not yet wired" at startup instead
    # of crashing deep inside a loop.
    "books": {
        "display_name": "說書頻道（故事化）",
        "data_dir": "data/books",
        "token_file": "data/books/youtube_token.pickle",
        "script_module": "script_generator_books",     # TODO: Phase 3
        "title_dna_module": "title_dna_books",         # TODO: Phase 3 (after competitor DNA extraction)
        "topic_module": "topic_manager_books",         # TODO: Phase 3
        "tone": "narrative-driven, dramatic, revelation-focused",
        "topic_axis": "mixed",  # fear (e.g. tragic biographies) + aspiration (e.g. life-changing insight)
        "hashtags_short": ["#說書", "#書中故事", "#歷史故事", "#Shorts", "#台灣"],
        "hashtags_long": ["#說書", "#歷史故事", "#人物傳記", "#深度解析", "#台灣"],
        "video_log": "video_log.json",
        "used_topics": "used_topics.json",
        "topics_bank": "topics.json",
        "today_topics": "today_topics.json",
        "pexels_seen_ids": "pexels_seen_ids.json",
        # Marker so orchestrators can skip this channel until its content
        # modules are ready.
        "enabled": False,
    },
}


def get(channel: str = DEFAULT_CHANNEL) -> dict:
    """Return the config dict for a channel. Defaults to truecrime so
    existing single-channel callers (no explicit channel arg) keep working."""
    if channel not in CHANNELS:
        raise ValueError(
            f"Unknown channel: {channel!r}. "
            f"Known channels: {', '.join(CHANNELS.keys())}"
        )
    return CHANNELS[channel]


def data_path(channel: str, filename_key: str) -> str:
    """Resolve a state-file path for a given channel.

    filename_key is a key into the channel config (e.g. 'video_log'), NOT
    a bare filename — this keeps file naming under config control.
    """
    import os
    cfg = get(channel)
    fname = cfg.get(filename_key)
    if not fname:
        raise KeyError(f"Channel {channel!r} has no {filename_key!r} entry")
    data_dir = cfg.get("data_dir", ".")
    return os.path.join(data_dir, fname) if data_dir != "." else fname


def enabled_channels() -> list[str]:
    """List channels that are ready for production runs."""
    return [
        name for name, cfg in CHANNELS.items()
        if cfg.get("enabled", True)  # default True unless explicitly disabled
    ]
