"""30-min prototype: generate sprite candidates via Imagen for evaluation.

Generates 4 candidates each for Brick Phone + Glass Slab using imagen-4.0-fast
($0.02/img × 8 = $0.16 total). Saves to pixel_battle/assets/sprite_proto/.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUT_DIR = ROOT / "pixel_battle" / "assets" / "sprite_proto"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "imagen-4.0-fast-generate-001"

# 4 prompt variations per character to see range
BRICK_PROMPTS = [
    "Front view pixel art character sprite of a chunky vintage Nokia 3310 brick phone with a stocky body, "
    "small stubby arms with clenched fists, two short legs, a single green LCD rectangle as its face with "
    "simple pixelated angry eyes, antenna on top, ready-to-fight stance, "
    "16-bit fighting game pixel art style, isolated on solid dark navy background, "
    "clear silhouette, no gradients, no shadows, 64x96 pixel resolution scaled up, retro arcade aesthetic.",

    "16-bit pixel art sprite of an anthropomorphic 90s gray brick cellphone, square chunky body, "
    "two muscular pixel arms, two stubby legs, big rectangular green screen with two pixel eyes as face, "
    "antenna sticking up, T-pose battle stance, vibrant retro color palette, "
    "clear black outline around character, isolated on dark purple background, no extra props, no text.",

    "Pixel art fighting game character: a vintage gray Nokia-style phone with stubby arms and legs, "
    "green LCD screen showing an angry expression, antenna, retro 16-bit arcade sprite aesthetic, "
    "dark gradient background, character centered and isolated, no text, no UI elements.",

    "Cute chibi pixel art sprite of a retro brick mobile phone character, gray body, big square screen face, "
    "small arms holding up in a fighting pose, two tiny feet, expressive cartoon eyes on screen, "
    "16-bit Stardew-Valley style pixel art, clean black outline, isolated on dark blue background.",
]

GLASS_PROMPTS = [
    "Front view pixel art character sprite of a sleek modern smartphone with a tall slim body, "
    "thin pixel arms with sharp gestures, two slim legs, a vibrant blue rectangular touchscreen as its face "
    "displaying simple pixelated eyes, ready-to-fight stance, "
    "16-bit fighting game pixel art style, isolated on solid dark gray background, "
    "white and silver color palette with blue accent, clear silhouette, retro arcade aesthetic.",

    "16-bit pixel art sprite of an anthropomorphic modern iPhone-style glass slab phone, tall rectangular body, "
    "white and silver bezels, glowing blue rectangular screen as face with cyan pixel eyes, "
    "two slim arms in martial-arts stance, two thin legs, futuristic clean look, "
    "clear black outline around character, isolated on dark purple background, no text, no UI.",

    "Pixel art fighting game character: a thin modern glass smartphone with arms and legs, "
    "bright cyan screen face with confident expression, white plastic frame with rounded corners, "
    "retro 16-bit arcade sprite aesthetic, dark gradient background, character centered and isolated.",

    "Cute chibi pixel art sprite of a modern slab smartphone character, white slim body, "
    "tall blue glowing screen face, small arms in fighting pose, two tiny feet, "
    "cute expressive cartoon eyes on screen, 16-bit Stardew-Valley style pixel art, "
    "clean black outline, isolated on dark teal background.",
]


def gen(client, prompt: str, out_path: Path) -> bool:
    try:
        result = client.models.generate_images(
            model=MODEL,
            prompt=prompt,
            config={"number_of_images": 1, "aspect_ratio": "9:16"},
        )
        imgs = getattr(result, "generated_images", None) or []
        if not imgs:
            print(f"  [skip] no image returned for {out_path.name}")
            return False
        imgs[0].image.save(str(out_path))
        size = out_path.stat().st_size
        if size < 10_000:
            print(f"  [skip] {out_path.name} too small ({size} bytes)")
            return False
        print(f"  [ok]   {out_path.name} ({size//1024} KB)")
        return True
    except Exception as e:
        print(f"  [fail] {out_path.name}: {str(e)[:120]}")
        return False


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set (check .env)")
        sys.exit(1)
    client = genai.Client(api_key=api_key)

    print(f"Generating to {OUT_DIR}\n")

    print("=== Brick Phone candidates ===")
    for i, p in enumerate(BRICK_PROMPTS, 1):
        out = OUT_DIR / f"brick_phone_{i}.png"
        gen(client, p, out)

    print("\n=== Glass Slab candidates ===")
    for i, p in enumerate(GLASS_PROMPTS, 1):
        out = OUT_DIR / f"glass_slab_{i}.png"
        gen(client, p, out)

    print(f"\nDone. Cost: ~$0.16 (8 images × $0.02)")
    print(f"Open all: open {OUT_DIR}")


if __name__ == "__main__":
    main()
