#!/usr/bin/env python3
"""
Video quality checker — run after assembly to verify output integrity.
Usage:
  python test_video.py output/20260324_開膛手傑克/final_zh.mp4
  python test_video.py output/20260324_開膛手傑克/   # auto-finds final_zh.mp4
"""

import sys
import os

def check_subtitles(srt_path: str, audio_duration: float) -> bool:
    """Verify SRT timing doesn't exceed audio and cards aren't too long."""
    import srt as srt_lib

    passed = True
    print(f"\n  --- Subtitle Check: {os.path.basename(srt_path)} ---")

    with open(srt_path, "r", encoding="utf-8") as f:
        subs = list(srt_lib.parse(f.read()))

    if not subs:
        print("  [FAIL] SRT is empty")
        return False

    # Check last subtitle doesn't exceed audio
    last_end = max(s.end.total_seconds() for s in subs)
    print(f"  Last subtitle end: {last_end:.2f}s vs audio {audio_duration:.2f}s", end="")
    if last_end > audio_duration + 0.5:
        print(f"  ← [FAIL] Subtitles extend {last_end - audio_duration:.1f}s past audio")
        passed = False
    else:
        print("  ✅")

    # Check no card is too long (> 34 chars)
    long_cards = [(i+1, s.content) for i, s in enumerate(subs) if len(s.content.replace("\n","")) > 34]
    if long_cards:
        print(f"  [WARN] {len(long_cards)} cards exceed 34 chars:")
        for idx, txt in long_cards[:3]:
            print(f"    #{idx}: {txt[:40]}")
    else:
        print(f"  All {len(subs)} cards ≤34 chars  ✅")

    # Check for truncated cards (ending with …)
    truncated = [s for s in subs if s.content.rstrip().endswith("…")]
    if truncated:
        print(f"  [FAIL] {len(truncated)} cards truncated with '…'")
        passed = False
    else:
        print("  No truncated cards  ✅")

    # Check bracket pairs are not split across cards
    PAIRS = [("『", "』"), ("「", "」"), ("\u201c", "\u201d")]
    split_pairs = []
    for i, sub in enumerate(subs):
        for op, cl in PAIRS:
            opens = sub.content.count(op)
            closes = sub.content.count(cl)
            if opens != closes:
                split_pairs.append((i + 1, sub.content[:30]))
    if split_pairs:
        print(f"  [FAIL] {len(split_pairs)} cards have unmatched dialogue brackets:")
        for idx, txt in split_pairs[:3]:
            print(f"    #{idx}: {txt}")
        passed = False
    else:
        print("  Dialogue brackets balanced in all cards  ✅")

    # Check subtitle timing is proportional (no card > 20% of total duration)
    total_dur = sum((s.end - s.start).total_seconds() for s in subs)
    oversized = [(i+1, (s.end-s.start).total_seconds()) for i, s in enumerate(subs)
                 if (s.end-s.start).total_seconds() > audio_duration * 0.20]
    if oversized:
        print(f"  [WARN] {len(oversized)} cards are very long (>20% of video):")
        for idx, dur in oversized[:3]:
            print(f"    #{idx}: {dur:.1f}s")
    else:
        print(f"  Timing spread looks even  ✅")

    return passed


def check_video(video_path: str, audio_path: str = None) -> bool:
    from moviepy.editor import VideoFileClip, AudioFileClip
    import numpy as np

    print(f"\n{'='*50}")
    print(f"Quality Check: {os.path.basename(video_path)}")
    print(f"{'='*50}")

    passed = True

    # 1. File exists and has reasonable size
    if not os.path.exists(video_path):
        print("  [FAIL] File does not exist")
        return False

    size_mb = os.path.getsize(video_path) / 1024 / 1024
    print(f"  File size: {size_mb:.1f} MB", end="")
    if size_mb < 1:
        print("  ← [FAIL] Too small")
        passed = False
    elif size_mb > 500:
        print("  ← [WARN] Very large")
    else:
        print("  ✅")

    # 2. Load video
    try:
        clip = VideoFileClip(video_path)
    except Exception as e:
        print(f"  [FAIL] Cannot open video: {e}")
        return False

    vid_dur = clip.duration
    print(f"  Video duration: {vid_dur:.2f}s  ✅")

    # 3. Check audio track
    if clip.audio is None:
        print("  [FAIL] No audio track")
        passed = False
    else:
        aud_dur = clip.audio.duration
        print(f"  Audio duration: {aud_dur:.2f}s", end="")
        diff = abs(vid_dur - aud_dur)
        if diff > 1.0:
            print(f"  ← [FAIL] Mismatch vs video ({diff:.1f}s gap)")
            passed = False
        else:
            print("  ✅")

    # 4. Compare against voiceover if provided
    if audio_path and os.path.exists(audio_path):
        vo = AudioFileClip(audio_path)
        vo_dur = vo.duration
        vo.close()
        print(f"  Voiceover duration: {vo_dur:.2f}s", end="")
        diff = abs(vid_dur - vo_dur)
        if diff > 1.5:
            print(f"  ← [FAIL] Video ({vid_dur:.1f}s) vs voiceover ({vo_dur:.1f}s): {diff:.1f}s gap")
            passed = False
        else:
            print(f"  ✅ (diff {diff:.2f}s)")

    # 5. Check first frame is not black (sample at 2s to skip any fade-in)
    try:
        frame_start = clip.get_frame(min(2.0, vid_dur * 0.05))
        brightness_start = frame_start.mean()
        print(f"  First frame brightness: {brightness_start:.1f}", end="")
        if brightness_start < 1:
            print("  ← [FAIL] Black frame at start")
            passed = False
        else:
            print("  ✅")
    except Exception as e:
        print(f"  [WARN] Could not sample first frame: {e}")

    # 6. Check middle frame
    try:
        mid = vid_dur / 2
        frame_mid = clip.get_frame(mid)
        brightness_mid = frame_mid.mean()
        print(f"  Middle frame brightness ({mid:.0f}s): {brightness_mid:.1f}", end="")
        if brightness_mid < 2:
            print("  ← [FAIL] Black frame at middle")
            passed = False
        else:
            print("  ✅")
    except Exception as e:
        print(f"  [WARN] Could not sample middle frame: {e}")

    # 7. Check last 3 seconds are NOT black
    try:
        check_t = max(0, vid_dur - 2.0)
        frame_end = clip.get_frame(check_t)
        brightness_end = frame_end.mean()
        print(f"  Last frame brightness ({check_t:.0f}s): {brightness_end:.1f}", end="")
        if brightness_end < 2:
            print("  ← [FAIL] Black frame near end (no video at ending)")
            passed = False
        else:
            print("  ✅")
    except Exception as e:
        print(f"  [WARN] Could not sample end frame: {e}")

    # 8. Count scene cuts (estimate from frame differences)
    try:
        sample_times = np.linspace(0, vid_dur, min(200, int(vid_dur)))
        cuts = 0
        prev_bright = None
        for t in sample_times:
            f = clip.get_frame(float(t))
            b = f.mean()
            if prev_bright is not None and abs(b - prev_bright) > 20:
                cuts += 1
            prev_bright = b
        cuts_per_min = cuts / (vid_dur / 60)
        print(f"  Estimated scene cuts: {cuts} (~{cuts_per_min:.0f}/min)", end="")
        if cuts_per_min < 2:
            print("  ← [WARN] Very few cuts (may feel static)")
        else:
            print("  ✅")
    except Exception as e:
        print(f"  [WARN] Could not count cuts: {e}")

    clip.close()

    print(f"\n{'='*50}")
    if passed:
        print("  ✅ ALL CHECKS PASSED")
    else:
        print("  ❌ SOME CHECKS FAILED — review output above")
    print(f"{'='*50}\n")

    return passed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_video.py <video_path_or_output_dir>")
        sys.exit(1)

    target = sys.argv[1]

    # If directory given, find final_zh.mp4
    if os.path.isdir(target):
        video_path = os.path.join(target, "final_zh.mp4")
        audio_path = os.path.join(target, "voiceover_zh.mp3")
    else:
        video_path = target
        audio_path = video_path.replace("final_zh.mp4", "voiceover_zh.mp3")

    ok = check_video(video_path, audio_path if os.path.exists(audio_path) else None)

    # Also check SRT if available
    srt_path = video_path.replace("final_zh.mp4", "subtitles_zh.srt")
    if os.path.exists(srt_path) and audio_path and os.path.exists(audio_path):
        from moviepy.editor import AudioFileClip as _AFC
        _a = _AFC(audio_path)
        aud_dur = _a.duration
        _a.close()
        srt_ok = check_subtitles(srt_path, aud_dur)
        ok = ok and srt_ok

    sys.exit(0 if ok else 1)
