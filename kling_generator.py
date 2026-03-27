"""
Kling AI video generation for true crime scene clips.
Uses hybrid strategy: AI-generate topic-specific scenes, Pexels for generic atmosphere.
API docs: https://docs.qingque.cn/d/home/eZQDvivgMPyKlvWKZPbTU45eY
"""

import time
import jwt
import requests
import os
from config import KLING_ACCESS_KEY, KLING_SECRET_KEY

KLING_API_BASE = "https://api.klingai.com"
# How many AI clips to generate per video (conserves credits)
AI_CLIPS_PER_VIDEO = 6
# Clip duration in seconds (5s is cheapest tier)
CLIP_DURATION = 5


def _make_jwt() -> str:
    """Generate a short-lived JWT token for Kling API auth."""
    now = int(time.time())
    payload = {
        "iss": KLING_ACCESS_KEY,
        "exp": now + 1800,   # 30 min expiry
        "nbf": now - 5,
    }
    return jwt.encode(payload, KLING_SECRET_KEY, algorithm="HS256")


def _scene_prompt(subtitle_text: str, topic: str) -> str:
    """
    Convert a subtitle card into a cinematic video generation prompt.
    Dark true crime documentary style.
    """
    base_style = (
        "cinematic dark atmospheric shot, true crime documentary style, "
        "moody blue-teal color grade, film noir lighting, shallow depth of field, "
        "slow camera movement, 9:16 vertical format"
    )
    return f"{subtitle_text}. {base_style}. Related to: {topic}"


def _submit_generation(prompt: str) -> str | None:
    """Submit a video generation task and return task ID."""
    token = _make_jwt()
    resp = requests.post(
        f"{KLING_API_BASE}/v1/videos/text2video",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model_name": "kling-v1",
            "prompt": prompt,
            "negative_prompt": "text, watermark, logo, bright colors, happy, cheerful",
            "cfg_scale": 0.5,
            "mode": "std",           # std = 10 credits/clip (vs pro = 35)
            "aspect_ratio": "9:16",
            "duration": str(CLIP_DURATION),
        },
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  [WARN] Kling submit failed: {resp.status_code} {resp.text[:200]}")
        return None
    data = resp.json()
    task_id = data.get("data", {}).get("task_id")
    return task_id


def _poll_task(task_id: str, timeout_sec: int = 300) -> str | None:
    """Poll task until complete. Returns video URL or None."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        token = _make_jwt()
        resp = requests.get(
            f"{KLING_API_BASE}/v1/videos/text2video/{task_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        if resp.status_code != 200:
            time.sleep(5)
            continue

        data = resp.json().get("data", {})
        status = data.get("task_status")

        if status == "succeed":
            videos = data.get("task_result", {}).get("videos", [])
            if videos:
                return videos[0].get("url")
            return None
        elif status == "failed":
            print(f"  [WARN] Kling task failed: {data.get('task_status_msg', '')}")
            return None
        # Still processing — wait and retry
        time.sleep(8)

    print(f"  [WARN] Kling task {task_id} timed out")
    return None


def _download_clip(url: str, filepath: str) -> bool:
    """Download a generated video clip."""
    try:
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"  [WARN] Clip download failed: {e}")
        return False


def generate_ai_clips(
    subtitle_cards: list[str],
    topic: str,
    output_dir: str,
    max_clips: int = AI_CLIPS_PER_VIDEO,
) -> list[str]:
    """
    Generate AI video clips for key subtitle scenes using Kling.

    Selects `max_clips` evenly-spaced subtitle cards as prompts,
    generates them in parallel (submit all, then poll all).

    Returns list of saved clip file paths.
    """
    if not KLING_ACCESS_KEY or not KLING_SECRET_KEY:
        print("  [SKIP] No Kling API keys configured")
        return []

    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    # Pick evenly-spaced cards as key scenes (skip first/last which are usually intro/outro)
    n = len(subtitle_cards)
    if n <= max_clips:
        selected = subtitle_cards
    else:
        step = n / max_clips
        selected = [subtitle_cards[int(i * step)] for i in range(max_clips)]

    print(f"  Generating {len(selected)} AI clips with Kling...")

    # Submit all tasks first
    tasks = []
    for i, card in enumerate(selected):
        prompt = _scene_prompt(card, topic)
        print(f"  Submitting scene {i+1}/{len(selected)}: {card[:30]}...")
        task_id = _submit_generation(prompt)
        if task_id:
            tasks.append((i, task_id, card))
        else:
            print(f"  [SKIP] Submit failed for scene {i+1}")
        time.sleep(1)   # brief pause between submissions

    # Poll all tasks and download
    saved_paths = []
    for i, task_id, card in tasks:
        print(f"  Waiting for scene {i+1} ({task_id[:12]}...)...")
        url = _poll_task(task_id)
        if not url:
            continue
        filename = f"ai_{i+1:02d}_{card[:20].replace(' ', '_')}.mp4"
        filepath = os.path.join(clips_dir, filename)
        if _download_clip(url, filepath):
            print(f"  ✅ AI clip saved: {filename}")
            saved_paths.append(filepath)

    print(f"  Generated {len(saved_paths)}/{len(selected)} AI clips")
    return saved_paths
