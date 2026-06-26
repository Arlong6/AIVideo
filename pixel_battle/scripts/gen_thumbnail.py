"""Generate a VS cover/thumbnail for a fight short.

Rather than re-draw the stick figures in PIL (which never matches the game's
look), we pull the most VISUALLY ENERGETIC frame from the rendered fight and
composite the matchup billboard over it — so the cover is a real hero shot.

Output: a 1080x1920 cover (TikTok cover / YT Shorts thumbnail). Optionally a
1280x720 (center-cropped) for any 16:9 reposting.

Usage:
  python -m pixel_battle.scripts.gen_thumbnail VIDEO LEFT_ID RIGHT_ID OUT_COVER [--wide OUT_169]
"""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
CHARS = json.loads((ROOT / "data" / "characters.json").read_text())
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"   # Latin + CJK, no emoji glyphs
W, H = 1080, 1920


def _font(sz):
    return ImageFont.truetype(FONT, sz)


def _disp(cid):
    return str(CHARS.get(cid, {}).get("display_name", cid)).upper()


def _brand(cid):
    c = CHARS.get(cid, {}).get("brand_color", [255, 255, 255])
    return tuple(int(x) for x in c)


def _ult_name(cid):
    for s in CHARS.get(cid, {}).get("skills", []):
        if s.get("type") == "ultimate":
            return s["id"].replace("_", " ").upper()
    return ""


def _probe_dur(p):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout.strip()
    return float(out)


def _pick_hero_frame(video, tmp):
    """Sample candidate frames across the action window and keep the one with the
    highest luminance stddev (a cheap proxy for contrast / VFX / action)."""
    dur = _probe_dur(video)
    best, best_score = None, -1.0
    for frac in (0.32, 0.42, 0.52, 0.62, 0.72, 0.82):
        t = dur * frac
        fp = tmp / f"cand_{int(frac*100)}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video),
             "-frames:v", "1", str(fp)],
            capture_output=True, text=True)
        if not fp.exists():
            continue
        im = Image.open(fp).convert("RGB")
        # score = luminance stddev (contrast/energy) + a bonus for bright VFX px
        gray = im.convert("L")
        std = ImageStat.Stat(gray).stddev[0]
        hist = gray.histogram()
        bright = sum(hist[210:]) / (gray.width * gray.height)   # fraction of hot px
        score = std + bright * 120.0
        if score > best_score:
            best, best_score = fp, score
    return best


def _fit_cover(im):
    """Scale/crop a frame to exactly WxH (cover)."""
    im = im.convert("RGB")
    s = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    return im.crop((x, y, x + W, y + H))


def _grad_band(draw, y0, y1, top_alpha, bot_alpha):
    """Vertical alpha gradient dark band for text legibility."""
    for y in range(y0, y1):
        f = (y - y0) / max(1, (y1 - y0))
        a = int(top_alpha + (bot_alpha - top_alpha) * f)
        draw.line([(0, y), (W, y)], fill=(0, 0, 0, a))


def _text(draw, cx, cy, s, font, fill, anchor="mm", sw=8, stroke=(0, 0, 0)):
    draw.text((cx, cy), s, font=font, fill=fill, anchor=anchor,
              stroke_width=sw, stroke_fill=stroke)


def _fit_font(s, max_w, start=96, lo=40):
    """Largest font (<=start) whose rendered width fits max_w — so long names
    like JUGGERNAUT shrink instead of colliding with the centered VS."""
    sz = start
    while sz > lo:
        if _font(sz).getlength(s) <= max_w:
            return _font(sz)
        sz -= 4
    return _font(lo)


def build_cover(video, left, right, out_cover, wide=None):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        hero = _pick_hero_frame(video, tmp)
        if hero is None:
            raise SystemExit("no frame extracted")
        base = _fit_cover(Image.open(hero))

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    # darken top + bottom for the billboard text
    _grad_band(d, 0, 430, 200, 0)
    _grad_band(d, 1500, H, 0, 225)

    ld, rd = _disp(left), _disp(right)
    lc, rc = _brand(left), _brand(right)
    ult = _ult_name(left)
    GOLD = (255, 224, 70)

    # Top hook
    _text(d, W // 2, 150, "誰會贏?", _font(150), GOLD, sw=10)
    # Bottom billboard: LEFT name | VS | RIGHT name — each name auto-fits its own
    # 425px column so the centered VS never collides with a long codename.
    lf = _fit_font(ld, 425)
    rf = _fit_font(rd, 425)
    _text(d, 55, 1665, ld, lf, lc, anchor="lm", sw=8)
    _text(d, W - 55, 1665, rd, rf, rc, anchor="rm", sw=8)
    _text(d, W // 2, 1665, "VS", _font(88), GOLD, sw=8)
    if ult:
        _text(d, W // 2, 1810, ult, _font(56), (245, 245, 245), sw=6)

    out = Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")
    Path(out_cover).parent.mkdir(parents=True, exist_ok=True)
    out.save(out_cover, quality=92)
    print(f"  cover -> {out_cover}")

    if wide:
        # 16:9 center crop of the cover for any non-vertical reposting
        crop_h = int(W * 9 / 16)
        y = (H - crop_h) // 2
        out.crop((0, y, W, y + crop_h)).resize((1280, 720), Image.LANCZOS).save(wide, quality=92)
        print(f"  wide  -> {wide}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("left")
    ap.add_argument("right")
    ap.add_argument("out_cover")
    ap.add_argument("--wide", default=None)
    a = ap.parse_args()
    build_cover(a.video, a.left, a.right, a.out_cover, a.wide)


if __name__ == "__main__":
    main()
