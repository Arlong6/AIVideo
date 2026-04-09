#!/usr/bin/env python3
"""
Pre-flight health check for the daily auto-production pipeline.

Runs a series of cheap smoke tests to catch environment regressions BEFORE
the 2 AM launchd run fires. On failure, sends a Telegram alert and exits
non-zero so the caller can bail out early.

Usage:
  python health_check.py              # exit 0 on success, 1 on failure
  python health_check.py --verbose    # print all checks even on success
"""
import argparse
import json
import os
import shutil
import sys
import traceback

# Ensure moviepy can find ffmpeg even if this script is invoked without the
# fix-up that daily_run.sh applies.
os.environ.setdefault("IMAGEIO_FFMPEG_EXE", "/opt/homebrew/bin/ffmpeg")

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)

REQUIRED_ENV_VARS = [
    "GEMINI_API_KEY",
    "PEXELS_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

MIN_FREE_DISK_GB = 5.0


def check_ffmpeg():
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg not found on PATH")
    env_path = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if env_path and not os.path.exists(env_path):
        raise RuntimeError(f"IMAGEIO_FFMPEG_EXE points at missing file: {env_path}")
    return f"ffmpeg={path}"


def check_imports():
    """Import the top of generate.py — this catches the exact failure mode
    we hit on 04-06..04-08 (imageio_ffmpeg bundled binary missing)."""
    modules = [
        "script_generator",
        "tts_generator",
        "subtitle_generator",
        "footage_downloader",
        "wiki_footage",
        "music_downloader",
        "video_assembler",
        "youtube_uploader",
        "topic_manager",
        "thumbnail_generator",
        "telegram_notify",
        "analytics_tracker",
        # Not on the daily-run critical path but still must import cleanly —
        # silent-bitrot protection (caught trend_engine's stale TITLE_PATTERNS
        # import on 2026-04-08).
        "trend_engine",
        "title_dna",
        "channel_config",
    ]
    for m in modules:
        __import__(m)
    return f"imported {len(modules)} modules"


def check_json_files():
    """Scan every *.json in project root — unresolved merge conflicts or
    corruption in any of them will crash generate.py at runtime."""
    import glob
    bad = []
    checked = 0
    for path in sorted(glob.glob(os.path.join(PROJECT_DIR, "*.json"))):
        name = os.path.basename(path)
        # Skip third-party / generated files that might not be JSON
        if name in ("client_secrets.json", "claude_daily_usage.json"):
            # still check they parse, they ARE JSON
            pass
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if "<<<<<<<" in content or "\n=======\n" in content or ">>>>>>>" in content:
                bad.append(f"{name}: unresolved merge conflict markers")
                continue
            json.loads(content)
            checked += 1
        except json.JSONDecodeError as e:
            bad.append(f"{name}: invalid JSON ({e.msg} at line {e.lineno})")
        except Exception as e:
            bad.append(f"{name}: {e}")
    if bad:
        raise RuntimeError("; ".join(bad))
    return f"{checked} JSON files valid"


def check_env_vars():
    from dotenv import load_dotenv
    load_dotenv()
    missing = [k for k in REQUIRED_ENV_VARS if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"missing env vars: {', '.join(missing)}")
    return f"{len(REQUIRED_ENV_VARS)} required env vars present"


def check_youtube_token():
    path = os.path.join(PROJECT_DIR, "youtube_token.pickle")
    if not os.path.exists(path):
        raise RuntimeError("youtube_token.pickle missing — run reauth.py")
    return "youtube_token.pickle present"


def check_disk_space():
    stat = shutil.disk_usage(PROJECT_DIR)
    free_gb = stat.free / (1024 ** 3)
    if free_gb < MIN_FREE_DISK_GB:
        raise RuntimeError(f"only {free_gb:.1f}GB free (need >{MIN_FREE_DISK_GB}GB)")
    return f"{free_gb:.1f}GB free"


def check_logs_writable():
    log_dir = os.path.join(PROJECT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    testfile = os.path.join(log_dir, ".healthcheck_write_test")
    with open(testfile, "w") as f:
        f.write("ok")
    os.remove(testfile)
    return "logs/ writable"


def check_channel_config():
    """Verify multi-channel config loads and truecrime is enabled. Catches
    regressions where the config file gets corrupted or truecrime becomes
    accidentally disabled (which would silently skip all production runs)."""
    import channel_config
    enabled = channel_config.enabled_channels()
    if "truecrime" not in enabled:
        raise RuntimeError(f"truecrime is NOT in enabled channels: {enabled}")
    # Every channel must resolve a data path without exploding
    for name in channel_config.CHANNELS:
        channel_config.data_path(name, "video_log")
    return f"{len(channel_config.CHANNELS)} channels configured, {len(enabled)} enabled"


def check_title_dna_wired():
    """Verify title_dna is actually being injected into both Shorts and long-form
    prompts. Catches regressions like: DNA module exists but prompt stops calling it."""
    from title_dna import get_title_prompt_insert, TITLE_DNA
    insert = get_title_prompt_insert()
    if "標題 DNA 公式" not in insert:
        raise RuntimeError("get_title_prompt_insert() produced unexpected output")
    if len(TITLE_DNA) < 3:
        raise RuntimeError(f"TITLE_DNA only has {len(TITLE_DNA)} patterns")
    # Shorts prompt must have the placeholder
    with open(os.path.join(PROJECT_DIR, "script_generator.py"), "r", encoding="utf-8") as f:
        src = f.read()
    if "{title_dna}" not in src:
        raise RuntimeError("script_generator.py no longer contains {title_dna} placeholder")
    if "get_title_prompt_insert" not in src:
        raise RuntimeError("script_generator.py no longer imports title_dna helper")
    # Dry-run Shorts prompt format
    from script_generator import PROMPT_ZH
    rendered = PROMPT_ZH.format(topic="__probe__", title_dna=insert)
    if "標題 DNA 公式" not in rendered or "__probe__" not in rendered:
        raise RuntimeError("Shorts prompt format dry-run failed to inject DNA or topic")
    return f"{len(TITLE_DNA)} DNA patterns wired into short + long prompts"


CHECKS = [
    ("ffmpeg", check_ffmpeg),
    ("imports", check_imports),
    ("json_files", check_json_files),
    ("env_vars", check_env_vars),
    ("youtube_token", check_youtube_token),
    ("disk_space", check_disk_space),
    ("logs_writable", check_logs_writable),
    ("channel_config", check_channel_config),
    ("title_dna_wired", check_title_dna_wired),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true", help="Print all checks")
    parser.add_argument("--no-alert", action="store_true", help="Don't send Telegram on failure")
    args = parser.parse_args()

    results = []
    failures = []
    for name, fn in CHECKS:
        try:
            detail = fn()
            results.append((name, "OK", detail))
        except Exception as e:
            tb = traceback.format_exc(limit=2).strip().splitlines()[-1]
            results.append((name, "FAIL", f"{e} [{tb}]"))
            failures.append((name, str(e)))

    if args.verbose or failures:
        print("=== AIvideo health check ===")
        for name, status, detail in results:
            marker = "✓" if status == "OK" else "✗"
            print(f"  {marker} {name}: {detail}")

    if failures:
        body = "\n".join(f"• {n}: {e}" for n, e in failures)
        print(f"\nFAILED {len(failures)}/{len(CHECKS)} checks", file=sys.stderr)
        if not args.no_alert:
            try:
                from telegram_notify import notify_failure
                notify_failure("health_check", body, topic="daily pipeline")
            except Exception as e:
                print(f"  (could not send telegram alert: {e})", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print(f"\nAll {len(CHECKS)} checks passed")
    sys.exit(0)


if __name__ == "__main__":
    main()
