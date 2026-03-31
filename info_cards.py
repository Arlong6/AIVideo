"""
Generate documentary-style info cards for long-form crime videos.

Three styles:
A) Breaking News — 新聞快報 (for twists, key events)
B) Timeline — 時間線 (for case progression)
C) Case File — 案件檔案 (for intro/outro)

Each function returns a static image path that can be converted to
a Ken Burns video clip by the assembler.
"""

import os
import random
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080


def _find_font() -> str:
    for p in [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if os.path.exists(p):
            return p
    return ""


FONT_PATH = _find_font()


def _font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Style A: Breaking News (新聞快報)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_breaking_news(headline: str, sub_lines: list[str],
                       ticker: str = "", output_path: str = "") -> str:
    """Breaking news style card."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark blue gradient
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(10 + 15 * t), int(15 + 20 * t), int(40 + 50 * t)))

    # Red top bar
    draw.rectangle([(0, 0), (W, 6)], fill=(200, 20, 20))

    # "即時新聞" badge
    draw.rounded_rectangle([30, 20, 210, 64], radius=6, fill=(200, 20, 20))
    draw.text((46, 22), "即時新聞", font=_font(32), fill=(255, 255, 255))

    # LIVE indicator
    draw.rounded_rectangle([W - 155, 20, W - 30, 64], radius=6, fill=(200, 20, 20))
    draw.text((W - 138, 22), "● LIVE", font=_font(30), fill=(255, 255, 255))

    # Main headline — auto-wrap if too long
    f_lg = _font(64)
    # Wrap headline to max ~16 chars per line
    h_lines = []
    remaining = headline
    while remaining:
        h_lines.append(remaining[:18])
        remaining = remaining[18:]
    h_lines = h_lines[:2]

    total_h = len(h_lines) * 80
    start_y = (H - total_h) // 2 - 60
    for i, hl in enumerate(h_lines):
        bbox = draw.textbbox((0, 0), hl, font=f_lg)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, start_y + i * 80), hl, font=f_lg, fill=(255, 255, 255))

    # Separator
    sep_y = start_y + len(h_lines) * 80 + 15
    draw.line([(200, sep_y), (W - 200, sep_y)], fill=(80, 80, 120), width=1)

    # Sub lines — also wrap long lines
    f_md = _font(34)
    sub_y = sep_y + 25
    for i, line in enumerate(sub_lines[:3]):
        # Truncate to ~35 chars
        if len(line) > 38:
            line = line[:36] + "…"
        bbox = draw.textbbox((0, 0), line, font=f_md)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, sub_y + i * 52), line, font=f_md, fill=(190, 200, 220))

    # Bottom ticker bar
    if ticker:
        draw.rectangle([(0, H - 72), (W, H)], fill=(180, 15, 15))
        draw.line([(0, H - 74), (W, H - 74)], fill=(220, 20, 20), width=2)
        ticker_text = ticker[:60] if len(ticker) > 60 else ticker
        draw.text((30, H - 62), f"▶ {ticker_text}", font=_font(28), fill=(255, 255, 255))

    img.save(output_path, "JPEG", quality=95)
    return output_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Style B: Timeline (時間線)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_timeline(title: str, year: str,
                  events: list[tuple[str, str, str]],
                  output_path: str = "") -> str:
    """Timeline card."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Very dark background
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(5 + 8 * t), int(5 + 5 * t), int(8 + 12 * t)))

    # Red accent bars
    draw.rectangle([(0, 0), (W, 5)], fill=(180, 20, 20))
    draw.rectangle([(0, H - 5), (W, H)], fill=(180, 20, 20))

    # Big faded year
    draw.text((80, 50), year, font=_font(110), fill=(45, 45, 65))

    # Title — wrap if needed
    title_display = title[:20] if len(title) > 20 else title
    draw.text((250, 90), title_display, font=_font(56), fill=(255, 250, 230))
    draw.text((250, 160), "案件時間線", font=_font(32), fill=(130, 130, 155))

    # Calculate spacing based on event count
    n_events = min(len(events), 5)
    line_x = 220
    y_start = 230
    spacing = min(145, (H - y_start - 60) // max(n_events, 1))

    # Vertical timeline line
    y_end = y_start + n_events * spacing
    draw.line([(line_x, y_start), (line_x, y_end)], fill=(180, 30, 30), width=3)

    # Events
    for i, (date, evt_title, desc) in enumerate(events[:5]):
        y = y_start + 15 + i * spacing
        # Red dot
        draw.ellipse([line_x - 7, y - 7, line_x + 7, y + 7], fill=(200, 30, 30))
        # Date — truncate
        date_str = date[:12] if len(date) > 12 else date
        draw.text((line_x + 35, y - 18), date_str, font=_font(30), fill=(200, 80, 80))
        # Event title — truncate
        evt_str = evt_title[:18] if len(evt_title) > 18 else evt_title
        draw.text((line_x + 280, y - 20), evt_str, font=_font(32), fill=(255, 250, 230))
        # Description — truncate
        if desc:
            desc_str = desc[:28] if len(desc) > 28 else desc
            draw.text((line_x + 280, y + 18), desc_str, font=_font(24), fill=(140, 140, 160))

    img.save(output_path, "JPEG", quality=95)
    return output_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Style C: Case File (案件檔案)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def make_case_file(title: str, case_number: str,
                   fields: list[tuple[str, str]],
                   status: str = "調查中",
                   output_path: str = "") -> str:
    """Case file card."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Dark textured background
    rng = random.Random(42)
    for y in range(0, H, 2):
        for x in range(0, W, 4):
            v = rng.randint(18, 28)
            draw.rectangle([x, y, x + 4, y + 2], fill=(v, v - 2, v - 5))

    # Left red accent bar
    draw.rectangle([(0, 0), (8, H)], fill=(160, 20, 20))

    # Case number badge
    badge_text = f"案件編號 {case_number}"
    badge_w = len(badge_text) * 17 + 50
    draw.rounded_rectangle([60, 50, 60 + badge_w, 105],
                            radius=8, outline=(180, 30, 30), width=2)
    draw.text((80, 58), badge_text, font=_font(32), fill=(180, 50, 50))

    # Title — wrap if too long
    title_display = title[:22] if len(title) > 22 else title
    draw.text((80, 135), title_display, font=_font(52), fill=(220, 215, 200))

    # Divider
    draw.line([(80, 210), (W - 80, 210)], fill=(80, 70, 60), width=1)

    # Fields — consistent label column width
    label_x = 100
    value_x = 320
    for i, (label, value) in enumerate(fields[:6]):
        y = 240 + i * 75
        # Truncate long values
        value_str = value[:30] if len(value) > 30 else value
        draw.text((label_x, y), f"{label}：", font=_font(30), fill=(140, 120, 100))
        draw.text((value_x, y), value_str, font=_font(30), fill=(220, 215, 200))
        draw.line([(value_x, y + 42), (W - 100, y + 42)], fill=(50, 45, 40), width=1)

    # Status stamp — bottom right
    stamp_color = (180, 30, 30) if "結案" in status or "CLOSED" in status else (180, 140, 30)
    status_str = status[:16] if len(status) > 16 else status
    sb = draw.textbbox((0, 0), status_str, font=_font(34))
    sw = sb[2] - sb[0]
    stamp_x = W - sw - 100
    draw.rounded_rectangle([stamp_x - 20, H - 120, stamp_x + sw + 20, H - 60],
                            radius=6, outline=stamp_color, width=3)
    draw.text((stamp_x, H - 114), status_str, font=_font(34), fill=stamp_color)

    img.save(output_path, "JPEG", quality=95)
    return output_path


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Auto-generate cards for a case from script sections
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_info_cards(script_data: dict, output_dir: str) -> dict[str, str]:
    """
    Auto-generate info cards for each section of a long-form video.
    Uses Gemini to extract case details from the script.

    Returns: {"hook": path, "crime": path, "twist": path, ...}
    """
    cards_dir = os.path.join(output_dir, "info_cards")
    os.makedirs(cards_dir, exist_ok=True)

    title = script_data.get("title", "真實犯罪")
    sections = script_data.get("sections", [])

    # Extract case details from script for the case file card
    case_details = _extract_case_details(script_data)

    cards = {}

    # 1. Hook section → Case File card (intro)
    cards["hook"] = make_case_file(
        title=title,
        case_number=case_details.get("case_number", "#XXXX"),
        fields=case_details.get("fields", []),
        status=case_details.get("status", "調查中"),
        output_path=os.path.join(cards_dir, "card_hook_casefile.jpg"),
    )

    # 2. Crime section → Timeline card
    cards["crime"] = make_timeline(
        title=title,
        year=case_details.get("year", "20XX"),
        events=case_details.get("timeline_events", []),
        output_path=os.path.join(cards_dir, "card_crime_timeline.jpg"),
    )

    # 3. Twist section → Breaking News card
    twist_section = next((s for s in sections if s["name"] == "twist"), None)
    twist_headline = title
    twist_lines = []
    if twist_section:
        # Use first 2 sentences as sub-lines
        script_text = twist_section["script"]
        sentences = [s.strip() for s in script_text.replace("。", "。|").split("|") if s.strip()]
        twist_lines = sentences[:3]

    cards["twist"] = make_breaking_news(
        headline=f"【突發】{title}",
        sub_lines=twist_lines,
        ticker=case_details.get("ticker", ""),
        output_path=os.path.join(cards_dir, "card_twist_news.jpg"),
    )

    # 4. Resolution section → Case File card (closed)
    cards["resolution"] = make_case_file(
        title=title,
        case_number=case_details.get("case_number", "#XXXX"),
        fields=case_details.get("fields", []),
        status=case_details.get("resolution_status", "已結案 CLOSED"),
        output_path=os.path.join(cards_dir, "card_resolution_casefile.jpg"),
    )

    print(f"  Generated {len(cards)} info cards")
    return cards


def _extract_case_details(script_data: dict) -> dict:
    """Extract case details from script using Gemini."""
    try:
        from config import GEMINI_API_KEY
        from google import genai

        if not GEMINI_API_KEY:
            raise ValueError("No Gemini key")

        client = genai.Client(api_key=GEMINI_API_KEY)
        title = script_data.get("title", "")
        script = script_data.get("script", "")[:2000]

        prompt = f"""從以下犯罪案件腳本中提取關鍵資訊，用 JSON 格式回傳：

標題：{title}
腳本摘要：{script}

請回傳：
{{
  "case_number": "#年份-月日（如 #1997-0414）",
  "year": "案發年份（如 1997）",
  "fields": [
    ["受害者", "姓名（年齡）"],
    ["案發地點", "城市，國家"],
    ["案發日期", "年月日"],
    ["嫌疑人", "姓名"],
    ["案件類型", "類型"],
    ["結案狀態", "狀態"]
  ],
  "status": "調查中 或 已結案 CLOSED 或 懸案 UNSOLVED",
  "resolution_status": "最終狀態",
  "timeline_events": [
    ["日期", "事件標題", "簡短描述"],
    ["日期", "事件標題", "簡短描述"]
  ],
  "ticker": "新聞跑馬燈文字（一句話描述案件最震撼的點）"
}}"""

        r = client.models.generate_content(
            model="gemini-2.5-flash", contents=prompt,
            config={"response_mime_type": "application/json"},
        )
        import json
        content = r.text
        start = content.find("{")
        end = content.rfind("}") + 1
        details = json.loads(content[start:end])

        # Convert fields/timeline from lists to tuples
        details["fields"] = [tuple(f) for f in details.get("fields", [])]
        details["timeline_events"] = [tuple(e) for e in details.get("timeline_events", [])]
        return details

    except Exception as e:
        print(f"  [WARN] Case detail extraction failed: {e}")
        return {
            "case_number": "#XXXX",
            "year": "20XX",
            "fields": [("案件", script_data.get("title", "未知"))],
            "status": "調查中",
            "resolution_status": "已結案 CLOSED",
            "timeline_events": [],
            "ticker": "",
        }
