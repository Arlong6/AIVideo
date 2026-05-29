"""Generate cinematic VFX texture assets via fal.ai FLUX (text-to-image).

Key trick: every texture is rendered on a PURE BLACK background so it can be
composited in pygame with BLEND_RGB_ADD — black adds nothing (stays invisible),
the bright energy adds light. No background stripping needed, and it gives the
authentic "glow" look that light effects require.

Output: pixel_battle/assets/vfx/{name}.png  (1024x1024 RGB on black)

Cost: ~$0.025-0.05 per image on flux/dev.

Usage:
    python -m pixel_battle.scripts.gen_vfx_textures
"""
import io
import os
import sys
import urllib.request
from pathlib import Path

import fal_client
from dotenv import load_dotenv
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "pixel_battle" / "assets" / "vfx"

FLUX_MODEL = "fal-ai/flux/dev"

# Each prompt MUST stress: pure black background, glowing, centered, symmetrical.
# Additive compositing depends on the background being true black (0,0,0).
# NOTE: textures are intentionally MONOCHROME WHITE so they can be tinted to any
# character's brand color at composite time (white * tint = tint, dark stays dark).
TEXTURES = {
    "magic_circle": (
        "A glowing arcane magic circle seen from directly above (top-down), "
        "concentric rings with intricate runes and geometric sigils, "
        "bright pure WHITE luminous lines, monochrome white light, radiant glow, "
        "perfectly centered and symmetrical, on a PURE SOLID BLACK background, "
        "no gradient, no color, the circle glows like white neon light, "
        "fantasy game VFX, high contrast, the background is completely black."
    ),
    "light_burst": (
        "A brilliant radial burst of pure WHITE light, intense white central core "
        "with sharp white rays and lens-flare star spikes shooting outward in all "
        "directions, anamorphic flare streaks, energy explosion, monochrome white, "
        "perfectly centered, on a PURE SOLID BLACK background, "
        "the light glows extremely bright white, fantasy game ultimate VFX, "
        "high contrast, the background is completely black."
    ),
    "energy_core": (
        "A glowing sphere of concentrated magical energy, bright WHITE-hot core "
        "fading to soft white at the edges, swirling white plasma "
        "and crackling white energy wisps around it, monochrome white, "
        "perfectly centered and round, on a PURE SOLID BLACK background, "
        "the orb glows intensely white, fantasy game VFX, "
        "high contrast, the background is completely black."
    ),
}


def _http_get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def _force_black_bg(img: Image.Image, floor: int = 18) -> Image.Image:
    """Crush near-black pixels to true black so additive blend stays clean.

    FLUX often renders the 'black' background as very dark grey (~10-15).
    Under BLEND_RGB_ADD that grey would brighten the whole scene like a haze.
    We subtract a floor and clamp so anything below `floor` becomes 0.
    """
    from PIL import ImageMath
    rgb = img.convert("RGB")
    bands = rgb.split()
    out_bands = []
    for b in bands:
        # subtract floor, clamp at 0 (ImageMath handles the clamp via max(0,..))
        out_bands.append(ImageMath.eval("convert(max(a-f,0)*255/(255-f), 'L')",
                                        a=b, f=floor))
    return Image.merge("RGB", out_bands)


def gen_texture(prompt: str, out_path: Path) -> bool:
    try:
        result = fal_client.subscribe(
            FLUX_MODEL,
            arguments={
                "prompt": prompt,
                "image_size": "square_hd",      # 1024x1024
                "num_inference_steps": 30,
                "guidance_scale": 3.5,
                "num_images": 1,
                "enable_safety_checker": False,
                "output_format": "png",
            },
            with_logs=False,
        )
        url = result["images"][0]["url"]
        raw = Image.open(io.BytesIO(_http_get_bytes(url)))
        cleaned = _force_black_bg(raw)
        cleaned.save(out_path)
        return True
    except Exception as e:
        print(f"    error: {str(e)[:200]}")
        return False


def main():
    if not os.getenv("FAL_KEY"):
        print("ERROR: FAL_KEY not set")
        sys.exit(1)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, prompt in TEXTURES.items():
        out_path = OUT_DIR / f"{name}.png"
        print(f"  generating {name}...", end=" ", flush=True)
        if gen_texture(prompt, out_path):
            kb = out_path.stat().st_size // 1024
            print(f"ok ({kb} KB)")
            ok += 1
        else:
            print("FAIL")
    print(f"\nDone: {ok}/{len(TEXTURES)} -> {OUT_DIR}")


if __name__ == "__main__":
    main()
