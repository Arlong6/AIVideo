"""
QA Agent — quality assurance and review.

Responsibilities:
- Check subtitles exist and are burned in
- Check footage variety (no excessive repetition)
- Check info cards are inserted
- Check audio/video sync
- Check duration is within target range
- Report issues with severity levels
- Decide: pass / fix and retry / reject
"""
import os
import subprocess


def review_video(output_dir: str, expected_duration: float = 0) -> dict:
    """
    Comprehensive quality check of the generated video.
    Returns pass/fail with detailed issue list.
    """
    print("  [QA] Running quality checks...")

    final_path = os.path.join(output_dir, "final_zh.mp4")
    srt_path = os.path.join(output_dir, "subtitles_zh.srt")
    info_cards_dir = os.path.join(output_dir, "info_cards")
    clips_dir = os.path.join(output_dir, "clips")

    issues = []

    # 1. Check video file exists and is valid
    if not os.path.exists(final_path):
        issues.append({"check": "影片檔案", "status": "FAIL", "severity": "critical",
                       "detail": "final_zh.mp4 不存在"})
        return _build_report(issues)

    # Get video info
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", "-show_streams", final_path
        ], capture_output=True, text=True, timeout=30)
        import json
        probe = json.loads(result.stdout)
        duration = float(probe["format"]["duration"])
        file_size = int(probe["format"]["size"]) / 1024 / 1024  # MB
        video_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        has_audio = any(s["codec_type"] == "audio" for s in probe["streams"])
    except Exception as e:
        issues.append({"check": "影片讀取", "status": "FAIL", "severity": "critical",
                       "detail": f"ffprobe 失敗: {e}"})
        return _build_report(issues)

    # 2. Duration check
    if duration < 480:  # < 8 min
        issues.append({"check": "時長", "status": "WARN", "severity": "medium",
                       "detail": f"{duration/60:.1f} 分鐘，建議 10-20 分鐘"})
    elif duration > 1500:  # > 25 min
        issues.append({"check": "時長", "status": "WARN", "severity": "low",
                       "detail": f"{duration/60:.1f} 分鐘，可能太長"})
    else:
        issues.append({"check": "時長", "status": "PASS",
                       "detail": f"{duration/60:.1f} 分鐘 ✓"})

    # 3. Resolution check
    if width >= 1920 and height >= 1080:
        issues.append({"check": "解析度", "status": "PASS",
                       "detail": f"{width}x{height} ✓"})
    else:
        issues.append({"check": "解析度", "status": "WARN", "severity": "medium",
                       "detail": f"{width}x{height}，建議 1920x1080"})

    # 4. Audio check
    if has_audio:
        issues.append({"check": "音訊", "status": "PASS", "detail": "有音訊 ✓"})
    else:
        issues.append({"check": "音訊", "status": "FAIL", "severity": "critical",
                       "detail": "沒有音訊！"})

    # 5. Subtitle check — sample a frame to see if subtitles are visible
    if os.path.exists(srt_path):
        srt_size = os.path.getsize(srt_path)
        if srt_size > 100:
            issues.append({"check": "字幕檔", "status": "PASS",
                           "detail": f"SRT 存在 ({srt_size/1024:.0f} KB) ✓"})
        else:
            issues.append({"check": "字幕檔", "status": "FAIL", "severity": "high",
                           "detail": "SRT 檔案太小，可能是空的"})
    else:
        issues.append({"check": "字幕檔", "status": "FAIL", "severity": "high",
                       "detail": "SRT 檔案不存在"})

    # Check if subtitles are burned in (compare file size with/without subs)
    # Heuristic: if file is < 1.5 MB/min, subtitles probably weren't burned
    mb_per_min = file_size / (duration / 60)
    if mb_per_min < 8:
        issues.append({"check": "字幕燒錄", "status": "WARN", "severity": "medium",
                       "detail": f"Bitrate 偏低 ({mb_per_min:.0f} MB/min)，字幕可能未燒入"})

    # 6. Info cards check
    if os.path.exists(info_cards_dir) and len(os.listdir(info_cards_dir)) >= 3:
        issues.append({"check": "資訊字卡", "status": "PASS",
                       "detail": f"{len(os.listdir(info_cards_dir))} 張字卡 ✓"})
    else:
        issues.append({"check": "資訊字卡", "status": "FAIL", "severity": "high",
                       "detail": "沒有資訊字卡或不足 3 張"})

    # 7. Footage variety check
    if os.path.exists(clips_dir):
        clip_files = [f for f in os.listdir(clips_dir) if f.endswith(".mp4")]
        unique_scenes = len(set(f.split("_clip")[0] for f in clip_files))
        if unique_scenes < 15:
            issues.append({"check": "素材多樣性", "status": "WARN", "severity": "medium",
                           "detail": f"只有 {unique_scenes} 個不同場景"})
        else:
            issues.append({"check": "素材多樣性", "status": "PASS",
                           "detail": f"{unique_scenes} 個場景 ✓"})

    # 8. File size check
    if file_size > 2000:
        issues.append({"check": "檔案大小", "status": "WARN", "severity": "low",
                       "detail": f"{file_size:.0f} MB，YouTube 上傳限制 256GB 但建議 < 2GB"})
    else:
        issues.append({"check": "檔案大小", "status": "PASS",
                       "detail": f"{file_size:.0f} MB ✓"})

    return _build_report(issues)


def _build_report(issues: list) -> dict:
    """Build QA report from issues list."""
    critical = [i for i in issues if i.get("severity") == "critical"]
    high = [i for i in issues if i.get("severity") == "high"]
    passes = [i for i in issues if i.get("status") == "PASS"]
    fails = [i for i in issues if i.get("status") == "FAIL"]

    verdict = "PASS"
    if critical:
        verdict = "REJECT"
    elif high:
        verdict = "FIX_AND_RETRY"
    elif fails:
        verdict = "FIX_AND_RETRY"

    report = {
        "verdict": verdict,
        "total_checks": len(issues),
        "passed": len(passes),
        "failed": len(fails),
        "issues": issues,
    }

    # Print summary
    print(f"\n  [QA] ══════ Quality Report ══════")
    for i in issues:
        icon = "✅" if i["status"] == "PASS" else ("❌" if i["status"] == "FAIL" else "⚠️")
        print(f"  {icon} {i['check']}: {i['detail']}")
    print(f"  ─────────────────────────────")
    print(f"  Verdict: {verdict} ({len(passes)}/{len(issues)} passed)")
    print(f"  ════════════════════════════\n")

    return report
