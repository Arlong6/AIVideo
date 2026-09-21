"""Draw the meme overlay stickers as 1080x1920 transparent PNGs.

Drawn, not downloaded. The recognisable part of a meme impact is the TIMING and
the convention — a jagged comic burst on a big hit, a flat caption on a whiff —
not any particular file. Drawing them keeps the channel clear of the rights
problems that circulating meme assets carry (the well-known "vine boom" rip and
the usual "bruh" clip are both routinely claimed), and it means the type matches
the covers instead of looking bolted on.

Each sticker is full-frame with its position baked in, which is the same idiom
build_short already uses for the hook and winner bands: ffmpeg composites them
with `overlay=0:0:enable='between(t,a,b)'` and never has to compute a position.

Three scales per sticker give a snap-in pop without ffmpeg's zoompan — the
compositor shows 0.72, then 1.12, then 1.0 for a couple of frames each.

Usage:
  python3 pixel_battle/scripts/gen_meme_stickers.py [OUT_DIR]
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "pixel_battle/assets/meme"
W, H = 1080, 1920

FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
GOLD = (255, 230, 70)
HOT = (255, 90, 80)
WHITE = (255, 255, 255)

SCALES = (0.72, 1.12, 1.0)


def _font(size: int):
    return ImageFont.truetype(FONT, size)


def _burst(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int,
           fill: tuple, spikes: int = 12, jag: float = 0.55) -> None:
    """Comic starburst: alternating long and short radii around a circle."""
    pts = []
    for i in range(spikes * 2):
        ang = (i / (spikes * 2)) * 2 * math.pi - math.pi / 2
        rad = r if i % 2 == 0 else r * jag
        pts.append((cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    d.polygon(pts, fill=fill)


def _stroked(d: ImageDraw.ImageDraw, cx: int, cy: int, text: str,
             font, fill: tuple, stroke: int = 10) -> None:
    box = d.textbbox((0, 0), text, font=font)
    d.text((cx - (box[2] - box[0]) / 2 - box[0], cy - (box[3] - box[1]) / 2 - box[1]),
           text, font=font, fill=fill, stroke_width=stroke, stroke_fill=(0, 0, 0))


def make_pow() -> Image.Image:
    """Big hit. Comic burst with the impact word, sitting over the fighters."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, int(H * 0.52)
    _burst(d, cx, cy, 330, (255, 255, 255, 235), spikes=14, jag=0.52)
    _burst(d, cx, cy, 290, GOLD + (255,), spikes=14, jag=0.55)
    _burst(d, cx, cy, 225, HOT + (255,), spikes=14, jag=0.58)
    _stroked(d, cx, cy, "POW!", _font(190), WHITE, stroke=12)
    return img


def make_boom() -> Image.Image:
    """The finisher landing. Bigger, hotter, and it owns the frame."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = W // 2, int(H * 0.48)
    _burst(d, cx, cy, 470, (255, 255, 255, 240), spikes=16, jag=0.5)
    _burst(d, cx, cy, 410, GOLD + (255,), spikes=16, jag=0.52)
    _burst(d, cx, cy, 320, HOT + (255,), spikes=16, jag=0.55)
    _stroked(d, cx, cy, "BOOM", _font(230), WHITE, stroke=14)
    return img


def make_bruh() -> Image.Image:
    """A whiff. Flat caption, deliberately plain — the joke is the deadpan."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cy = int(H * 0.30)
    d.rounded_rectangle([W // 2 - 300, cy - 110, W // 2 + 300, cy + 110],
                        radius=28, fill=(0, 0, 0, 205))
    _stroked(d, W // 2, cy, "bruh", _font(150), WHITE, stroke=8)
    return img


def make_final() -> Image.Image:
    """Pre-ultimate band. Pairs with the music dropping out underneath it."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 190], fill=(0, 0, 0, 225))
    d.rectangle([0, H - 190, W, H], fill=(0, 0, 0, 225))
    _stroked(d, W // 2, int(H * 0.33), "FINAL BLOW", _font(140), GOLD, stroke=11)
    return img


MAKERS = {"pow": make_pow, "boom": make_boom, "bruh": make_bruh, "final": make_final}


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT
    out.mkdir(parents=True, exist_ok=True)
    for name, make in MAKERS.items():
        base = make()
        for s in SCALES:
            if s == 1.0:
                img = base
            else:
                # Scale about the canvas centre so the pop grows in place.
                sw, sh = int(W * s), int(H * s)
                img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                img.paste(base.resize((sw, sh), Image.LANCZOS),
                          ((W - sw) // 2, (H - sh) // 2))
            p = out / f"{name}_{int(s * 100)}.png"
            img.save(p)
        print(f"  {name}: {len(SCALES)} scales")
    print(f"wrote {len(MAKERS) * len(SCALES)} stickers to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
