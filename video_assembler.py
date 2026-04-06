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


def _render_subtitle_frame(txt: str, target_w: int = 0) -> np.ndarray:
    """Render subtitle text as RGBA image. Adapts to video width."""
    from PIL import Image, ImageDraw, ImageFont

    font_candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    ]
    font_path = next((p for p in font_candidates if os.path.exists(p)), "")

    if target_w == 0:
        target_w = TARGET_W

    # Adapt font size and chars per line based on video width
    if target_w >= 1920:  # 16:9 landscape
        FONT_SIZE = 38
        CHARS_PER_LINE = 28
    else:  # 9:16 vertical
        FONT_SIZE = 46
        CHARS_PER_LINE = 16

    lines = []
    remaining = txt.strip()
    while remaining:
        lines.append(remaining[:CHARS_PER_LINE])
        remaining = remaining[CHARS_PER_LINE:]

    try:
        font = ImageFont.truetype(font_path, FONT_SIZE) if font_path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()

    line_h = FONT_SIZE + 12
    img = Image.new("RGBA", (target_w, line_h * len(lines) + 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (target_w - w) // 2
        y = i * line_h
        # Black outline for readability
        for ox, oy in [(-2, -2), (-2, 2), (2, -2), (2, 2), (0, -2), (0, 2), (-2, 0), (2, 0)]:
            draw.text((x + ox, y + oy), line, font=font, fill=(0, 0, 0, 220))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    return np.array(img)


def _burn_subtitles_pillow(input_path: str, srt_path: str, output_path: str):
    """Burn subtitles using Pillow. Auto-detects video dimensions."""
    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))

    base = VideoFileClip(input_path)
    video_dur = base.duration
    vid_w, vid_h = base.size

    # Subtitle position: near bottom, adapted to aspect ratio
    sub_y = vid_h - 120 if vid_w >= 1920 else vid_h - 220

    subtitle_clips = []
    for sub in subtitles:
        start = sub.start.total_seconds()
        end = min(sub.end.total_seconds(), video_dur)
        if start >= video_dur or end <= start:
            continue
        txt = sub.content.replace("\n", " ").strip()
        if not txt:
            continue

        frame = _render_subtitle_frame(txt, target_w=vid_w)
        sc = (ImageClip(frame, ismask=False)
              .set_start(start)
              .set_end(end)
              .set_position(("center", sub_y)))
        subtitle_clips.append(sc)

    final = CompositeVideoClip([base] + subtitle_clips)
    final = final.set_audio(base.audio)
    final.write_videofile(output_path, fps=25, codec="libx264", audio_codec="aac", logger=None)
    final.close()
    base.close()


def _burn_subtitles_ffmpeg(input_path: str, srt_path: str, output_path: str):
    """
    Burn subtitles for long videos by splitting into chunks, processing
    each with PIL (low memory), then concatenating back.
    Falls back to PIL method if ffmpeg subtitles filter is unavailable.
    """
    import subprocess

    # Split video into 3-minute chunks, burn subs on each, concatenate
    # This avoids OOM from loading the entire video into MoviePy at once
    with open(srt_path, "r", encoding="utf-8") as f:
        subtitles = list(srt.parse(f.read()))

    # Get video duration
    base = VideoFileClip(input_path, audio=False)
    total_dur = base.duration
    base.close()

    chunk_dur = 180.0  # 3 minutes per chunk
    n_chunks = max(1, int(total_dur / chunk_dur) + 1)
    chunk_dir = os.path.join(os.path.dirname(output_path), "_sub_chunks")
    os.makedirs(chunk_dir, exist_ok=True)

    chunk_paths = []
    for ci in range(n_chunks):
        t_start = ci * chunk_dur
        t_end = min((ci + 1) * chunk_dur, total_dur)
        if t_start >= total_dur:
            break

        chunk_in = os.path.join(chunk_dir, f"chunk_{ci:03d}_in.mp4")
        chunk_out = os.path.join(chunk_dir, f"chunk_{ci:03d}_out.mp4")

        # Extract chunk with ffmpeg (fast, no re-encode)
        subprocess.run([
            "ffmpeg", "-y", "-ss", str(t_start), "-t", str(t_end - t_start),
            "-i", input_path, "-c", "copy", chunk_in,
        ], capture_output=True, timeout=60)

        # Filter subtitles for this chunk's time range
        chunk_subs = []
        for sub in subtitles:
            s = sub.start.total_seconds()
            e = sub.end.total_seconds()
            if s < t_end and e > t_start:
                import copy
                new_sub = copy.copy(sub)
                new_sub.start = srt.timedelta(seconds=max(0, s - t_start))
                new_sub.end = srt.timedelta(seconds=min(t_end - t_start, e - t_start))
                chunk_subs.append(new_sub)

        if chunk_subs and os.path.exists(chunk_in):
            # Write chunk SRT
            chunk_srt = os.path.join(chunk_dir, f"chunk_{ci:03d}.srt")
            with open(chunk_srt, "w", encoding="utf-8") as f:
                f.write(srt.compose(chunk_subs))
            # Burn with PIL (small chunk = safe memory)
            try:
                _burn_subtitles_pillow(chunk_in, chunk_srt, chunk_out)
                os.remove(chunk_in)
                os.remove(chunk_srt)
                chunk_paths.append(chunk_out)
            except Exception as e:
                print(f"  [WARN] Chunk {ci} subtitle failed: {e}")
                chunk_paths.append(chunk_in)  # use unsubbed chunk
        elif os.path.exists(chunk_in):
            chunk_paths.append(chunk_in)

        if (ci + 1) % 3 == 0:
            print(f"    Subtitle chunk {ci+1}/{n_chunks}...")

    # Concatenate all chunks
    if chunk_paths:
        concat_list = os.path.join(chunk_dir, "concat.txt")
        with open(concat_list, "w") as f:
            for p in chunk_paths:
                f.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-c", "copy", output_path,
        ], capture_output=True, check=True, timeout=120)

        # Cleanup
        import shutil
        shutil.rmtree(chunk_dir, ignore_errors=True)
    else:
        raise RuntimeError("No subtitle chunks produced")


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

    # Pre-compute cut plan — each clip used ONCE, no repeats
    # If not enough clips, extend each clip's duration (slow down) instead of looping
    total_clips = sum(len(g) for g in scene_groups)
    if total_clips > 0:
        # Target duration per clip to fill the entire video without repeats
        target_per_clip = total_duration / total_clips
        # But don't go shorter than pacing allows or longer than 15s
        min_dur = 3.0
        max_dur = 15.0
        per_clip_dur = max(min_dur, min(max_dur, target_per_clip))
    else:
        per_clip_dur = default_interval

    plan = []
    t = 0.0
    for si, group in enumerate(scene_groups):
        for cp, clip_path in enumerate(group):
            if t >= total_duration - 0.05:
                break
            chunk = min(per_clip_dur, total_duration - t)
            plan.append((si, cp, chunk))
            t += chunk
        if t >= total_duration - 0.05:
            break

    avg_cut = sum(c for _, _, c in plan) / len(plan) if plan else default_interval
    print(f"  {len(scene_groups)} scenes, {total_clips} clips, "
          f"{len(plan)} cuts (avg {avg_cut:.1f}s, no repeats) — {fmt} mode ({tw}x{th})...")

    os.makedirs(temp_dir, exist_ok=True)
    temp_paths = []
    for i, (si, cp, chunk) in enumerate(plan):
        src_path = scene_groups[si][cp]
        temp_path = os.path.join(temp_dir, f"cut_{i:03d}.mp4")
        try:
            src = VideoFileClip(src_path, audio=False)
            src = _crop_to_target(src, tw, th)
            if fmt == "short":
                src = _apply_dark_grade(src)

            if src.duration >= chunk:
                # Clip is long enough — use a random segment
                offset = random.uniform(0, src.duration - chunk)
                sub = src.subclip(offset, offset + chunk)
            else:
                # Clip shorter than needed — use entire clip (no repeat)
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


def _image_to_video(image_path: str, video_path: str, duration: float = 4.0):
    """Convert a static image to a video clip with slight zoom effect."""
    import subprocess
    tw, th = TARGET_W_LONG, TARGET_H_LONG
    # Slight zoom in effect (1.0 → 1.05 over duration)
    vf = f"scale={tw}:{th},zoompan=z='min(zoom+0.0008,1.05)':d={int(duration*25)}:s={tw}x{th}:fps=25"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", image_path,
        "-vf", vf,
        "-t", str(duration), "-r", "25",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        video_path,
    ], capture_output=True, timeout=30)


def _insert_info_cards(cut_paths: list[str], info_cards: dict,
                       output_dir: str, total_duration: float) -> list[str]:
    """
    Insert info card video clips at section-appropriate positions.
    hook card → near start, crime card → ~20%, twist card → ~60%, resolution → ~85%
    """
    n = len(cut_paths)
    cards_dir = os.path.join(output_dir, "info_cards")

    # Section → approximate position in timeline
    insert_map = {
        "hook": max(1, int(n * 0.02)),        # right after opening
        "crime": int(n * 0.20),               # ~20% through
        "twist": int(n * 0.55),               # ~55% through
        "resolution": int(n * 0.82),          # ~82% through
    }

    # Convert each card image to video clip and insert
    result = list(cut_paths)
    offset = 0  # track insertions
    for section_name in ["hook", "crime", "twist", "resolution"]:
        if section_name not in info_cards:
            continue
        img_path = info_cards[section_name]
        if not os.path.exists(img_path):
            continue

        vid_path = img_path.replace(".jpg", ".mp4")
        card_duration = 5.0 if section_name == "hook" else 4.0
        _image_to_video(img_path, vid_path, duration=card_duration)

        if os.path.exists(vid_path):
            pos = insert_map[section_name] + offset
            pos = min(pos, len(result))
            result.insert(pos, vid_path)
            offset += 1

    return result


def _interleave_wiki_clips(cut_paths: list[str], wiki_clips: list[str]) -> list[str]:
    """
    Insert wiki archive clips evenly throughout the video.
    For long-form (many wiki clips), they become the PRIMARY visual content,
    with Pexels clips as transitions between wiki images.
    """
    if not wiki_clips:
        return cut_paths

    n_cuts = len(cut_paths)
    n_wiki = len(wiki_clips)

    # If we have lots of wiki clips (long-form), distribute evenly
    # Every N cuts, insert a wiki clip
    if n_wiki >= 10:
        # Roughly 1 wiki clip every 3-4 Pexels cuts
        interval = max(2, n_cuts // (n_wiki + 1))
        result = []
        wiki_idx = 0
        for i, cut in enumerate(cut_paths):
            result.append(cut)
            if (i + 1) % interval == 0 and wiki_idx < n_wiki:
                result.append(wiki_clips[wiki_idx])
                wiki_idx += 1
        # Append any remaining wiki clips at the end
        while wiki_idx < n_wiki:
            result.append(wiki_clips[wiki_idx])
            wiki_idx += 1
        return result

    # Original logic for Shorts (few wiki clips)
    insert_positions = [2]
    remaining = wiki_clips[1:]
    step = max(1, n_cuts // (len(remaining) + 1))
    pos = step
    for _ in remaining:
        insert_positions.append(min(pos, n_cuts - 1))
        pos += step

    result = list(cut_paths)
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

    # (red bars removed for clean look)

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
                   scene_pacing: list | None = None, fmt: str = "short",
                   info_cards: dict | None = None) -> str | None:
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

    # Insert info cards at section boundaries (long-form only)
    if info_cards and fmt == "long":
        cut_paths = _insert_info_cards(cut_paths, info_cards, output_dir, duration)
        print(f"  Inserted {len(info_cards)} info cards")

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
            "-af", "volume=0.30",
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

    # Subtitles: long-form uses SRT upload, Shorts burn into video
    subtitle_out = temp_path
    if fmt == "short" and os.path.exists(srt_path):
        print("  Burning subtitles (Shorts only)...")
        sub_out = final_path.replace("final_", "_sub_")
        try:
            _burn_subtitles_pillow(temp_path, srt_path, sub_out)
            os.remove(temp_path)
            subtitle_out = sub_out
            print("  Subtitles burned ✅")
        except Exception as e:
            print(f"  [WARN] Subtitle burn failed: {e}")
            subtitle_out = temp_path
    else:
        print("  Subtitles: will upload SRT to YouTube")

    # Apply cinematic effects (grain + vignette + color grade)
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
    ])

    try:
        result = subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-vf", vf,
            "-c:a", "copy",
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            output_path,
        ], capture_output=True, timeout=1200)
        if result.returncode == 0:
            print("  Cinematic effects applied ✅")
            return True
        else:
            print(f"  [WARN] Effects failed: {result.stderr[-300:].decode('utf-8','ignore')}")
            return False
    except Exception as e:
        print(f"  [WARN] Cinematic effects error: {e}")
        return False
