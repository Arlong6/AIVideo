"""Scrape Taiwanese true-crime competitors and produce a pattern report."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import urlparse

from anthropic import Anthropic
from dotenv import load_dotenv
from yt_dlp import YoutubeDL

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"
CHANNELS_JSON = SCRIPTS_DIR / "channels.json"
TODAY = datetime.now().strftime("%Y-%m-%d")
VIDEOS_PER_CHANNEL = 30

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
ANALYSIS_MODEL = os.getenv("COMPETITOR_ANALYSIS_MODEL", "claude-sonnet-4-6")


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "dict"):
        dumped = value.dict()
        return dumped if isinstance(dumped, dict) else {}
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _load_channels() -> list[str]:
    if not CHANNELS_JSON.exists():
        raise FileNotFoundError(
            f"Missing {CHANNELS_JSON}. Expected format: "
            '{"channels": ["https://www.youtube.com/@channel1"]}'
        )
    data = json.loads(CHANNELS_JSON.read_text(encoding="utf-8"))
    channels = data.get("channels")
    if not isinstance(channels, list) or not all(isinstance(url, str) for url in channels):
        raise ValueError(f"{CHANNELS_JSON} must contain a string list under 'channels'.")
    return [url.strip() for url in channels if url.strip()]


def _channel_handle(url: str) -> str:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    raw = next((part for part in parts if part.startswith("@")), parts[-1] if parts else parsed.netloc)
    handle = re.sub(r"[^A-Za-z0-9_.@-]+", "_", raw).strip("._-")
    if handle:
        return handle[:80]
    return f"channel_{hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]}"


def _channel_root(channel_url: str) -> str:
    """yt-dlp returns sub-tab entries for some channel roots; always hit /videos."""
    clean = channel_url.split("?", 1)[0].rstrip("/")
    if clean.endswith("/videos") or clean.endswith("/shorts") or clean.endswith("/streams"):
        return clean
    return f"{clean}/videos"


def _raw_path(channel_url: str) -> Path:
    return DATA_DIR / f"competitor_raw_{_channel_handle(channel_url)}_{TODAY}.json"


def _ytdlp_extract(url: str) -> dict[str, Any]:
    """Fetch up to VIDEOS_PER_CHANNEL videos using yt-dlp's flat playlist mode."""
    opts = {
        "extract_flat": "in_playlist",
        "playlistend": VIDEOS_PER_CHANNEL,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": True,
    }
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def _scrape_channel(channel_url: str) -> dict[str, Any]:
    path = _raw_path(channel_url)
    if path.exists():
        print(f"[cache] {channel_url} -> {path.name}")
        return json.loads(path.read_text(encoding="utf-8"))

    target_url = _channel_root(channel_url)
    print(f"[yt-dlp] {target_url}")
    info = _ytdlp_extract(target_url)
    raw_entries = info.get("entries") or []

    videos: list[dict[str, Any]] = []
    for entry in raw_entries[:VIDEOS_PER_CHANNEL]:
        if not isinstance(entry, dict):
            continue
        video_id = entry.get("id") or ""
        title = entry.get("title") or ""
        if not video_id or not title:
            continue
        thumb = entry.get("thumbnails") or []
        thumb_url = ""
        if isinstance(thumb, list) and thumb:
            best = thumb[-1]
            if isinstance(best, dict):
                thumb_url = str(best.get("url", ""))
        if not thumb_url:
            thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        videos.append({
            "video_id": video_id,
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            "source_channel_url": channel_url,
            "title": title,
            "thumbnail_url": thumb_url,
            "view_count": entry.get("view_count"),
            "view_count_raw": "",
            "publish_date": entry.get("upload_date") or entry.get("release_timestamp") or "",
            "duration": entry.get("duration"),
            "description": (entry.get("description") or "")[:200],
        })

    payload = {
        "channel_url": channel_url,
        "channel_root": target_url,
        "channel_handle": _channel_handle(channel_url),
        "channel_name": info.get("channel") or info.get("uploader") or "",
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
        "video_count": len(videos),
        "videos": videos,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[save] {path.name}: {len(videos)} videos")
    return payload


def _channel_stats(channel: dict[str, Any]) -> dict[str, Any]:
    views = [
        int(video["view_count"])
        for video in channel.get("videos", [])
        if isinstance(video.get("view_count"), int)
    ]
    med = int(median(views)) if views else 0
    outliers = [
        video for video in channel.get("videos", [])
        if isinstance(video.get("view_count"), int) and med > 0 and video["view_count"] >= med * 3
    ]
    return {
        "channel_url": channel["channel_url"],
        "channel_handle": channel["channel_handle"],
        "video_count": len(channel.get("videos", [])),
        "median_views": med,
        "max_views": max(views) if views else 0,
        "outlier_count": len(outliers),
        "outliers": outliers,
    }


def _analysis_payload(channels: list[dict[str, Any]], errors: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "date": TODAY,
        "errors": errors,
        "channels": [
            {
                **_channel_stats(channel),
                "videos": [
                    {
                        "title": video.get("title", ""),
                        "thumbnail_url": video.get("thumbnail_url", ""),
                        "views": video.get("view_count"),
                        "views_raw": video.get("view_count_raw", ""),
                        "publish_date": video.get("publish_date", ""),
                        "description_head": str(video.get("description", ""))[:200].replace("\n", " "),
                    }
                    for video in channel.get("videos", [])
                ],
            }
            for channel in channels
        ],
    }


def _fallback_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# Competitor Analysis - {TODAY}",
        "",
        "## Per-channel summary",
    ]
    for channel in payload["channels"]:
        lines.append(
            f"- {channel['channel_handle']}: {channel['video_count']} videos, "
            f"median views {channel['median_views']:,}, outliers {channel['outlier_count']}"
        )
    if payload["errors"]:
        lines.append("")
        lines.append("Scrape errors:")
        for error in payload["errors"]:
            lines.append(f"- {error['channel_url']}: {error['error']}")
    lines.extend([
        "",
        "## Cross-channel title patterns",
        "OpenAI analysis was skipped because no scraped videos were available.",
        "",
        "## Outlier teardown",
        "No outlier teardown available.",
        "",
        "## Recommendations for our channel (5 concrete actions)",
        "1. Confirm each URL points to a public YouTube channel videos tab.",
        "2. Re-run with Firecrawl returning HTML so ytInitialData can be parsed.",
        "3. Keep same-day raw cache files for channels that scraped successfully.",
        "4. Do not make title or thumbnail decisions until at least 20 videos per channel are available.",
        "5. Review scrape errors above before spending OpenAI analysis tokens again.",
    ])
    return "\n".join(lines)


def _call_anthropic(payload: dict[str, Any]) -> str:
    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    prompt = f"""
You are a YouTube strategy analyst for a Taiwanese true-crime channel.

Use only the supplied scraped data. Do not invent channel names, videos,
view counts, thumbnail details, or facts. If thumbnail URL alone is
insufficient to determine dominant colors or text placement, explicitly say
that thumbnail visual analysis is skipped.

Analyze title structures against view counts, per-channel 3x median outliers,
and description hooks/keyword density. Write Traditional Chinese markdown with
exactly these sections:

## Per-channel summary
## Cross-channel title patterns
## Outlier teardown
## Recommendations for our channel (5 concrete actions)

For each channel summary include video count, median views, high performers,
and scrape gaps. For title patterns, name concrete sentence structures and use
real titles as examples. For outliers, explain what videos with 3x+ channel
median share. End with five specific actions only.

Scraped data JSON:
{json.dumps(payload, ensure_ascii=False)}
""".strip()
    response = client.messages.create(
        model=ANALYSIS_MODEL,
        max_tokens=8192,
        system="You produce concise, evidence-grounded YouTube competitor analysis.",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    blocks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
    content = "".join(blocks).strip()
    if not content:
        raise RuntimeError("Anthropic returned an empty analysis.")
    return content


def _notify(report_path: Path, channels: list[dict[str, Any]], errors: list[dict[str, str]]) -> None:
    try:
        from telegram_notify import _send_raw

        total_videos = sum(len(channel.get("videos", [])) for channel in channels)
        _send_raw(
            "\n".join([
                f"🔍 [AIvideo] 競品分析完成 ({TODAY})",
                f"頻道: {len(channels)} / 影片: {total_videos}",
                f"錯誤: {len(errors)}",
                f"Report: {report_path}",
            ])
        )
        print("[telegram] notified")
    except Exception as exc:
        print(f"[telegram] skipped: {exc}")


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    channels = _load_channels()
    if len(channels) > 5:
        print(f"[warn] channels.json has {len(channels)} URLs; using first 5 to control Firecrawl credits.")
        channels = channels[:5]

    scraped: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for channel_url in channels:
        try:
            channel = _scrape_channel(channel_url)
            if not channel.get("videos"):
                raise RuntimeError("No videos extracted from channel videos page.")
            scraped.append(channel)
        except Exception as exc:
            print(f"[error] {channel_url}: {exc}")
            errors.append({"channel_url": channel_url, "error": str(exc)})

    payload = _analysis_payload(scraped, errors)
    report_path = DATA_DIR / f"competitor_analysis_{TODAY}.md"
    if sum(channel["video_count"] for channel in payload["channels"]) == 0:
        report = _fallback_report(payload)
    else:
        report = _call_anthropic(payload)
    report_path.write_text(report, encoding="utf-8")
    print(f"[save] report -> {report_path}")
    _notify(report_path, scraped, errors)


if __name__ == "__main__":
    main()
