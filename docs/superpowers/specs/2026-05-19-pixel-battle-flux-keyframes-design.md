# Pixel Battle — FLUX Kontext Keyframe Generator

**Date**: 2026-05-19
**Status**: Approved
**Trigger**: Current `gen_keyframes.py` uses Gemini 2.5 Flash i2i (`gemini-2.5-flash-image`). Quality issues: "pixel" output is a filter-feel rather than a true pixel grid; character consistency between poses is unstable; slow (~30s/image). FLUX.1 Kontext (Black Forest Labs, hosted on fal.ai) offers reference-image-anchored generation with much tighter identity preservation at 3-5s/image.

## Goal

Replace the Gemini i2i keyframe pipeline with FLUX.1 Kontext on fal.ai, add a pixel-art LoRA, and harden the pixel aesthetic with Pillow post-processing.

Three pieces:
1. **Engine swap**: `google.genai` → `fal-client`. Same i2i flow (reference image + edit prompt), better identity preservation.
2. **Pixel aesthetic**: load `nerijs/pixel-art-xl` LoRA via fal.ai's FLUX LoRA endpoint; post-process every output with `Image.quantize(colors=16)` + `Image.resize(NEAREST, ×4)` so the output is a real pixel grid.
3. **Pose expansion**: add `jump_up`, `jump_apex`, `jump_land` to the 8 existing poses → 11 total.

## Three blocks

### A. Migrate `gen_keyframes.py` from Gemini to FLUX Kontext

**A1. New dependency + env var**

- `pip install fal-client Pillow numpy` (Pillow + numpy already in tree; only `fal-client` is new)
- New env var: `FAL_KEY` (loaded via existing `python-dotenv` flow)
- Remove `google.genai` import; keep `dotenv` and `PIL.Image`

**A2. New API call wrapper**

Replace `gen_pose(client, base_image, instruction, out_path)`:

```python
import base64, io, fal_client

KONTEXT_MODEL = "fal-ai/flux-pro/kontext"

def gen_pose_flux(base_image: Image.Image, instruction: str, out_path: Path) -> bool:
    """One Kontext i2i call. Returns True on success, writes PNG to out_path."""
    # Encode reference image as data URI
    buf = io.BytesIO()
    base_image.save(buf, format="PNG")
    img_data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    try:
        result = fal_client.subscribe(
            KONTEXT_MODEL,
            arguments={
                "image_url": img_data_uri,
                "prompt": instruction,
                # Encourage retro pixel aesthetic via Kontext's default; LoRA layered separately if available
                "guidance_scale": 3.5,
                "num_inference_steps": 28,
                "aspect_ratio": "1:1",
                "output_format": "png",
            },
            with_logs=False,
        )
        # Result schema: {"images": [{"url": "..."}]}
        img_url = result["images"][0]["url"]
        img_bytes = fal_client.download_file(img_url) if hasattr(fal_client, "download_file") \
                     else _http_get_bytes(img_url)
        # Decode and post-process for pixel aesthetic
        raw_img = Image.open(io.BytesIO(img_bytes))
        pixel_img = pixel_art_finalize(raw_img, palette_colors=16, target_px=512)
        pixel_img.save(out_path)
        return True
    except Exception as e:
        print(f"    error: {str(e)[:200]}")
        return False
```

`_http_get_bytes(url)` is a simple `urllib.request.urlopen(url).read()` fallback if `fal_client.download_file` is unavailable in the installed version.

**A3. Pillow pixel-art finalizer**

```python
from PIL import Image

def pixel_art_finalize(img: Image.Image, palette_colors: int = 16,
                       target_px: int = 512) -> Image.Image:
    """Force a real pixel grid: downsample → quantize → NEAREST upscale.

    Steps:
      1. Downsample to 128x128 (LANCZOS for clean detail)
      2. Quantize to palette_colors (Pillow MEDIANCUT)
      3. NEAREST upscale back to target_px so each "pixel" is a 4x4 block
    """
    grid = 128
    small = img.convert("RGB").resize((grid, grid), Image.LANCZOS)
    quant = small.quantize(colors=palette_colors, method=Image.MEDIANCUT, dither=Image.NONE)
    return quant.convert("RGB").resize((target_px, target_px), Image.NEAREST)
```

### B. Expand POSES from 8 to 11

Insert three jump poses while keeping the existing 8 unchanged:

```python
POSES = {
    "attack_windup":  "... (unchanged)",
    "attack_strike":  "... (unchanged)",
    "attack_recover": "... (unchanged)",
    "hit_recoil":     "... (unchanged)",
    "ko_falling":     "... (unchanged)",
    "ko_landed":      "... (unchanged)",
    "special_charge": "... (unchanged)",
    "ultimate_pose":  "... (unchanged)",

    "jump_up": "Modify the image to show the same character beginning a jump: "
               "knees bent into a coiled crouch, arms swinging downward in preparation, "
               "weight loaded on both feet, eyes upward. " + PRESERVE,

    "jump_apex": "Modify the image to show the same character at the peak of a jump in mid-air: "
                 "both feet tucked up toward the chest, arms slightly raised, "
                 "body compact and vertical, expression focused. " + PRESERVE,

    "jump_land": "Modify the image to show the same character landing from a jump: "
                 "knees bent in deep cushion, one arm out for balance, "
                 "body lowered close to the ground, dust particle hint at feet. " + PRESERVE,
}
```

### C. Update main loop for new engine

`main()` body changes:
- API key check: `os.getenv("FAL_KEY")` instead of `GEMINI_API_KEY`
- Drop `client = genai.Client(...)` — fal-client uses env var directly
- Call `gen_pose_flux(base_img, instr, out_path)` instead of `gen_pose(client, ...)`
- Cost line: `~${total_ok * 0.05:.2f}` (FLUX Kontext pro tier)

Per-character output unchanged: `pixel_battle/assets/sprites/{char_id}/{pose}.png`. `idle.png` copied from base sprite as before.

## Architecture

One file rewrite, no module structure change:
- `pixel_battle/scripts/gen_keyframes.py` — full rewrite

New runtime dependency:
- `fal-client` Python SDK (add to project's `requirements.txt` or note in script docstring if no formal requirements file)

Test script (smoke) — covered separately under Testing.

## Error handling

- Missing `FAL_KEY` → clear stderr message + exit code 1 (mirrors current behavior)
- fal.ai API error → caught in `gen_pose_flux`, prints first 200 chars, returns False, summary tracks fail count
- LoRA endpoint unavailable / unsupported parameter → fall back to no-LoRA call (let prompt + Kontext + Pillow do the heavy lifting); log to stderr once
- Pillow quantize error (rare, e.g., color mode mismatch) → catch in `pixel_art_finalize`, log, return raw image as fallback
- Network timeout: `fal-client.subscribe` already polls with backoff internally

## Testing

### Smoke test (new)

- `tests/test_gen_keyframes_smoke.py`:
  - Skip if `FAL_KEY` not set (env-gated; CI-friendly)
  - `pixel_art_finalize` round-trip: takes a random 1024x1024 noise image, returns a 512x512 image with ≤ 16 unique colors
  - `POSES` dict contains exactly 11 entries with the expected keys
  - `KONTEXT_MODEL` constant points to `fal-ai/flux-pro/kontext`

### Manual verification

After running `python -m pixel_battle.scripts.gen_keyframes`:
- 2 chars × 11 poses = 22 PNGs in `assets/sprites/{char_id}/`
- Each is 512×512 (or whatever `target_px` was set) with crisp pixel grid (zoom in: rectangular blocks, no anti-aliased smudges)
- Same character identity preserved across all 11 poses per char (subjective: brick_phone reads as the same blocky phone in idle / windup / jump_apex / ko_landed)
- Total cost ≈ $1.10

## Implementation order

1. **A3 `pixel_art_finalize`** — pure Pillow function (TDD)
2. **B POSES expansion** — add 3 jump entries (mechanical)
3. **A1+A2 FLUX wrapper** — rewrite gen_pose, env var check (mocked fal_client in unit test for smoke)
4. **C main loop swap** — wire to new engine
5. **Smoke run** — execute against live fal.ai; spot-check 22 outputs

## Out of scope

- LoRA tuning beyond loading `nerijs/pixel-art-xl` (single LoRA, no weight tweak)
- Multi-shot consistency tooling (PuLID / InstantID) — not pixel-art aligned
- ControlNet pose conditioning — Kontext's text-edit pose works fine for this set
- Sprite sheet packing (separate concern, not in this scope)
- Backwards compat with Gemini — direct replacement per user direction

## Tuning knobs

- `KONTEXT_MODEL = "fal-ai/flux-pro/kontext"`
- `guidance_scale = 3.5` (Kontext sweet spot per BFL docs)
- `num_inference_steps = 28`
- `pixel_art_finalize`: 128px grid, 16-color palette, 512px target
- LoRA: `nerijs/pixel-art-xl` (load via fal.ai LoRA endpoint OR plain Kontext if LoRA layering rejected — fallback path documented)
