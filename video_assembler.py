import os
import random
import numpy as np
import srt
# Pillow 10+ removed ANTIALIAS; patch before MoviePy imports it
from PIL import Image as _PIL_Image
if not hasattr(_PIL_Image, 'ANTIALIAS'):
    _PIL_Image.ANTIALIAS = _PIL_Image.LANCZOS
from moviepy.editor import (
    VideoFileClip,
    AudioFileClip,
    concatenate_videoclips,
    CompositeAudioClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_audioclips,
)

TARGET_W, TARGET_H = 1080, 1920  # 9:16 vertical (Shorts default)
TARGET_W_LONG, TARGET_H_LONG = 1920, 1080  # 16:9 landscape (long-form)
CUT_INTERVAL = 4.0               # default seconds per scene cut

# Pacing label → cut duration in seconds
PACING_DURATIONS = {
    "slow": 5.0,
    "medium": 4.0,
    "fast": 2.5,
    "climax": 1.5,
}

# Long-form pacing is slower (more footage per scene)
PACING_DURATIONS_LONG = {
    "slow": 8.0,
    "medium": 5.0,
    "fast": 3.0,
    "climax": 2.0,
}


def _crop_to_target(clip, tw, th):
    """Crop and resize clip to target dimensions (any aspect ratio)."""
    w, h = clip.size
    target_ratio = tw / th
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        x1 = (w - new_w) // 2
        clip = clip.crop(x1=x1, x2=x1 + new_w)
    else:
        new_h = int(w / target_ratio)
        y1 = (h - new_h) // 2
        clip = clip.crop(y1=y1, y2=y1 + new_h)
    return clip.resize((tw, th))


def _crop_to_vertical(clip):
    return _crop_to_target(clip, TARGET_W, TARGET_H)


def _apply_dark_grade(clip):
    """
    Dark true crime color grade:
    - Heavy darkening (0.50) for oppressive atmosphere
    - Cold blue-teal tone (reduce red/green, boost blue)
    - Slight red push in mid-tones for tension/blood feel
    - Vignette: darken edges, focus center — classic film noir
    """
    h, w = TARGET_H, TARGET_W
    # Pre-compute vignette mask (same for every frame — compute once)
    Y, X = np.ogrid[:h, :w]
    dist = np.sqrt(((X - w / 2) / (w / 2)) ** 2 + ((Y - h / 2) / (h / 2)) ** 2)
    vignette = np.clip(1.0 - dist * 0.50, 0.35, 1.0).astype(np.float32)

    def grade(frame):
        f = frame.astype(np.float32)
        # Overall darken — 0.60 keeps it dark but not pitch black
        f *= 0.60
        # Cool blue-teal tone
        f[:, :, 0] *= 0.78                               # pull red down
        f[:, :, 1] *= 0.86                               # pull green down
        f[:, :, 2] = np.minimum(f[:, :, 2] * 1.15, 255) # push blue up
        # Subtle red tension in mid-tones for crime atmosphere
        mid = (f[:, :, 0] > 15) & (f[:, :, 0] < 90)
        f[mid, 0] = np.minimum(f[mid, 0] * 1.20, 255)
        # Vignette (edges at 35% brightness, centre unaffected)
        f *= vignette[:, :, np.newaxis]
        return f.clip(0, 255).astype(np.uint8)

    return clip.fl_image(grade)


def _render_subtitle_frame(txt: str) -> np.ndarray:
    """Render subtitle text as RGBA image. Text is pre-split to fit — no truncation."""
    from PIL import Image, ImageDraw, ImageFont

    FONT_PATH = "/System/Library/Fonts/STHeiti Medium.ttc"
    FONT_SIZE = 46
    CHARS_PER_LINE = 16  # must match MAX_CHARS_PER_CARD // 2 in subtitle_generator

    # Wrap into lines of CHARS_PER_LINE each
    lines = []
    remaining = txt.strip()
    while remaining:
        lines.append(remaining[:CHARS_PER_LINE])
        remaining = remaining[CHARS_PER_LINE:]

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    line_h = FONT_SIZE + 12
    img = Image.new("RGBA", (TARGET_W, line_h * len(lines) + 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (TARGET_W - w) // 2
        y = i * line_h
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 210))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return np.array(img)


def _burn_subtitles_pillow(input_path: str, srt_path: str, output_path: str):
    """Burn subtitles using Pillow. Clamps end times to video duration."""
    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))

    base = VideoFileClip(input_path)
    video_dur = base.duration

    subtitle_clips = []
    for sub in subtitles:
        start = sub.start.total_seconds()
        end = min(sub.end.total_seconds(), video_dur)  # clamp to video length
        if start >= video_dur or end <= start:
            continue
        txt = sub.content.replace("\n", " ").strip()
        if not txt:
            continue

        frame = _render_subtitle_frame(txt)
        sc = (ImageClip(frame, ismask=False)
              .set_start(start)
              .set_end(end)
              .set_position(("center", TARGET_H - 220)))
        subtitle_clips.append(sc)

    final = CompositeVideoClip([base] + subtitle_clips)
    final = final.set_audio(base.audio)  # explicitly preserve audio
    final.write_videofile(output_path, fps=25, codec="libx264", audio_codec="aac", logger=None)
    final.close()
    base.close()


def _burn_subtitles_ffmpeg(input_path: str, srt_path: str, output_path: str):
    """Burn subtitles using ffmpeg ASS filter — works for long videos without OOM."""
    import subprocess

    # Find CJK font
    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((p for p in font_candidates if os.path.exists(p)), "")

    # Use subtitles filter with force_style for white text with black outline
    style = (
        "FontName=Noto Sans CJK TC,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=60"
    )
    if "STHeiti" in font_path:
        style = style.replace("Noto Sans CJK TC", "STHeiti")

    # Escape path for ffmpeg subtitles filter (colons and backslashes)
    srt_escaped = srt_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    vf = f"subtitles='{srt_escaped}':force_style='{style}'"

    result = subprocess.run([
        "ffmpeg", "-y", "-i", input_path,
        "-vf", vf,
        "-c:a", "copy",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        output_path,
    ], capture_output=True, timeout=600)

    if result.returncode != 0:
        err = result.stderr[-500:].decode("utf-8", "ignore")
        print(f"  [WARN] ffmpeg subtitle burn failed: {err}")
        raise RuntimeError("ffmpeg subtitle burn failed")


def _group_clips_by_scene(clip_files: list) -> list[list]:
    """Group clip paths by scene prefix s00_, s01_, ... in story order."""
    import re
    groups: dict[int, list] = {}
    for path in sorted(clip_files, key=lambda p: os.path.basename(p)):
        m = re.match(r's(\d+)_', os.path.basename(path))
        idx = int(m.group(1)) if m else 999
        groups.setdefault(idx, []).append(path)
    return [groups[k] for k in sorted(groups.keys())]


def _build_video_clips(clip_files: list, total_duration: float, temp_dir: str,
                       scene_pacing: list | None = None,
                       fmt: str = "short") -> list[str]:
    """
    Build cut sequence in story order with no within-scene repetition.
    fmt='short': 9:16 vertical + per-frame dark grade (MoviePy)
    fmt='long': 16:9 landscape + skip dark grade (use ffmpeg cinematic effects later)
    """
    scene_groups = _group_clips_by_scene(clip_files)
    if not scene_groups:
        return []

    num_scenes = len(scene_groups)
    tw = TARGET_W_LONG if fmt == "long" else TARGET_W
    th = TARGET_H_LONG if fmt == "long" else TARGET_H
    pacing_table = PACING_DURATIONS_LONG if fmt == "long" else PACING_DURATIONS
    default_interval = 5.0 if fmt == "long" else CUT_INTERVAL

    def _scene_duration(scene_idx: int) -> float:
        if scene_pacing and scene_idx < len(scene_pacing):
            return pacing_table.get(scene_pacing[scene_idx], default_interval)
        return default_interval

    # Pre-compute cut plan
    plan = []
    scene_clip_idx = [0] * num_scenes
    t = 0.0
    cut_index = 0
    total_cuts_estimate = int(total_duration / default_interval) + 1
    while t < total_duration - 0.05:
        si = min(int(cut_index / total_cuts_estimate * num_scenes), num_scenes - 1)
        interval = _scene_duration(si)
        chunk = min(interval, total_duration - t)
        cp = scene_clip_idx[si] % len(scene_groups[si])
        scene_clip_idx[si] += 1
        plan.append((si, cp, chunk))
        t += chunk
        cut_index += 1

    avg_cut = sum(c for _, _, c in plan) / len(plan) if plan else default_interval
    print(f"  {len(scene_groups)} scenes, {sum(len(g) for g in scene_groups)} clips, "
          f"{len(plan)} cuts (avg {avg_cut:.1f}s) — {fmt} mode ({tw}x{th})...")

    os.makedirs(temp_dir, exist_ok=True)
    temp_paths = []
    for i, (si, cp, chunk) in enumerate(plan):
        src_path = scene_groups[si][cp]
        temp_path = os.path.join(temp_dir, f"cut_{i:03d}.mp4")
        try:
            src = VideoFileClip(src_path, audio=False)
            src = _crop_to_target(src, tw, th)
            # Long-form: skip per-frame dark grade (ffmpeg does it later, much faster)
            if fmt == "short":
                src = _apply_dark_grade(src)
            if src.duration >= chunk:
                offset = random.uniform(0, src.duration - chunk)
                sub = src.subclip(offset, offset + chunk)
            else:
                sub = src.subclip(0, src.duration)
            sub.write_videofile(temp_path, fps=25, codec="libx264",
                                audio=False, logger=None)
            src.close()
            temp_paths.append(temp_path)
            if (i + 1) % 10 == 0:
                print(f"    Cut {i+1}/{len(plan)}...")
        except Exception as e:
            print(f"  [WARN] Cut {i}: {e}")

    return temp_paths


def _interleave_wiki_clips(cut_paths: list[str], wiki_clips: list[str]) -> list[str]:
    """
    Insert wiki archive clips at evenly-spaced positions in the cut sequence.
    Wiki clips are placed at ~20%, 40%, 60%, 80% through the timeline
    (and one at the very start if available).
    Wiki clips already have dark grade applied via Ken Burns.
    """
    if not wiki_clips:
        return cut_paths

    n = len(cut_paths)
    # Positions to insert wiki clips (as fractions of total cuts)
    # First wiki clip at position 2 (after opening shots), rest evenly spread
    insert_positions = [2]
    remaining = wiki_clips[1:]
    step = max(1, n // (len(remaining) + 1))
    pos = step
    for _ in remaining:
        insert_positions.append(min(pos, n - 1))
        pos += step

    result = list(cut_paths)
    # Insert in reverse order so earlier indices stay valid
    wiki_iter = list(zip(sorted(insert_positions, reverse=True), reversed(wiki_clips)))
    for insert_at, wiki_path in wiki_iter:
        result.insert(insert_at, wiki_path)

    return result


def _make_opening_card(text: str, output_path: str, duration: float = 2.0,
                       fmt: str = "short"):
    """Generate a title card with large white text using ffmpeg."""
    import subprocess
    tw = TARGET_W_LONG if fmt == "long" else TARGET_W
    th = TARGET_H_LONG if fmt == "long" else TARGET_H

    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((p for p in font_candidates if os.path.exists(p)), "")

    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", (tw, th), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Red top/bottom accent bars
    draw.rectangle([(0, 0), (tw, 8)], fill=(200, 10, 10))
    draw.rectangle([(0, th - 8), (tw, th)], fill=(200, 10, 10))

    # Draw text centered with stroke
    font_size = 96 if len(text) <= 8 else 78
    try:
        font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (tw - text_w) // 2
    y = (th - text_h) // 2

    # Stroke (black outline)
    for ox in range(-5, 6):
        for oy in range(-5, 6):
            if ox != 0 or oy != 0:
                draw.text((x + ox, y + oy), text, font=font, fill=(0, 0, 0))
    # White text
    draw.text((x, y), text, font=font, fill=(255, 248, 220))

    # Save frame and convert to video with ffmpeg
    frame_path = output_path + "_frame.jpg"
    img.save(frame_path, "JPEG", quality=95)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", frame_path,
        "-t", str(duration), "-r", "25",
        "-vf", f"scale={tw}:{th}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        output_path,
    ], capture_output=True, check=True)
    os.remove(frame_path)


def assemble_video(output_dir: str, lang: str = "zh", wiki_clips: list | None = None,
                   scene_pacing: list | None = None, fmt: str = "short") -> str | None:
    clips_dir = os.path.join(output_dir, "clips")
    voiceover_path = os.path.join(output_dir, f"voiceover_{lang}.mp3")
    srt_path = os.path.join(output_dir, f"subtitles_{lang}.srt")
    music_path = os.path.join(output_dir, "background_music.mp3")
    temp_path = os.path.join(output_dir, f"_temp_{lang}.mp4")
    final_path = os.path.join(output_dir, f"final_{lang}.mp4")

    if not os.path.exists(voiceover_path):
        print(f"  [ERROR] Voiceover not found: {voiceover_path}")
        return None

    clip_files = sorted([
        os.path.join(clips_dir, f)
        for f in os.listdir(clips_dir) if f.endswith(".mp4")
    ]) if os.path.exists(clips_dir) else []

    if not clip_files:
        print("  [ERROR] No video clips found in clips/")
        return None

    print("  Loading voiceover...")
    voiceover = AudioFileClip(voiceover_path)
    duration = voiceover.duration
    print(f"  Voiceover duration: {duration:.1f}s")

    temp_cuts_dir = os.path.join(output_dir, "_cuts")
    print(f"  Building scene cuts from {len(clip_files)} clips ({fmt} mode)...")
    cut_paths = _build_video_clips(clip_files, duration, temp_cuts_dir,
                                   scene_pacing=scene_pacing, fmt=fmt)

    if not cut_paths:
        print("  [ERROR] No clips assembled")
        return None

    # Prepend opening title card if available
    meta_path = os.path.join(output_dir, "metadata.json")
    if os.path.exists(meta_path):
        try:
            import json as _json
            meta = _json.load(open(meta_path, encoding="utf-8"))
            zh_meta = meta if "opening_card" in meta else meta.get("zh", {})
            card_text = zh_meta.get("opening_card", "")
            if card_text:
                card_path = os.path.join(output_dir, "_opening_card.mp4")
                print(f"  Making opening card: 「{card_text}」")
                _make_opening_card(card_text, card_path, duration=2.0, fmt=fmt)
                cut_paths = [card_path] + cut_paths
        except Exception as e:
            print(f"  [WARN] Opening card failed: {e}")

    # Interleave Wikimedia archive clips at key story positions
    if wiki_clips:
        cut_paths = _interleave_wiki_clips(cut_paths, wiki_clips)
        print(f"  Inserted {len(wiki_clips)} wiki archive clips")

    # Concatenate cut files via ffmpeg concat demuxer (memory-efficient)
    concat_path = os.path.join(output_dir, "_concat.mp4")
    concat_list = os.path.join(output_dir, "_concat.txt")
    with open(concat_list, "w") as f:
        for p in cut_paths:
            f.write(f"file '{os.path.abspath(p)}'\n")

    print(f"  Concatenating {len(cut_paths)} cuts via ffmpeg...")
    import subprocess
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", concat_path
    ], capture_output=True, check=True)

    # Clean up temp cut files
    import shutil
    shutil.rmtree(temp_cuts_dir, ignore_errors=True)
    os.remove(concat_list)

    # Mix audio + combine with video using ffmpeg only (no MoviePy re-render = no OOM)
    print("  Mixing audio with ffmpeg...")
    if os.path.exists(music_path):
        # Build looped music file first so ffmpeg doesn't need complex filter looping
        music_loop_path = os.path.join(output_dir, "_music_loop.mp3")
        subprocess.run([
            "ffmpeg", "-y",
            "-stream_loop", "-1", "-i", music_path,
            "-t", str(duration),
            "-af", "volume=0.18",
            music_loop_path,
        ], capture_output=True, check=True)
        # Mix voiceover + music, combine with video
        subprocess.run([
            "ffmpeg", "-y",
            "-i", concat_path,
            "-i", voiceover_path,
            "-i", music_loop_path,
            "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-t", str(duration),
            "-c:v", "copy",
            "-c:a", "aac",
            temp_path,
        ], capture_output=True, check=True)
        os.remove(music_loop_path)
    else:
        subprocess.run([
            "ffmpeg", "-y",
            "-i", concat_path,
            "-i", voiceover_path,
            "-map", "0:v", "-map", "1:a",
            "-t", str(duration),
            "-c:v", "copy", "-c:a", "aac",
            temp_path,
        ], capture_output=True, check=True)

    voiceover.close()
    if os.path.exists(concat_path):
        os.remove(concat_path)

    # Burn subtitles
    subtitle_out = final_path.replace("final_", "_sub_")
    if os.path.exists(srt_path):
        print(f"  Adding subtitles ({'ffmpeg' if fmt == 'long' else 'PIL'} mode)...")
        try:
            if fmt == "long":
                _burn_subtitles_ffmpeg(temp_path, srt_path, subtitle_out)
            else:
                _burn_subtitles_pillow(temp_path, srt_path, subtitle_out)
            os.remove(temp_path)
            print("  Subtitles added ✅")
        except Exception as e:
            print(f"  [WARN] Subtitle burn failed: {e}")
            subtitle_out = temp_path
    else:
        subtitle_out = temp_path

    # Apply cinematic effects (grain + vignette + color grade + red bars)
    print("  Applying cinematic effects...")
    effects_ok = _apply_cinematic_effects(subtitle_out, final_path)
    if os.path.exists(subtitle_out) and subtitle_out != final_path:
        os.remove(subtitle_out)
    if not effects_ok:
        if os.path.exists(subtitle_out):
            os.rename(subtitle_out, final_path)

    size_mb = os.path.getsize(final_path) / 1024 / 1024
    print(f"  ✅ Video ready: final_{lang}.mp4 ({size_mb:.1f} MB, {duration:.0f}s)")
    return final_path


def _apply_cinematic_effects(input_path: str, output_path: str) -> bool:
    """
    Post-process final video with:
    - Film grain (noise)
    - Vignette (darken edges)
    - Slight color grade (darker shadows, cooler tone)
    - Red accent bars top/bottom
    - REC indicator (top-left, like CCTV)
    """
    import subprocess

    # Filter chain (no drawtext — not available in all ffmpeg builds)
    vf = ",".join([
        # Grain
        "noise=alls=10:allf=t+u",
        # Vignette
        "vignette=PI/5",
        # Color grade: slightly darker, desaturated (documentary feel)
        "eq=brightness=-0.03:saturation=0.85:contrast=1.05",
        # Red top bar
        "drawbox=x=0:y=0:w=iw:h=6:color=red@0.9:t=fill",
        # Red bottom bar
        "drawbox=x=0:y=ih-6:w=iw:h=6:color=red@0.9:t=fill",
    ])

    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            output_path,
        ], capture_output=True, timeout=300)
        if result.returncode == 0:
            print("  Cinematic effects applied ✅")
            return True
        else:
            print(f"  [WARN] Effects failed: {result.stderr[-300:].decode('utf-8','ignore')}")
            return False
    except Exception as e:
        print(f"  [WARN] Cinematic effects error: {e}")
        return False
