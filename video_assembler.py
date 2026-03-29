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

TARGET_W, TARGET_H = 1080, 1920  # 9:16 vertical
CUT_INTERVAL = 4.0               # default seconds per scene cut

# Pacing label → cut duration in seconds
PACING_DURATIONS = {
    "slow": 5.0,
    "medium": 4.0,
    "fast": 2.5,
    "climax": 1.5,
}


def _crop_to_vertical(clip):
    w, h = clip.size
    target_ratio = TARGET_W / TARGET_H
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        x1 = (w - new_w) // 2
        clip = clip.crop(x1=x1, x2=x1 + new_w)
    else:
        new_h = int(w / target_ratio)
        y1 = (h - new_h) // 2
        clip = clip.crop(y1=y1, y2=y1 + new_h)
    return clip.resize((TARGET_W, TARGET_H))


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
                       scene_pacing: list | None = None) -> list[str]:
    """
    Build cut sequence in story order with no within-scene repetition.
    Uses scene_pacing (list of 15 pacing labels) for dynamic cut durations.
    Processes one source clip at a time (low memory).
    """
    scene_groups = _group_clips_by_scene(clip_files)
    if not scene_groups:
        return []

    num_scenes = len(scene_groups)

    # Build per-scene cut duration from pacing labels
    # scene_pacing has 15 entries (one per scene); cycle if needed
    def _scene_duration(scene_idx: int) -> float:
        if scene_pacing and scene_idx < len(scene_pacing):
            return PACING_DURATIONS.get(scene_pacing[scene_idx], CUT_INTERVAL)
        return CUT_INTERVAL

    # Pre-compute cut plan: (scene_idx, clip_pos_within_scene, chunk_duration)
    plan = []
    scene_clip_idx = [0] * num_scenes
    t = 0.0
    cut_index = 0
    total_cuts_estimate = int(total_duration / CUT_INTERVAL) + 1
    while t < total_duration - 0.05:
        si = min(int(cut_index / total_cuts_estimate * num_scenes), num_scenes - 1)
        interval = _scene_duration(si)
        chunk = min(interval, total_duration - t)
        cp = scene_clip_idx[si] % len(scene_groups[si])
        scene_clip_idx[si] += 1
        plan.append((si, cp, chunk))
        t += chunk
        cut_index += 1

    avg_cut = sum(c for _, _, c in plan) / len(plan) if plan else CUT_INTERVAL
    print(f"  {len(scene_groups)} scenes, {sum(len(g) for g in scene_groups)} clips, "
          f"{len(plan)} cuts (avg {avg_cut:.1f}s) — processing one clip at a time...")

    # Process each cut: open source → subclip → dark grade → write temp → close
    os.makedirs(temp_dir, exist_ok=True)
    temp_paths = []
    for i, (si, cp, chunk) in enumerate(plan):
        src_path = scene_groups[si][cp]
        temp_path = os.path.join(temp_dir, f"cut_{i:03d}.mp4")
        try:
            src = VideoFileClip(src_path, audio=False)
            src = _crop_to_vertical(src)
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


def assemble_video(output_dir: str, lang: str = "zh", wiki_clips: list | None = None,
                   scene_pacing: list | None = None) -> str | None:
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
    print(f"  Building scene cuts from {len(clip_files)} clips...")
    cut_paths = _build_video_clips(clip_files, duration, temp_cuts_dir, scene_pacing=scene_pacing)

    if not cut_paths:
        print("  [ERROR] No clips assembled")
        return None

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
        print("  Adding subtitles...")
        try:
            _burn_subtitles_pillow(temp_path, srt_path, subtitle_out)
            os.remove(temp_path)
            print("  Subtitles added ✅")
        except Exception as e:
            print(f"  [WARN] Subtitle burn failed: {e}")
            subtitle_out = temp_path  # fallback: use audio-only version

    else:
        subtitle_out = temp_path

    # Apply cinematic effects (CCTV grain + vignette + red bars + REC indicator)
    print("  Applying cinematic effects...")
    effects_ok = _apply_cinematic_effects(subtitle_out, final_path)
    if os.path.exists(subtitle_out) and subtitle_out != final_path:
        os.remove(subtitle_out)
    if not effects_ok:
        # Fallback: just rename
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
