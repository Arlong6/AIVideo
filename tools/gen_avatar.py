"""Draw the channel avatar: bold VS mark over two stick-figure silhouettes.

Why not crop a video frame: TikTok shows the avatar as a circle at roughly 50px
in feed. A cropped fight frame turns to mush at that size and the circle clips
whichever fighter sits near the edge. An avatar needs one bold shape that
survives the downscale, so this draws a purpose-built mark using the cover's own
gold and typeface, keeping it visually part of the same family.

Writes a 1080x1080 PNG. TikTok applies the circular mask itself, so everything
important stays well inside the inscribed circle.

Usage:
  python3 tools/gen_avatar.py [out.png]
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"      # same face as the covers
GOLD = (255, 224, 70)
INK = (12, 15, 26)
BG_TOP = (44, 52, 82)
BG_BOT = (16, 19, 32)
S = 1080


def _figure(d: ImageDraw.ImageDraw, cx: int, cy: int, h: int, color, head: str,
            face: int) -> None:
    """A minimal stick figure: head, spine, two arms, two legs.

    Deliberately chunkier than the in-game renderer — thin limbs vanish once the
    image is scaled to avatar size.
    """
    lw = max(6, h // 13)
    head_r = h // 5
    hy = cy - h // 2 + head_r
    if head == "diamond":
        d.polygon([(cx, hy - head_r), (cx + head_r, hy),
                   (cx, hy + head_r), (cx - head_r, hy)], fill=color)
    else:
        d.rectangle([cx - head_r, hy - head_r, cx + head_r, hy + head_r], fill=color)

    sy = hy + head_r                      # shoulders
    hipy = cy + h // 6
    d.line([(cx, sy), (cx, hipy)], fill=color, width=lw)
    # lead arm reaches toward the opponent, rear arm guards
    d.line([(cx, sy + lw), (cx + face * h // 3, sy + h // 12)], fill=color, width=lw)
    d.line([(cx, sy + lw), (cx - face * h // 7, sy + h // 5)], fill=color, width=lw)
    foot = cy + h // 2
    d.line([(cx, hipy), (cx + face * h // 5, foot)], fill=color, width=lw)
    d.line([(cx, hipy), (cx - face * h // 6, foot)], fill=color, width=lw)


def build(out: Path) -> None:
    img = Image.new("RGB", (S, S), BG_BOT)
    d = ImageDraw.Draw(img)
    for y in range(S):                    # vertical gradient, same mood as the arenas
        t = y / S
        d.line([(0, y), (S, y)],
               fill=tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)))

    # Figures sit low and outboard so the VS owns the middle. An earlier pass put
    # them at mid-height and the VS was sandwiched between two heads — legible at
    # 300px, mush at the 50px the feed actually renders.
    fh = int(S * 0.34)
    _figure(d, int(S * 0.235), int(S * 0.70), fh, GOLD, "diamond", face=1)
    _figure(d, int(S * 0.765), int(S * 0.70), fh, (236, 64, 72), "square", face=-1)

    # VS is the one element that must survive the downscale: large, centred, with
    # an ink halo so it never fights the background gradient.
    f = ImageFont.truetype(FONT, int(S * 0.40))
    txt = "VS"
    box = d.textbbox((0, 0), txt, font=f)
    tx, ty = (S - (box[2] - box[0])) // 2 - box[0], int(S * 0.20) - box[1]
    for dx in range(-9, 10, 3):
        for dy in range(-9, 10, 3):
            d.text((tx + dx, ty + dy), txt, font=f, fill=INK)
    d.text((tx, ty), txt, font=f, fill=GOLD)

    img.save(out)
    print(f"-> {out}")


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        ROOT / "pixel_battle/output/profile/avatar.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
