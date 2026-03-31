"""
Design Agent — visual design, layout, and competitor style reference.

Responsibilities:
- Analyze competitor channel visual styles
- Design info cards (case file, timeline, breaking news)
- Ensure visual consistency across the video
- Manage color palette, typography, spacing
- Generate scene-by-scene visual direction
"""
from agents.llm import ask


# Competitor style profiles (extracted from channel analysis)
COMPETITOR_STYLES = {
    "腦洞烏托邦": {
        "color_palette": "dark navy/black + white text + red accents",
        "font_style": "large bold sans-serif Chinese, centered",
        "thumbnail": "dark background, 4-8 char bold text, red elements, one face",
        "video_style": "narration + real photos + maps + document images",
        "transitions": "cross-dissolve, slow zoom on images",
        "text_overlay": "bottom-center subtitles, white with black outline",
    },
    "老高與小茉": {
        "color_palette": "warm dark tones, occasional bright accent",
        "font_style": "clean sans-serif, moderate size",
        "thumbnail": "face reactions + bold Chinese text + mystery imagery",
        "video_style": "face cam + slides + photos",
        "transitions": "cut, occasional zoom",
        "text_overlay": "large bottom subtitles",
    },
    "曉涵哥來了": {
        "color_palette": "high contrast, red/black dominant",
        "font_style": "bold, sometimes with glow effect",
        "thumbnail": "dramatic face + red text + exclamation marks",
        "video_style": "face cam + case footage + dramatic overlays",
        "transitions": "fast cuts during tense moments",
        "text_overlay": "animated text popups for emphasis",
    },
}

# Our channel's design system
DESIGN_SYSTEM = {
    "primary_bg": (10, 10, 20),
    "text_primary": (255, 250, 230),
    "text_secondary": (150, 150, 170),
    "accent_red": (200, 20, 20),
    "accent_red_dark": (140, 15, 15),
    "date_color": (200, 80, 80),
    "divider_color": (80, 70, 60),
    "badge_bg": (180, 10, 10),
    "font_sizes": {
        "title_large": 64,
        "title_medium": 48,
        "body": 32,
        "caption": 24,
        "badge": 28,
    },
}


def plan_visual_direction(script_data: dict, case_data: dict) -> dict:
    """
    Create a scene-by-scene visual direction plan.
    Tells the Visual Agent exactly what to show for each section.
    """
    print("  [Design] Planning visual direction...")

    sections_summary = []
    for s in script_data.get("sections", []):
        sections_summary.append({
            "name": s["name"],
            "script_preview": s["script"][:150],
            "visual_hints": s.get("visual_hints", []),
        })

    result = ask(f"""你是一位犯罪紀實影片的視覺總監，參考腦洞烏托邦的風格。

案件：{case_data.get('case_name', '')}
年份：{case_data.get('year', '')}
地點：{case_data.get('city', '')}

各段落摘要：
{sections_summary}

受害者：{case_data.get('victims', [])}
嫌疑人：{case_data.get('suspects', [])}

=== 參考風格（腦洞烏托邦）===
- 暗色背景（深藍/黑色）
- 真實案件照片為主（嫌犯、受害者、現場、法庭）
- 地圖標記犯罪地點
- 新聞報紙頭版截圖
- 時間線動態呈現
- 少量 stock footage 作為過場（雨天街道、警車、法庭外觀）
- 字幕：底部白色，黑色描邊

=== 任務 ===
為每個段落規劃具體的視覺方向，包括：
1. 應該搜尋什麼真實照片（Wikimedia 搜尋關鍵字）
2. 需要什麼類型的 info card
3. Pexels stock footage 搜尋詞（過場用）
4. 特效建議

回傳 JSON：
{{
  "sections": [
    {{
      "name": "段落名",
      "info_card_type": "case_file/timeline/breaking_news/none",
      "wiki_search_queries": ["搜尋1", "搜尋2"],
      "pexels_queries": ["atmospheric query1", "query2"],
      "visual_notes": "這段的視覺重點說明",
      "transition": "cut/cross-dissolve/fade-to-black"
    }}
  ],
  "color_mood": "整體色調建議",
  "style_notes": "額外的視覺風格筆記"
}}""")

    print(f"  [Design] Visual plan: {len(result.get('sections', []))} sections directed")
    return result


def review_visual_quality(video_info: dict) -> dict:
    """
    Review the assembled video for visual quality issues.
    Called by QA Agent.
    """
    print("  [Design] Reviewing visual quality...")

    issues = []

    # Check footage variety
    clip_count = video_info.get("total_clips", 0)
    unique_scenes = video_info.get("unique_scenes", 0)
    if unique_scenes > 0 and clip_count / unique_scenes > 3:
        issues.append({
            "type": "素材重複",
            "severity": "high",
            "detail": f"每個場景平均重複 {clip_count/unique_scenes:.1f} 次",
            "fix": "增加 Pexels 搜尋多樣性或增加 Wikimedia 圖片"
        })

    # Check info card presence
    if not video_info.get("has_info_cards", False):
        issues.append({
            "type": "缺少資訊字卡",
            "severity": "high",
            "detail": "影片沒有案件檔案/時間線/新聞字卡",
            "fix": "加入 info_cards 模組生成的字卡"
        })

    # Check subtitle presence
    if not video_info.get("has_subtitles", False):
        issues.append({
            "type": "缺少字幕",
            "severity": "critical",
            "detail": "影片沒有燒入字幕",
            "fix": "修復字幕燒錄流程"
        })

    # Check duration
    duration = video_info.get("duration", 0)
    if duration < 600:
        issues.append({
            "type": "時長不足",
            "severity": "medium",
            "detail": f"影片只有 {duration/60:.0f} 分鐘，建議 12-20 分鐘",
            "fix": "增加腳本字數或放慢語速"
        })

    return {
        "issues": issues,
        "pass": len([i for i in issues if i["severity"] in ("critical", "high")]) == 0,
    }
