"""
QA Agent — pre-upload quality gate for both crime and books pipelines.

Merged from the old qa_agent.py + test_video.py checks.
Runs automatically before upload; blocks upload on critical failures.

Checks:
 1. Video file exists + ffprobe metadata
 2. Duration within range
 3. Resolution ≥ 1920×1080
 4. Audio stream present
 5. Audio/video duration sync (≤1.5 s gap)
 6. SRT exists + content validation (card length, brackets, timing)
 7. Black frame detection (start / mid / end)
 8. Frozen frame detection (last N seconds — catches the Theranos bug)
 9. Scene cut frequency (≥2 cuts/min)
10. Info cards (crime) / illustration count (books)
11. File size sanity
"""
import os
import json
import subprocess
import tempfile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ffprobe_json(path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", path],
        capture_output=True, text=True, timeout=30,
    )
    return json.loads(r.stdout)


def _extract_frame_brightness(video_path: str, time_sec: float) -> float | None:
    """Extract a single frame via ffmpeg and return mean brightness (0-255)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=True) as tmp:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(time_sec), "-i", video_path,
                 "-frames:v", "1", "-f", "image2", tmp.name],
                capture_output=True, timeout=15,
            )
            if os.path.getsize(tmp.name) < 100:
                return None
            # Read raw pixel data — BMP is uncompressed so we can just average bytes
            data = open(tmp.name, "rb").read()
            # Skip BMP header (54 bytes typically), average remaining
            pixels = data[54:]
            if not pixels:
                return None
            return sum(pixels) / len(pixels)
    except Exception:
        return None


def _sample_brightness_series(video_path: str, n_samples: int, duration: float) -> list:
    """Sample brightness at evenly-spaced points. Returns [(time, brightness)]."""
    import numpy as np
    times = np.linspace(2.0, max(3.0, duration - 1.0), n_samples)
    results = []
    for t in times:
        b = _extract_frame_brightness(video_path, float(t))
        if b is not None:
            results.append((float(t), b))
    return results


# ---------------------------------------------------------------------------
# Subtitle validation (from test_video.py)
# ---------------------------------------------------------------------------

def _check_subtitles(srt_path: str, audio_duration: float) -> list:
    """Validate SRT content. Returns list of issue dicts."""
    issues = []
    try:
        import srt as srt_lib
    except ImportError:
        issues.append({"check": "字幕內容", "status": "WARN", "severity": "low",
                       "detail": "srt library not installed, skipping content checks"})
        return issues

    try:
        with open(srt_path, "r", encoding="utf-8") as f:
            subs = list(srt_lib.parse(f.read()))
    except Exception as e:
        issues.append({"check": "字幕解析", "status": "FAIL", "severity": "high",
                       "detail": f"SRT parse error: {e}"})
        return issues

    if not subs:
        issues.append({"check": "字幕內容", "status": "FAIL", "severity": "high",
                       "detail": "SRT is empty (0 cards)"})
        return issues

    # Last subtitle vs audio duration
    last_end = max(s.end.total_seconds() for s in subs)
    if last_end > audio_duration + 2.0:
        issues.append({"check": "字幕超出音訊", "status": "WARN", "severity": "medium",
                       "detail": f"字幕結束 {last_end:.1f}s > 音訊 {audio_duration:.1f}s"})

    # Card length (>34 chars)
    long_cards = [s for s in subs if len(s.content.replace("\n", "")) > 34]
    if len(long_cards) > len(subs) * 0.15:
        issues.append({"check": "字幕卡長度", "status": "WARN", "severity": "low",
                       "detail": f"{len(long_cards)}/{len(subs)} 張卡片超過 34 字"})

    # Truncated cards
    truncated = [s for s in subs if s.content.rstrip().endswith("…")]
    if truncated:
        issues.append({"check": "字幕截斷", "status": "WARN", "severity": "medium",
                       "detail": f"{len(truncated)} 張卡片被截斷 (…)"})

    # Bracket pairs
    PAIRS = [("『", "』"), ("「", "」"), ("\u201c", "\u201d")]
    split_count = 0
    for sub in subs:
        for op, cl in PAIRS:
            if sub.content.count(op) != sub.content.count(cl):
                split_count += 1
                break
    if split_count:
        issues.append({"check": "字幕括號配對", "status": "WARN", "severity": "low",
                       "detail": f"{split_count} 張卡片有未配對的引號/括號"})

    if not issues:
        issues.append({"check": "字幕內容", "status": "PASS",
                       "detail": f"{len(subs)} 張卡片，內容檢查通過 ✓"})
    return issues


# ---------------------------------------------------------------------------
# Main review
# ---------------------------------------------------------------------------

def review_video(output_dir: str, expected_duration: float = 0,
                 channel: str = "truecrime") -> dict:
    """
    Comprehensive pre-upload quality gate.

    channel: "truecrime" or "books" — adjusts which checks apply.
    Returns dict with verdict: PASS / FIX_AND_RETRY / REJECT.
    """
    print("  [QA] Running quality checks...")

    # Detect final video (books may have final_zh_with_intro.mp4)
    final_candidates = ["final_zh_with_intro.mp4", "final_zh.mp4"]
    final_path = None
    for name in final_candidates:
        p = os.path.join(output_dir, name)
        if os.path.exists(p):
            final_path = p
            break

    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    voiceover_path = os.path.join(output_dir, "voiceover_zh.mp3")
    info_cards_dir = os.path.join(output_dir, "info_cards")
    clips_dir = os.path.join(output_dir, "clips")
    illustrations_dir = os.path.join(output_dir, "illustrations")

    issues = []

    # ── 1. Video file exists ─────────────────────────────────────────
    if not final_path:
        issues.append({"check": "影片檔案", "status": "FAIL", "severity": "critical",
                       "detail": "找不到 final_zh*.mp4"})
        return _build_report(issues)

    # ── ffprobe metadata ─────────────────────────────────────────────
    try:
        probe = _ffprobe_json(final_path)
        duration = float(probe["format"]["duration"])
        file_size_mb = int(probe["format"]["size"]) / 1024 / 1024
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        has_audio = any(s["codec_type"] == "audio" for s in probe["streams"])
        audio_dur = None
        for s in probe["streams"]:
            if s["codec_type"] == "audio" and "duration" in s:
                audio_dur = float(s["duration"])
    except Exception as e:
        issues.append({"check": "影片讀取", "status": "FAIL", "severity": "critical",
                       "detail": f"ffprobe 失敗: {e}"})
        return _build_report(issues)

    # ── 2. Duration ──────────────────────────────────────────────────
    if channel == "books":
        min_dur, max_dur = 420, 1500  # 7-25 min
    else:
        min_dur, max_dur = 480, 1500  # 8-25 min

    if duration < min_dur:
        issues.append({"check": "時長", "status": "WARN", "severity": "medium",
                       "detail": f"{duration/60:.1f} 分鐘，偏短"})
    elif duration > max_dur:
        issues.append({"check": "時長", "status": "WARN", "severity": "low",
                       "detail": f"{duration/60:.1f} 分鐘，可能太長"})
    else:
        issues.append({"check": "時長", "status": "PASS",
                       "detail": f"{duration/60:.1f} 分鐘 ✓"})

    # ── 3. Resolution ────────────────────────────────────────────────
    if width >= 1920 and height >= 1080:
        issues.append({"check": "解析度", "status": "PASS",
                       "detail": f"{width}x{height} ✓"})
    else:
        issues.append({"check": "解析度", "status": "WARN", "severity": "medium",
                       "detail": f"{width}x{height}，建議 1920x1080"})

    # ── 4. Audio present ─────────────────────────────────────────────
    if has_audio:
        issues.append({"check": "音訊", "status": "PASS", "detail": "有音訊 ✓"})
    else:
        issues.append({"check": "音訊", "status": "FAIL", "severity": "critical",
                       "detail": "沒有音訊！"})

    # ── 5. Audio/video duration sync ─────────────────────────────────
    # Compare video duration against voiceover file
    vo_dur = None
    if os.path.exists(voiceover_path):
        try:
            vo_probe = _ffprobe_json(voiceover_path)
            vo_dur = float(vo_probe["format"]["duration"])
        except Exception:
            pass

    if vo_dur is not None:
        gap = abs(duration - vo_dur)
        # Books with intro will be longer than voiceover — that's expected
        if channel == "books" and duration > vo_dur:
            # Allow intro padding (up to 30s)
            gap = max(0, duration - vo_dur - 30)
        if gap > 3.0:
            issues.append({"check": "音畫同步", "status": "FAIL", "severity": "high",
                           "detail": f"影片 {duration:.1f}s vs 語音 {vo_dur:.1f}s (差 {abs(duration-vo_dur):.1f}s)"})
        elif gap > 1.5:
            issues.append({"check": "音畫同步", "status": "WARN", "severity": "medium",
                           "detail": f"影片 {duration:.1f}s vs 語音 {vo_dur:.1f}s (差 {abs(duration-vo_dur):.1f}s)"})
        else:
            issues.append({"check": "音畫同步", "status": "PASS",
                           "detail": f"差距 {abs(duration-vo_dur):.1f}s ✓"})

    # ── 6. Subtitle checks ───────────────────────────────────────────
    if os.path.exists(srt_path):
        srt_size = os.path.getsize(srt_path)
        if srt_size > 100:
            issues.append({"check": "字幕檔", "status": "PASS",
                           "detail": f"SRT {srt_size/1024:.0f} KB ✓"})
            # Deep subtitle validation
            ref_dur = vo_dur or duration
            issues.extend(_check_subtitles(srt_path, ref_dur))
        else:
            issues.append({"check": "字幕檔", "status": "FAIL", "severity": "high",
                           "detail": "SRT 檔案太小，可能是空的"})
    else:
        issues.append({"check": "字幕檔", "status": "FAIL", "severity": "high",
                       "detail": "SRT 檔案不存在"})

    # ── 7. Black frame detection ─────────────────────────────────────
    BLACK_THRESHOLD = 5  # brightness below this = black
    check_points = {
        "開頭": min(2.0, duration * 0.05),
        "中段": duration / 2,
        "結尾": max(0, duration - 2.0),
    }
    black_fails = []
    for label, t in check_points.items():
        b = _extract_frame_brightness(final_path, t)
        if b is not None and b < BLACK_THRESHOLD:
            black_fails.append(f"{label}({t:.0f}s)")

    if black_fails:
        issues.append({"check": "黑畫面", "status": "FAIL", "severity": "high",
                       "detail": f"偵測到黑畫面: {', '.join(black_fails)}"})
    else:
        issues.append({"check": "黑畫面", "status": "PASS", "detail": "無黑畫面 ✓"})

    # ── 8. Frozen frame detection (last 20% of video) ────────────────
    # This catches the Theranos bug: last N minutes stuck on same frame
    frozen_start = duration * 0.8
    n_frozen_samples = 8
    frozen_samples = []
    step = (duration - frozen_start) / max(1, n_frozen_samples)
    for i in range(n_frozen_samples):
        t = frozen_start + i * step
        b = _extract_frame_brightness(final_path, t)
        if b is not None:
            frozen_samples.append(b)

    if len(frozen_samples) >= 4:
        # If all samples have nearly identical brightness → likely frozen
        spread = max(frozen_samples) - min(frozen_samples)
        if spread < 2.0:
            issues.append({"check": "凍結畫面", "status": "FAIL", "severity": "critical",
                           "detail": f"最後 {(duration - frozen_start)/60:.1f} 分鐘畫面疑似凍結 (亮度差僅 {spread:.1f})"})
        else:
            issues.append({"check": "凍結畫面", "status": "PASS",
                           "detail": f"尾段畫面有變化 (spread={spread:.1f}) ✓"})

    # ── 9. Scene cut frequency ───────────────────────────────────────
    n_cut_samples = min(100, int(duration / 2))
    if n_cut_samples >= 10:
        samples = _sample_brightness_series(final_path, n_cut_samples, duration)
        if len(samples) >= 10:
            cuts = 0
            for i in range(1, len(samples)):
                if abs(samples[i][1] - samples[i-1][1]) > 15:
                    cuts += 1
            cuts_per_min = cuts / (duration / 60)
            if cuts_per_min < 1.5:
                issues.append({"check": "場景切換", "status": "WARN", "severity": "medium",
                               "detail": f"約 {cuts_per_min:.1f} 次/分鐘，可能太靜態"})
            else:
                issues.append({"check": "場景切換", "status": "PASS",
                               "detail": f"約 {cuts_per_min:.1f} 次/分鐘 ✓"})

    # ── 10. Content checks (channel-specific) ────────────────────────
    if channel == "truecrime":
        # Info cards
        if os.path.exists(info_cards_dir):
            n_cards = len([f for f in os.listdir(info_cards_dir) if f.endswith(".mp4")])
            if n_cards >= 3:
                issues.append({"check": "資訊字卡", "status": "PASS",
                               "detail": f"{n_cards} 張字卡 ✓"})
            else:
                issues.append({"check": "資訊字卡", "status": "FAIL", "severity": "high",
                               "detail": f"只有 {n_cards} 張字卡 (需 ≥3)"})
        else:
            issues.append({"check": "資訊字卡", "status": "FAIL", "severity": "high",
                           "detail": "info_cards/ 目錄不存在"})
        # Footage variety
        if os.path.exists(clips_dir):
            clip_files = [f for f in os.listdir(clips_dir) if f.endswith(".mp4")]
            unique = len(set(f.split("_clip")[0] for f in clip_files))
            if unique < 15:
                issues.append({"check": "素材多樣性", "status": "WARN", "severity": "medium",
                               "detail": f"只有 {unique} 個不同場景"})
            else:
                issues.append({"check": "素材多樣性", "status": "PASS",
                               "detail": f"{unique} 個場景 ✓"})

    elif channel == "books":
        # Illustration count
        if os.path.exists(illustrations_dir):
            n_illust = len([f for f in os.listdir(illustrations_dir) if f.endswith(".png")])
            if os.path.exists(clips_dir):
                n_clips = len([f for f in os.listdir(clips_dir) if f.endswith(".mp4")])
            else:
                n_clips = 0
            if n_illust < 10:
                issues.append({"check": "插圖數量", "status": "FAIL", "severity": "high",
                               "detail": f"只有 {n_illust} 張插圖"})
            elif n_clips < n_illust:
                issues.append({"check": "插圖完整性", "status": "WARN", "severity": "medium",
                               "detail": f"{n_illust} 張插圖但只有 {n_clips} 個 clips"})
            else:
                issues.append({"check": "插圖", "status": "PASS",
                               "detail": f"{n_illust} 張插圖, {n_clips} clips ✓"})

    # ── 11. File size ────────────────────────────────────────────────
    if file_size_mb > 2000:
        issues.append({"check": "檔案大小", "status": "WARN", "severity": "low",
                       "detail": f"{file_size_mb:.0f} MB，建議 < 2GB"})
    elif file_size_mb < 1:
        issues.append({"check": "檔案大小", "status": "FAIL", "severity": "critical",
                       "detail": f"{file_size_mb:.1f} MB，檔案異常小"})
    else:
        issues.append({"check": "檔案大小", "status": "PASS",
                       "detail": f"{file_size_mb:.0f} MB ✓"})

    return _build_report(issues)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(issues: list) -> dict:
    """Build QA report with verdict."""
    critical = [i for i in issues if i.get("severity") == "critical"]
    high = [i for i in issues if i.get("severity") == "high"]
    fails = [i for i in issues if i.get("status") == "FAIL"]
    passes = [i for i in issues if i.get("status") == "PASS"]

    if critical:
        verdict = "REJECT"
    elif high or fails:
        verdict = "FIX_AND_RETRY"
    else:
        verdict = "PASS"

    report = {
        "verdict": verdict,
        "total_checks": len(issues),
        "passed": len(passes),
        "failed": len(fails),
        "issues": issues,
    }

    print(f"\n  [QA] ══════ Quality Report ══════")
    for i in issues:
        icon = "✅" if i["status"] == "PASS" else ("❌" if i["status"] == "FAIL" else "⚠️")
        print(f"  {icon} {i['check']}: {i['detail']}")
    print(f"  ─────────────────────────────")
    print(f"  Verdict: {verdict} ({len(passes)}/{len(issues)} passed)")
    print(f"  ════════════════════════════\n")

    return report
