"""
Visual Agent — footage sourcing and content-matching.

Priority order:
1. Wikimedia real photos (with Pixabay image backup if rate limited)
2. Crime location maps
3. Info cards (case file, timeline, breaking news)
4. Pexels video (transitions only, ASIA-focused keywords)
"""
import os
import sys
import time

# Allow importing project-root modules (illustration_generator quota helpers,
# wiki_footage Ken Burns) since visual_agent lives in agents/.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ── Crime Imagen (Phase 1 video_quality_upgrade, 2026-04-29) ────────────────
# Generate 1 Ultra + 2 Fast variants per key narrative beat (hook/twist/
# resolution). Cost target: ~$0.30/video. Reuses illustration_generator's
# existing quota tracker so we don't double-spend the 70/day budget that
# thumbnail_generator and (formerly) books also tap.

# Neo-noir prefix validated 2026-05-13 against 4 crime scenes (aftermath /
# investigation / location / exterior). All 4 passed Imagen safety filter
# using oblique framing (objects + setting, not violent acts). See
# scripts/test_noir_style.py for the validation harness.
CRIME_STYLE_PREFIX = (
    "cinematic 16:9, neo-noir crime film aesthetic, "
    "extreme chiaroscuro lighting with deep shadows obscuring half the frame, "
    "desaturated near-monochrome palette, cool steel-blue and amber sodium tones, "
    "single hard practical light source like a streetlight or naked bulb or neon glow, "
    "heavy 35mm film grain, atmospheric haze, dust motes in the light beam, "
    "ominous oppressive mood, empty abandoned space, "
    "no text, no letters, no signs, no watermark, no faces, no people, no humans, "
    "shot on ARRI Alexa, of "
)

# 3 beats get multi-variant emphasis (1 Ultra + 2 Fast for angle variety).
KEY_SECTION_NAMES = ("hook", "twist", "resolution")
# Other narrative sections also get Imagen coverage to kill the Pexels stock
# soup that made the long-form look like disconnected clips. Each gets 1 Fast
# image. Section names per script_agent: hook/background/crime/investigation/
# twist/resolution/reflection/cta.
SECONDARY_SECTION_NAMES = ("background", "crime", "investigation", "reflection")
IMAGEN_FAST_MODEL = "imagen-4.0-fast-generate-001"
IMAGEN_ULTRA_MODEL = "imagen-4.0-ultra-generate-001"


def _generate_imagen_clip(visual_hint: str, scene_idx: int, output_dir: str,
                          model: str = "fast", suffix: str = "primary") -> str | None:
    """Generate one Imagen image, Ken Burns it to mp4, return clip path.

    model='ultra' uses imagen-4.0-ultra ($0.06/img); 'fast' uses fast
    ($0.02/img). Quota guard: skips if illustration_generator's tracker
    says we're at the 60-image switch threshold.
    """
    try:
        from illustration_generator import _imagen_has_quota, _consume_imagen_quota
    except Exception:
        # If illustration_generator not importable, fail open (quota uncounted).
        _imagen_has_quota = lambda: True
        _consume_imagen_quota = lambda: None

    if not _imagen_has_quota():
        print(f"  [Imagen] quota near limit, skip scene {scene_idx} ({suffix})")
        return None

    try:
        import numpy as np
        from PIL import Image as PILImage
        from google import genai
        from config import GEMINI_API_KEY
        # wiki_footage's Ken Burns is hardcoded portrait (1080x1920) for Shorts.
        # illustration_generator's version takes target_w/target_h, so we get
        # 1920x1080 landscape to match the long-form video frame.
        from illustration_generator import _make_ken_burns_clip
    except Exception as e:
        print(f"  [Imagen] import failed: {e}")
        return None

    model_id = IMAGEN_ULTRA_MODEL if model == "ultra" else IMAGEN_FAST_MODEL
    prompt = CRIME_STYLE_PREFIX + visual_hint.strip()

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        result = client.models.generate_images(
            model=model_id,
            prompt=prompt,
            config={"number_of_images": 1, "aspect_ratio": "16:9"},
        )
        imgs = getattr(result, "generated_images", None) or []
        if not imgs:
            print(f"  [Imagen] {model} returned 0 images for scene {scene_idx}")
            return None

        png_dir = os.path.join(output_dir, "imagen")
        os.makedirs(png_dir, exist_ok=True)
        png_path = os.path.join(png_dir, f"s{scene_idx:02d}_{suffix}.png")
        imgs[0].image.save(png_path)
        if not os.path.exists(png_path) or os.path.getsize(png_path) < 10_000:
            print(f"  [Imagen] {model} produced empty file for scene {scene_idx}")
            return None

        _consume_imagen_quota()

        # Render Ken Burns mp4 into wiki_clips/ so orchestrator/assembler
        # treats it identically to wiki photo clips.
        wiki_clips_dir = os.path.join(output_dir, "wiki_clips")
        os.makedirs(wiki_clips_dir, exist_ok=True)
        clip_path = os.path.join(wiki_clips_dir,
                                 f"imagen_s{scene_idx:02d}_{suffix}.mp4")
        img_arr = np.array(PILImage.open(png_path).convert("RGB"))
        clip = _make_ken_burns_clip(img_arr, duration=5.0,
                                     target_w=1920, target_h=1080)
        clip.write_videofile(clip_path, fps=25, codec="libx264",
                             audio=False, logger=None)
        clip.close()
        return clip_path
    except Exception as e:
        msg = str(e)[:150]
        print(f"  [Imagen] {model} failed for scene {scene_idx}: {msg}")
        return None


# Force Asia-focused + cinematic-leaning Pexels searches.
# 2026-04-29: bare locations ("taiwan", "tokyo") returned tourism stock.
# Added noir / shadow / night modifiers so results lean true crime aesthetic.
ASIA_MODIFIERS = [
    "taiwan night cinematic", "taipei rain noir",
    "asia dramatic shadow", "tokyo neon moody",
    "seoul night low light", "asian city dark cinematic",
    "rainy alley shallow depth", "noir city night",
]


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
        "maps": {},
    }

    # 1. Wikimedia real photos
    wiki_queries = []
    for section in visual_plan.get("sections", []):
        wiki_queries.extend(section.get("wiki_search_queries", []))
    wiki_queries.extend(case_data.get("search_keywords_en", []))
    wiki_queries.extend(case_data.get("search_keywords_zh", []))

    seen = set()
    unique_queries = [q for q in wiki_queries if q.lower() not in seen and not seen.add(q.lower())]

    # 2026-05-13: Wikimedia reduced from 25 → 8 as part of the all-noir
    # visual upgrade. The remaining 8 serve as fallback only — Imagen
    # noir scenes are now the primary visual layer. Memory note: most
    # Wiki hits were generic Taipei city photos, not case-specific.
    print(f"  [Visual] Wikimedia: {len(unique_queries)} search queries (fallback layer, max 8)")
    from wiki_footage import get_wiki_clips
    results["wiki_clips"] = get_wiki_clips(
        " ".join(unique_queries[:5]),
        output_dir, max_images=8
    )

    # If Wikimedia returned too few (rate limited), try Pixabay images as backup
    if len(results["wiki_clips"]) < 5:
        print(f"  [Visual] Wiki only got {len(results['wiki_clips'])}, trying Pixabay images...")
        pixabay_clips = _fetch_pixabay_images(case_data, output_dir, count=15)
        results["wiki_clips"].extend(pixabay_clips)

    # 2. Pexels video — ASIA-focused transition footage
    pexels_queries = []
    for section in visual_plan.get("sections", []):
        raw_queries = section.get("pexels_queries", [])
        for q in raw_queries:
            # Add Asia modifier to non-specific queries
            if not any(kw in q.lower() for kw in ["taiwan", "asia", "japan", "korea", "taipei", "tokyo"]):
                modifier = ASIA_MODIFIERS[len(pexels_queries) % len(ASIA_MODIFIERS)]
                q = f"{q} {modifier}"
            pexels_queries.append(q)

    # Also add script's visual_scenes with Asia modifiers
    for q in script_data.get("visual_scenes", []):
        if not any(kw in q.lower() for kw in ["taiwan", "asia", "japan", "korea"]):
            modifier = ASIA_MODIFIERS[len(pexels_queries) % len(ASIA_MODIFIERS)]
            q = f"{q} {modifier}"
        pexels_queries.append(q)

    # Deduplicate
    seen = set()
    unique_pexels = [q for q in pexels_queries if q.lower() not in seen and not seen.add(q.lower())]

    # 2026-05-13: Pexels capped at 10 (was 50) for the noir upgrade. The
    # generic "city street" stock was the worst offender for breaking
    # visual consistency. Kept at non-zero so the assembler still has
    # some video clips for transitions when Imagen stills can't cover.
    print(f"  [Visual] Pexels: {len(unique_pexels)} queries (capped at 10 for noir consistency)")
    from footage_downloader import download_footage
    download_footage(unique_pexels[:10], output_dir, fmt="long")
    results["pexels_clips_dir"] = os.path.join(output_dir, "clips")

    # 3. Info cards (uses case_data directly, no LLM call)
    print("  [Visual] Generating info cards...")
    from info_cards import generate_info_cards
    results["info_cards"] = generate_info_cards(script_data, output_dir, case_data=case_data)

    # 4. Crime location maps
    print("  [Visual] Generating crime location maps...")
    from map_generator import generate_case_maps
    try:
        results["maps"] = generate_case_maps(case_data, output_dir)
    except Exception as e:
        print(f"  [Visual] Map generation failed (non-fatal): {e}")
        results["maps"] = {}

    # 5. Imagen all-noir generation:
    #    - Key beats (hook/twist/resolution): 1 Ultra + 2 Fast variants
    #    - Secondary beats (background/crime/investigation/reflection):
    #      1 Fast image each (single angle, sufficient for narrative flow)
    #    Result: ~14 Imagen calls/video at ~$0.40/video. Quota guard inside
    #    _generate_imagen_clip stops gracefully if 70/day limit is hit, so
    #    secondary scenes degrade to "fewer Imagen, more Wiki/Pexels fallback"
    #    rather than crashing.
    print("  [Visual] Generating Imagen (noir, all sections)...")
    imagen_clips: list[str] = []
    script_sections = script_data.get("sections", [])
    ultra_count = 0
    fast_count = 0
    for sec_idx, sec in enumerate(script_sections):
        sec_name = sec.get("name")
        hints = sec.get("visual_hints", []) or []
        if not hints:
            continue
        primary_hint = hints[0]

        if sec_name in KEY_SECTION_NAMES:
            # 1 Ultra primary + 2 Fast variant angles
            p = _generate_imagen_clip(primary_hint, sec_idx, output_dir,
                                      model="ultra", suffix="ultra")
            if p:
                imagen_clips.append(p)
                ultra_count += 1
            for ang_label, ang_phrase in (("wide", "wide establishing shot"),
                                          ("close", "extreme close-up dramatic")):
                v = _generate_imagen_clip(f"{primary_hint}, {ang_phrase}",
                                          sec_idx, output_dir,
                                          model="fast", suffix=ang_label)
                if v:
                    imagen_clips.append(v)
                    fast_count += 1
        elif sec_name in SECONDARY_SECTION_NAMES:
            # 1 Fast image per secondary section — fills the narrative arc
            # without burning quota. Uses primary hint, no angle suffix.
            f_clip = _generate_imagen_clip(primary_hint, sec_idx, output_dir,
                                           model="fast", suffix="noir")
            if f_clip:
                imagen_clips.append(f_clip)
                fast_count += 1

    results["imagen_clips"] = imagen_clips
    cost = ultra_count * 0.06 + fast_count * 0.02
    print(f"  [Visual] Imagen: {len(imagen_clips)} clips "
          f"({ultra_count}U + {fast_count}F = ${cost:.2f})")

    # 6. Kling motion clips for key beats (FEATURE FLAG, default OFF).
    # When ENABLE_KLING=1 in env, generate 3 noir 16:9 5s clips for the
    # hook/twist/resolution visual_hints. Clips land in wiki_clips/ so the
    # assembler treats them like any other clip. Failure modes (no creds,
    # API timeout, model missing) all return [] silently — pipeline never
    # blocks on this. Validate A first; flip flag only after noir Imagen
    # output has been confirmed visually.
    if os.environ.get("ENABLE_KLING") == "1":
        print("  [Visual] ENABLE_KLING=1 — generating Kling motion clips...")
        try:
            from kling_generator import generate_kling_longform_clips
            key_hints = []
            for sec in script_sections:
                if sec.get("name") in KEY_SECTION_NAMES:
                    hints = sec.get("visual_hints", []) or []
                    if hints:
                        key_hints.append(hints[0])
            kling_clips = generate_kling_longform_clips(key_hints, output_dir, max_clips=3)
            results["kling_clips"] = kling_clips
            results["wiki_clips"].extend(kling_clips)
            print(f"  [Visual] Kling: {len(kling_clips)} motion clips added")
        except Exception as e:
            print(f"  [Visual] Kling generation failed (non-fatal): {e}")
            results["kling_clips"] = []
    else:
        results["kling_clips"] = []

    wiki_count = len(results["wiki_clips"])
    pexels_count = len(os.listdir(results["pexels_clips_dir"])) if os.path.exists(results["pexels_clips_dir"]) else 0
    card_count = len(results["info_cards"])
    map_count = sum(1 for v in results["maps"].values() if v)
    print(f"  [Visual] Complete: {wiki_count} wiki/pixabay, {pexels_count} Pexels, "
          f"{card_count} info cards, {map_count} maps, {len(imagen_clips)} Imagen")

    return results


def _fetch_pixabay_images(case_data: dict, output_dir: str, count: int = 15) -> list[str]:
    """
    Fetch still images from Pixabay as backup when Wikimedia is rate-limited.
    Converts to Ken Burns video clips.
    """
    try:
        from config import PIXABAY_API_KEY
    except ImportError:
        return []
    if not PIXABAY_API_KEY:
        return []

    import requests
    import numpy as np
    from PIL import Image
    from io import BytesIO

    queries = case_data.get("search_keywords_en", [])[:5]
    # Add Asia-specific queries
    country = case_data.get("country", "")
    city = case_data.get("city", "")
    if country:
        queries.append(f"{city} {country} city")
    queries.extend(["crime scene dark", "police asia", "court justice"])

    clips_dir = os.path.join(output_dir, "wiki_clips")
    os.makedirs(clips_dir, exist_ok=True)

    clips = []
    existing = len([f for f in os.listdir(clips_dir) if f.endswith(".mp4")])

    for qi, query in enumerate(queries):
        if len(clips) >= count:
            break
        try:
            resp = requests.get("https://pixabay.com/api/", params={
                "key": PIXABAY_API_KEY,
                "q": query,
                "image_type": "photo",
                "per_page": 5,
                "safesearch": "true",
                "orientation": "horizontal",
            }, timeout=15)
            if resp.status_code != 200:
                continue

            hits = resp.json().get("hits", [])
            for hit in hits[:3]:
                if len(clips) >= count:
                    break
                img_url = hit.get("webformatURL", "")
                if not img_url:
                    continue
                try:
                    img_resp = requests.get(img_url, timeout=15)
                    img = Image.open(BytesIO(img_resp.content)).convert("RGB")
                    img_arr = np.array(img)

                    # Use Ken Burns from wiki_footage
                    from wiki_footage import _make_ken_burns_clip
                    idx = existing + len(clips)
                    clip_path = os.path.join(clips_dir, f"pixabay_{idx:02d}.mp4")
                    clip = _make_ken_burns_clip(img_arr, duration=4.0)
                    clip.write_videofile(clip_path, fps=25, codec="libx264",
                                        audio=False, logger=None)
                    clip.close()
                    clips.append(clip_path)
                    time.sleep(0.5)
                except Exception:
                    continue
        except Exception:
            continue

    print(f"  [Visual] Pixabay backup: {len(clips)} images converted to clips")
    return clips
