"""Manual-upload packager — the post-YouTube distribution path (2026-07-06).

Takes a rendered reel's output dir (metadata.json + final mp4) and writes an
`upload_package/` folder next to it:

    upload_package/
      video.mp4            # copy of the final render
      caption_tiktok.txt   # title + hashtags tuned for TikTok
      caption_fb.txt       # Facebook Reels variant (AI disclosure included)
      cover.jpg            # thumbnail if the pipeline produced one

No API uploads by design: the YouTube termination taught us that API mass
upload IS the spam signal. arlong posts these by hand from the phone.

Usage:
    python export_reel.py <output_dir>            # package one render
    python export_reel.py --batch <n>             # produce n reels end-to-end, package each
"""
import json
import os
import shutil
import sys

# Platform policy: both TikTok and FB require realistic AI-generated content
# to be disclosed. We disclose in-caption (belt) on top of the platform's
# own AI toggle arlong sets when posting (suspenders).
AI_DISCLOSURE = "本影片包含 AI 生成的圖像與配音（內容基於公開紀錄查證）"

TIKTOK_TAGS = ["#真實案件", "#懸案", "#台灣", "#犯罪紀實"]
FB_TAGS = ["#真實案件", "#懸案", "#犯罪紀實"]


def _clean_tags(tags: list[str]) -> list[str]:
    return [t for t in tags if t.startswith("#") and len(t) > 2 and t.isprintable()]


def package(output_dir: str) -> str | None:
    meta_path = os.path.join(output_dir, "metadata.json")
    if not os.path.exists(meta_path):
        print(f"[export] no metadata.json in {output_dir}")
        return None
    meta = json.load(open(meta_path, encoding="utf-8"))
    zh = meta.get("zh", meta)

    video = None
    for name in ("final_zh.mp4", "final.mp4"):
        p = os.path.join(output_dir, name)
        if os.path.exists(p):
            video = p
            break
    if not video:
        print(f"[export] no final video in {output_dir}")
        return None

    pkg = os.path.join(output_dir, "upload_package")
    os.makedirs(pkg, exist_ok=True)
    shutil.copy(video, os.path.join(pkg, "video.mp4"))

    title = (zh.get("title") or "").strip()
    hook = (zh.get("opening_card") or "").strip()
    desc = (zh.get("description") or "").strip().split("\n")[0]

    script_tags = _clean_tags(zh.get("hashtags") or [])

    # TikTok: title line + short hook, tags inline (TikTok caption limit is
    # generous but discovery is tag+first-line driven).
    tiktok = "\n".join(filter(None, [
        title,
        hook if hook != title else "",
        " ".join(dict.fromkeys(script_tags + TIKTOK_TAGS)),
        AI_DISCLOSURE,
    ]))
    open(os.path.join(pkg, "caption_tiktok.txt"), "w", encoding="utf-8").write(tiktok)

    # FB Reels: fuller first paragraph (FB surfaces more text), fewer tags.
    fb = "\n\n".join(filter(None, [
        f"{title}\n{desc}" if desc else title,
        " ".join(dict.fromkeys(script_tags[:3] + FB_TAGS)),
        AI_DISCLOSURE,
    ]))
    open(os.path.join(pkg, "caption_fb.txt"), "w", encoding="utf-8").write(fb)

    for thumb in ("thumbnail.jpg", "thumbnail_pil.jpg"):
        tp = os.path.join(output_dir, thumb)
        if os.path.exists(tp):
            shutil.copy(tp, os.path.join(pkg, "cover.jpg"))
            break

    print(f"[export] package ready: {pkg}")
    return pkg


def main():
    if len(sys.argv) >= 2 and sys.argv[1] != "--batch":
        package(sys.argv[1])
        return
    print("Usage: python export_reel.py <output_dir>")
    sys.exit(1)


if __name__ == "__main__":
    main()
