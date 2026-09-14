"""Publer API client for TikTok auto-posting (stdlib-only, no `requests`).

Auth: Authorization: Bearer-API <key>, Publer-Workspace-Id: <ws_id>.
Two-step post: upload media → schedule post referencing media id.
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API_BASE = "https://app.publer.com/api/v1"


USER_AGENT = "nihongo-manabi-reels/1.0 (auto_post.py; +https://github.com/Arlong6)"


def _headers(api_key: str, workspace_id: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer-API {api_key}", "User-Agent": USER_AGENT, "Accept": "application/json"}
    if workspace_id:
        h["Publer-Workspace-Id"] = workspace_id
    return h


def _request(method: str, url: str, headers: dict[str, str], body: bytes | None = None, timeout: int = 60) -> dict[str, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        raise RuntimeError(f"Publer {method} {url} → HTTP {e.code}: {err_body[:500]}") from None
    if not raw:
        return {}
    return json.loads(raw)


def list_workspaces(api_key: str) -> list[dict[str, Any]]:
    data = _request("GET", f"{API_BASE}/workspaces", _headers(api_key), timeout=30)
    return data.get("workspaces", data) if isinstance(data, dict) else data


def list_accounts(api_key: str, workspace_id: str) -> list[dict[str, Any]]:
    data = _request("GET", f"{API_BASE}/accounts", _headers(api_key, workspace_id), timeout=30)
    return data.get("accounts", data) if isinstance(data, dict) else data


def _build_multipart(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    """Build multipart/form-data body. Returns (body, content_type)."""
    boundary = f"----publer{uuid.uuid4().hex}"
    buf = io.BytesIO()
    eol = b"\r\n"
    for k, v in fields.items():
        buf.write(f"--{boundary}".encode() + eol)
        buf.write(f'Content-Disposition: form-data; name="{k}"'.encode() + eol + eol)
        buf.write(str(v).encode() + eol)
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    buf.write(f"--{boundary}".encode() + eol)
    buf.write(
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode()
        + eol
    )
    buf.write(f"Content-Type: {mime}".encode() + eol + eol)
    buf.write(file_path.read_bytes() + eol)
    buf.write(f"--{boundary}--".encode() + eol)
    return buf.getvalue(), f"multipart/form-data; boundary={boundary}"


def upload_video(api_key: str, workspace_id: str, video_path: Path) -> dict[str, Any]:
    body, ctype = _build_multipart({"direct_upload": "true", "in_library": "false"}, video_path)
    headers = {**_headers(api_key, workspace_id), "Content-Type": ctype, "Content-Length": str(len(body))}
    return _request("POST", f"{API_BASE}/media", headers, body=body, timeout=600)


def schedule_tiktok_video(
    api_key: str,
    workspace_id: str,
    tiktok_account_id: str,
    media_id: str,
    caption: str,
    thumbnail_url: str | None = None,
    scheduled_at: datetime | None = None,
) -> dict[str, Any]:
    """Schedule a TikTok video. Default scheduled_at = now+90s (effectively immediate)."""
    if scheduled_at is None:
        scheduled_at = datetime.now(timezone.utc) + timedelta(seconds=90)
    thumb = thumbnail_url or ""
    payload = {
        "bulk": {
            "state": "scheduled",
            "posts": [
                {
                    "networks": {
                        "tiktok": {
                            "type": "video",
                            "media": [
                                {
                                    "id": media_id,
                                    "thumbnails": [{"real": thumb, "small": thumb}],
                                }
                            ],
                            "text": caption,
                            "details": {},
                        }
                    },
                    "accounts": [
                        {
                            "id": tiktok_account_id,
                            "scheduled_at": scheduled_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
                        }
                    ],
                }
            ],
        }
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {**_headers(api_key, workspace_id), "Content-Type": "application/json"}
    return _request("POST", f"{API_BASE}/posts/schedule", headers, body=body, timeout=60)


def post_video_to_tiktok(video_path: Path, caption: str) -> dict[str, Any]:
    """High-level helper auto_post.py uses. Reads env, uploads, schedules.

    Returns {"media_id": ..., "schedule_response": ...}.
    Raises RuntimeError if env vars missing.
    """
    api_key = os.environ.get("PUBLER_API_KEY")
    workspace_id = os.environ.get("PUBLER_WORKSPACE_ID")
    account_id = os.environ.get("PUBLER_TIKTOK_ACCOUNT_ID")
    missing = [k for k, v in [
        ("PUBLER_API_KEY", api_key),
        ("PUBLER_WORKSPACE_ID", workspace_id),
        ("PUBLER_TIKTOK_ACCOUNT_ID", account_id),
    ] if not v]
    if missing:
        raise RuntimeError(f"Publer env vars missing: {', '.join(missing)}")
    upload = upload_video(api_key, workspace_id, video_path)
    media_id = upload.get("id")
    if not media_id:
        raise RuntimeError(f"Publer upload returned no id: {upload}")
    thumb = upload.get("thumbnail") or upload.get("path")
    schedule = schedule_tiktok_video(api_key, workspace_id, account_id, media_id, caption, thumbnail_url=thumb)
    return {"media_id": media_id, "thumbnail": thumb, "schedule_response": schedule}
