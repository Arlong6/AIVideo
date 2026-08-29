"""Format a raw scripted-fight render into a platform-ready vertical short.

Pipeline per video:
  1. PIL renders two transparent 1080x1920 overlay PNGs (no emoji — the CJK font
     has no emoji glyphs, they'd tofu): a front-loaded HOOK (誰會贏? + matchup)
     and a WINNER banner revealed over the KO aftermath.
  2. ffmpeg cuts off the spawn intro (raw is already native 1080x1920),
     and composites both overlays with time-gated enable exprs.

Usage:
  python -m pixel_battle.scripts.build_short RAW OUT "L1" "L2" "WINTEXT" CUT_START
"""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
HOOK_SECS = 2.8          # hook visible for the first N seconds
WIN_TAIL = 4.2           # winner banner covers the last N seconds (the KO drama)


def _font(size):
    return ImageFont.truetype(FONT, size)


def _centered(draw, cy, text, font, fill, stroke=(0, 0, 0), sw=6):
    bb = draw.textbbox((0, 0), text, font=font, stroke_width=sw)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    draw.text(((W - w) / 2 - bb[0], cy - h / 2 - bb[1]), text, font=font,
              fill=fill, stroke_width=sw, stroke_fill=stroke)


def make_hook(path, l1, l2):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # translucent band behind the hook text for legibility over the fight
    d.rectangle([0, 250, W, 560], fill=(0, 0, 0, 110))
    _centered(d, 360, l1, _font(150), (255, 230, 70))      # 誰會贏? — gold
    _centered(d, 500, l2, _font(72), (255, 255, 255))      # matchup
    img.save(path)


def make_winner(path, text):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 1340, W, 1560], fill=(0, 0, 0, 120))
    _centered(d, 1450, text, _font(118), (255, 90, 80))    # WINNER — red impact
    img.save(path)


def probe_dur(p):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    return float(out)


def main():
    raw, out, l1, l2, wintext, cut_start = (
        sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5],
        float(sys.argv[6]))
    tmp = Path("/tmp/short_ov")
    tmp.mkdir(exist_ok=True)
    hook_p, win_p = str(tmp / "hook.png"), str(tmp / "win.png")
    make_hook(hook_p, l1, l2)
    make_winner(win_p, wintext)

    cut_dur = probe_dur(raw) - cut_start
    win_start = max(0.0, cut_dur - WIN_TAIL)

    # Does the raw carry an audio track? (Scripted renders now mux BGM+SFX in.)
    has_audio = bool(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", raw],
        capture_output=True, text=True).stdout.strip())

    # Polish chain: deband the gradient skies, whisper of film grain so flat
    # fills feel produced — all BEFORE the text overlays so the hook/winner
    # typography stays pristine. Then hook + winner band.
    fc = (
        f"[0:v]trim={cut_start},setpts=PTS-STARTPTS,"
        f"gradfun=1.2:16,"
        f"noise=alls=2:allf=t[v];"
        f"[v][1:v]overlay=0:0:enable='lt(t,{HOOK_SECS})'[v1];"
        f"[v1][2:v]overlay=0:0:enable='gte(t,{win_start})'[vo]"
    )
    cmd = ["ffmpeg", "-y", "-i", raw, "-i", hook_p, "-i", win_p]
    if has_audio:
        # Trim the audio in lock-step with the video so SFX stay synced.
        fc += f";[0:a]atrim={cut_start},asetpts=PTS-STARTPTS[a]"
        cmd += ["-filter_complex", fc, "-map", "[vo]", "-map", "[a]",
                "-c:a", "aac", "-b:a", "192k"]
    else:
        cmd += ["-filter_complex", fc, "-map", "[vo]"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-profile:v", "high", "-preset", "slow", "-crf", "18", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1500:]); sys.exit(1)
    print(f"  short -> {out}  ({probe_dur(out):.1f}s)")


if __name__ == "__main__":
    main()
