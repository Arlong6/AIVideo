"""
AI-generated illustrations for the books channel (Route B).

Dual-provider pipeline:
  1. Primary: Google Imagen 4 Fast — high quality, $0.02/image, paid tier 1
     limit 70 images/day
  2. Fallback: Pollinations.ai Flux — free, no auth, used automatically when
     Imagen quota is exhausted OR Imagen returns errors

Each generated PNG becomes a Ken Burns landscape clip (1920x1080) so the
video assembler consumes them just like Pexels footage.

2026-04-09 v3+: Added quota tracking to avoid the "silent quota exhaustion"
trap where a render fails halfway through with 429 errors. The tracker
persists to `data/imagen_quota.json` and resets on Pacific Time date change
(matching Google's actual quota reset).
"""
import json
import os
import random
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import requests
from PIL import Image as PILImage
from moviepy.editor import VideoClip

from google import genai
from config import GEMINI_API_KEY

# Books channel uses 16:9 landscape long-form.
LANDSCAPE_W, LANDSCAPE_H = 1920, 1080

# Style prefix prepended to every scene prompt.
# 2026-04-09 v3: Restored the exact "1940s wartime poster" phrasing from the
# S3 sample the user approved. v2's generalized prefix lost fidelity —
# removing "1940s wartime poster" weakened the vintage style anchor and
# some scenes came out cartoony. Keeping the specific historical anchor
# gives Imagen a stronger style target. The prefix still works for non-WWII
# topics because the KEY anchors are "editorial illustration" and "gouache
# painted", not the era.
BOOKS_STYLE_PREFIX = (
    "Vintage 20th century editorial illustration, "
    "2D painted in gouache and watercolor, "
    "warm muted historical color palette, sepia and deep blues, "
    "mature serious historical documentary aesthetic, "
    "soft painterly brushwork, textured paper feel, "
    "in the style of a history book illustration, "
    "not photorealistic, no 3D render, no digital art, "
    "no text, no letters, no words, "
    "cinematic 16:9 composition, of "
)

IMAGEN_MODEL = "imagen-4.0-fast-generate-001"

# Paid tier 1 daily limit as of 2026-04-09. Hitting this throws 429 with
# "quota exceeded".
#
# Google Gemini API RPD quotas reset at midnight PACIFIC TIME (not UTC).
# Verified 2026-04-10: quota tracker used UTC date and falsely reset at
# Taiwan 08:00, but the real Google counter didn't clear until Taiwan 15:00
# (PDT midnight = UTC 07:00 in April DST). See Google docs:
#   https://ai.google.dev/gemini-api/docs/rate-limits
# "Requests per day (RPD) quotas reset at midnight Pacific time."
IMAGEN_DAILY_LIMIT = 70
# Switch to Pollinations fallback when we hit this many — leaves buffer.
IMAGEN_SWITCH_AT = 60
# Seconds to wait between Imagen calls (prevent burst rate-limit)
# 2026-04-12: raised from 4 to 8 seconds after hitting RPM (per-minute) rate
# limit at pair 43/59. At 4s = 15 RPM which exceeded Imagen 4 Fast's ~10 RPM
# paid-tier-1 limit. 8s = 7.5 RPM, safely within bounds.
IMAGEN_CALL_DELAY = 8.0

# Pollinations.ai free Flux endpoint — no auth, no quota (rate-limited).
POLLINATIONS_URL_TEMPLATE = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=1920&height=1080&model=flux&nologo=true&safe=true"
)

# Per-daily quota tracker (persists across script runs same day)
QUOTA_FILE = os.path.join("data", "imagen_quota.json")


_PT_TZ = ZoneInfo("America/Los_Angeles")


def _pt_today() -> str:
    """Today's date in Pacific Time — the timezone Google uses for RPD reset."""
    return datetime.now(_PT_TZ).strftime("%Y-%m-%d")


# ── Quota tracking ────────────────────────────────────────────────────────────

def _load_quota() -> dict:
    """Load today's Imagen quota state. Resets on Pacific Time date change
    (to match Google's actual reset — see IMAGEN_DAILY_LIMIT comment)."""
    today = _pt_today()
    if not os.path.exists(QUOTA_FILE):
        return {"date": today, "count": 0, "limit": IMAGEN_DAILY_LIMIT}
    try:
        with open(QUOTA_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") != today:
            # New PT day — Google's daily counter cleared, so we reset too
            return {"date": today, "count": 0, "limit": IMAGEN_DAILY_LIMIT}
        return data
    except Exception:
        return {"date": today, "count": 0, "limit": IMAGEN_DAILY_LIMIT}


def _save_quota(data: dict):
    os.makedirs(os.path.dirname(QUOTA_FILE), exist_ok=True)
    with open(QUOTA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _imagen_has_quota() -> bool:
    """Return True if it's safe to call Imagen (haven't hit switch threshold)."""
    q = _load_quota()
    return q["count"] < IMAGEN_SWITCH_AT


def _consume_imagen_quota():
    """Increment today's Imagen counter. Fire Telegram warning at 80%."""
    q = _load_quota()
    q["count"] += 1
    _save_quota(q)
    # Warn once when crossing 80% threshold
    if q["count"] == int(IMAGEN_DAILY_LIMIT * 0.8):
        try:
            from telegram_notify import _send_raw
            _send_raw(
                f"⚠️ [AIvideo] Imagen 配額 80% 警告\n"
                f"今日已用: {q['count']}/{IMAGEN_DAILY_LIMIT}\n"
                f"剩餘 {IMAGEN_DAILY_LIMIT - q['count']} 張前會自動切換 Pollinations 備援\n"
                f"PT 00:00 (台灣 15:00 / 16:00 看 DST) 會 reset"
            )
        except Exception:
            pass


def _mark_imagen_exhausted():
    """Force count to max so the rest of this render uses Pollinations."""
    q = _load_quota()
    q["count"] = IMAGEN_DAILY_LIMIT
    _save_quota(q)
    try:
        from telegram_notify import _send_raw
        _send_raw(
            f"🔄 [AIvideo] Imagen 配額用完，本次及後續改用 Pollinations.ai 備援\n"
            f"(免費、品質略遜但可接受)\n"
            f"PT 00:00 (台灣 15:00 / 16:00 看 DST) 自動 reset"
        )
    except Exception:
        pass


# ── Pollinations.ai fallback provider ─────────────────────────────────────────

def _generate_with_pollinations(prompt: str, output_path: str) -> bool:
    """Fetch an image from Pollinations.ai free Flux endpoint.

    Returns True on success. No API key, no quota, but subject to their
    public rate limits (we don't pound it — only used as Imagen fallback).
    """
    encoded = urllib.parse.quote(prompt, safe="")
    url = POLLINATIONS_URL_TEMPLATE.format(prompt=encoded)
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 10_000:
                with open(output_path, "wb") as f:
                    f.write(resp.content)
                return True
            print(f"    [WARN] Pollinations attempt {attempt + 1}: "
                  f"status={resp.status_code} size={len(resp.content)}")
        except Exception as e:
            print(f"    [WARN] Pollinations attempt {attempt + 1}: {e}")
        time.sleep(5)
    return False


# ── Imagen API ────────────────────────────────────────────────────────────────

def _clean_scene_prompt(scene: str) -> str:
    """Defensive sanitization: strip tokens that bias Imagen toward
    photographic output instead of illustration.

    Specifically removes the 'Pexels/Wiki:' / 'Pexels:' / 'Wiki:' prefix
    (remnants of the script_generator_books prompt template before 2026-04-09
    fix) and phrases like 'photo of', 'archival footage of' which Imagen
    interprets literally and produces photographic results.
    """
    import re
    s = scene
    # Strip leading source labels
    s = re.sub(r"^\s*(Pexels/Wiki|Pexels|Wiki|Stock)\s*[:：]\s*", "", s, flags=re.IGNORECASE)
    # Strip photography-biasing phrases
    for phrase in [
        "iconic photo of", "photograph of", "photo of",
        "archival footage of", "archival photo of", "archival image of",
        "historical footage of", "vintage photo of",
        "stock footage of", "b-roll of",
    ]:
        s = re.sub(re.escape(phrase), "", s, flags=re.IGNORECASE)
    return s.strip(" ,.;")


def _generate_with_imagen(prompt: str, output_path: str, client) -> str | None:
    """Call Imagen 4 Fast directly. Returns 'ok', 'quota', or 'error'."""
    try:
        response = client.models.generate_images(
            model=IMAGEN_MODEL,
            prompt=prompt,
            config={
                "number_of_images": 1,
                "aspect_ratio": "16:9",
            },
        )
        imgs = getattr(response, "generated_images", None) or []
        for gen in imgs:
            gen.image.save(output_path)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10_000:
                return "ok"
        return "error"
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "quota" in msg or "resource_exhausted" in msg:
            return "quota"
        print(f"    [WARN] Imagen error: {str(e)[:150]}")
        return "error"


class ImagenQuotaExhausted(Exception):
    """Raised when Imagen daily quota is hit and fallback is not allowed.
    Callers catch this to stop the pipeline cleanly and Telegram-alert the user."""
    pass


def generate_illustration(scene: str, output_path: str,
                          client=None,
                          style_prefix: str | None = None,
                          allow_fallback: bool = False) -> bool:
    """Generate one illustration via Imagen 4 Fast.

    Strict quality mode (default): Imagen only. If quota is exhausted or
    Imagen fails, raises ImagenQuotaExhausted or returns False — caller
    decides whether to stop the whole render. This matches user's
    2026-04-09 feedback: quality consistency > keeping the pipeline running.

    Relaxed mode (allow_fallback=True): if Imagen hits quota, fall back to
    Pollinations.ai free Flux. Use only when user explicitly opts in via
    --allow-fallback or similar.

    Returns True on success.
    Raises ImagenQuotaExhausted if quota is gone and fallback is disallowed.
    """
    if client is None:
        client = genai.Client(api_key=GEMINI_API_KEY)

    cleaned_scene = _clean_scene_prompt(scene)
    prompt = (style_prefix or BOOKS_STYLE_PREFIX) + cleaned_scene + ", cinematic 16:9"

    # Primary: Imagen 4 Fast
    if _imagen_has_quota():
        for attempt in range(2):
            result = _generate_with_imagen(prompt, output_path, client)
            if result == "ok":
                _consume_imagen_quota()
                time.sleep(IMAGEN_CALL_DELAY)
                return True
            if result == "quota":
                print(f"    [INFO] Imagen quota exhausted during run")
                _mark_imagen_exhausted()
                break
            # else: error — retry once
            time.sleep(2)

    # At this point Imagen is either out of quota or failing.
    if not allow_fallback:
        raise ImagenQuotaExhausted(
            "Imagen 4 Fast unavailable (quota or error). "
            "Fallback to Pollinations is DISABLED by default to preserve "
            "quality baseline. Re-run with --allow-fallback to use free Flux, "
            "or wait for PT 00:00 (≈ Taiwan 15:00/16:00) quota reset."
        )

    # Opt-in fallback: Pollinations.ai free Flux
    print(f"    [INFO] Using Pollinations.ai fallback (explicit opt-in)")
    if _generate_with_pollinations(prompt, output_path):
        return True

    return False


# ── Landscape Ken Burns (parallel to wiki_footage portrait version) ───────────

def _fit_for_ken_burns(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Resize image to be larger than target, giving room to pan/zoom."""
    h, w = img.shape[:2]
    target_ratio = target_w / target_h  # 16:9 = 1.778
    img_ratio = w / h
    pad = 1.18

    if img_ratio > target_ratio:
        # Wider than target — fit by height
        new_h = int(target_h * pad)
        new_w = int(new_h * img_ratio)
    else:
        # Taller than target — fit by width
        new_w = int(target_w * pad)
        new_h = int(new_w / img_ratio)

    pil = PILImage.fromarray(img).resize((new_w, new_h), PILImage.LANCZOS)
    return np.array(pil)


def _make_ken_burns_clip(img: np.ndarray, duration: float = 8.0,
                         target_w: int = LANDSCAPE_W,
                         target_h: int = LANDSCAPE_H) -> VideoClip:
    """Create a Ken Burns video clip from a static image for landscape 1920x1080."""
    base = _fit_for_ken_burns(img, target_w, target_h)
    bh, bw = base.shape[:2]
    tw, th = target_w, target_h

    effect = random.choice(["zoom_in", "zoom_out", "pan_right", "pan_left"])
    max_dx = max(0, bw - tw)
    max_dy = max(0, bh - th)

    def make_frame(t: float) -> np.ndarray:
        p = t / duration  # 0→1

        if effect == "zoom_in":
            scale = 1.0 - 0.12 * p
            cw = min(int(tw * (1 / scale)), bw)
            ch = min(int(th * (1 / scale)), bh)
            x0 = (bw - cw) // 2
            y0 = (bh - ch) // 2
        elif effect == "zoom_out":
            scale = 0.88 + 0.12 * p
            cw = min(int(tw * (1 / scale)), bw)
            ch = min(int(th * (1 / scale)), bh)
            x0 = (bw - cw) // 2
            y0 = (bh - ch) // 2
        elif effect == "pan_right":
            x0 = int(max_dx * p)
            y0 = max_dy // 2
            cw, ch = tw, th
        else:  # pan_left
            x0 = max_dx - int(max_dx * p)
            y0 = max_dy // 2
            cw, ch = tw, th

        x0 = max(0, min(x0, bw - cw))
        y0 = max(0, min(y0, bh - ch))
        crop = base[y0:y0 + ch, x0:x0 + cw]
        frame = np.array(PILImage.fromarray(crop).resize((tw, th), PILImage.LANCZOS))
        return frame

    return VideoClip(make_frame, duration=duration).set_fps(25)


# ── Batch entry point ─────────────────────────────────────────────────────────

def generate_illustrations_batch(
    scenes: list[str],
    output_dir: str,
    duration_per_clip: float = 8.0,
    style_prefix: str | None = None,
) -> list[str]:
    """Generate Imagen illustrations for a list of scene descriptions, turn each
    into a Ken Burns landscape clip, and save with the same naming convention
    used by Pexels download_footage (so video_assembler consumes them unchanged).

    Returns list of generated clip paths.
    """
    clips_dir = os.path.join(output_dir, "clips")
    illustrations_dir = os.path.join(output_dir, "illustrations")
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(illustrations_dir, exist_ok=True)

    client = genai.Client(api_key=GEMINI_API_KEY)
    clip_paths: list[str] = []
    failures = 0

    for i, scene in enumerate(scenes):
        preview = scene[:60].replace("\n", " ")
        print(f"  [{i + 1}/{len(scenes)}] {preview}")

        png_path = os.path.join(illustrations_dir, f"scene_{i:02d}.png")
        clip_path = os.path.join(clips_dir, f"s{i:02d}_clip1.mp4")

        ok = generate_illustration(scene, png_path, client=client,
                                    style_prefix=style_prefix)
        if not ok:
            failures += 1
            print(f"    ✗ Imagen failed, scene skipped")
            continue

        # Convert PNG → Ken Burns mp4 clip
        try:
            img = np.array(PILImage.open(png_path).convert("RGB"))
            clip = _make_ken_burns_clip(img, duration=duration_per_clip)
            clip.write_videofile(clip_path, fps=25, codec="libx264",
                                 audio=False, logger=None)
            clip.close()
            clip_paths.append(clip_path)
            print(f"    ✓ s{i:02d}_clip1.mp4")
        except Exception as e:
            failures += 1
            print(f"    ✗ Ken Burns failed: {e}")

    print(f"\n  Illustration batch done: {len(clip_paths)}/{len(scenes)} success, "
          f"{failures} failed")
    return clip_paths


def generate_illustrations_from_pairs(
    pairs: list[dict],
    output_dir: str,
    style_prefix: str | None = None,
    allow_fallback: bool = False,
) -> list[str]:
    """v5 sentence-pair flow: one illustration per pair, each at its own duration.

    Each pair dict has keys:
      - "text": the concatenated text of the 2 (or 1) sentences
      - "duration": exact TTS duration in seconds for this pair

    allow_fallback: if True, permit Pollinations.ai free Flux as emergency
    fallback when Imagen is exhausted. Default False — quality baseline
    requires Imagen output. When False and quota hits, raises
    ImagenQuotaExhausted to stop the pipeline cleanly.

    Returns list of mp4 clip paths in pair order.
    """
    clips_dir = os.path.join(output_dir, "clips")
    illustrations_dir = os.path.join(output_dir, "illustrations")
    os.makedirs(clips_dir, exist_ok=True)
    os.makedirs(illustrations_dir, exist_ok=True)

    client = genai.Client(api_key=GEMINI_API_KEY)
    clip_paths: list[str] = []
    failures = 0
    total_pairs = len(pairs)

    # Pre-flight quota check — fail fast if we can't even start
    q = _load_quota()
    if not allow_fallback and not _imagen_has_quota():
        try:
            from telegram_notify import _send_raw
            _send_raw(
                f"❌ [AIvideo books] Imagen 配額已耗盡 ({q['count']}/{IMAGEN_DAILY_LIMIT})\n"
                f"Route B 品質要求禁止切免費備援\n"
                f"請等 PT 00:00 (台灣 15:00 / 16:00 看 DST) reset，或加 --allow-fallback"
            )
        except Exception:
            pass
        raise ImagenQuotaExhausted(
            f"Imagen quota already exhausted at start ({q['count']}/{IMAGEN_DAILY_LIMIT}). "
            f"Wait for PT 00:00 reset (≈ Taiwan 15:00/16:00) or pass allow_fallback=True."
        )

    for i, pair in enumerate(pairs):
        text = pair["text"]
        duration = float(pair["duration"])
        preview = text[:70].replace("\n", " ")
        print(f"  [{i + 1}/{total_pairs}] ({duration:.1f}s) {preview}")

        png_path = os.path.join(illustrations_dir, f"pair_{i:03d}.png")
        clip_path = os.path.join(clips_dir, f"p{i:03d}_clip1.mp4")

        try:
            ok = generate_illustration(text, png_path, client=client,
                                       style_prefix=style_prefix,
                                       allow_fallback=allow_fallback)
        except ImagenQuotaExhausted as e:
            # Mid-run quota exhaustion — save what we have and stop cleanly
            print(f"\n  [STOP] Imagen quota exhausted at pair {i + 1}/{total_pairs}")
            print(f"         Generated {len(clip_paths)} clips so far.")
            try:
                from telegram_notify import _send_raw
                _send_raw(
                    f"❌ [AIvideo books] 渲染中途 Imagen 配額耗盡\n"
                    f"已產出: {len(clip_paths)}/{total_pairs} 張\n"
                    f"停在第 {i + 1} 張\n"
                    f"等 PT 00:00 (台灣 15:00 / 16:00 看 DST) reset 再試"
                )
            except Exception:
                pass
            raise

        if not ok:
            failures += 1
            print(f"    ✗ Provider failed, pair skipped")
            continue

        # Convert PNG → Ken Burns mp4 at the EXACT pair duration
        try:
            img = np.array(PILImage.open(png_path).convert("RGB"))
            clip = _make_ken_burns_clip(img, duration=duration)
            clip.write_videofile(clip_path, fps=25, codec="libx264",
                                 audio=False, logger=None)
            clip.close()
            clip_paths.append(clip_path)
            print(f"    ✓ p{i:03d}_clip1.mp4 ({duration:.1f}s)")
        except Exception as e:
            failures += 1
            print(f"    ✗ Ken Burns failed: {e}")

    print(f"\n  Pair batch done: {len(clip_paths)}/{total_pairs} success, "
          f"{failures} failed")
    return clip_paths
