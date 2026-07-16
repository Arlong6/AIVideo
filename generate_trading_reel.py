"""AI 交易實驗室 — 週報 reel 端到端。

用法：python generate_trading_reel.py [--end-date YYYY-MM-DD]
（--end-date 供回填/測試；正式跑不帶參數，吃最新數據 + 過期檢查）
"""
import argparse
import json
import os
from datetime import datetime

from market_data_ingest import build_week_pack
from trading_script import (
    generate_weekly_script, DISCLAIMER, BannedWordError, CJKNumeralError,
)
from number_gate import NumberMismatch
from equity_chart import render_equity_chart

GATE_ERRORS = (NumberMismatch, BannedWordError, CJKNumeralError)


def _generate_script_with_retry(pack: dict) -> dict:
    """腳本生成 — 數字/禁詞/CJK 閘門攔下時重試一次；連續兩次被攔就 fail-closed。"""
    last_err = None
    for attempt in (1, 2):
        try:
            return generate_weekly_script(pack)
        except GATE_ERRORS as e:
            last_err = e
            print(f"  [gate] attempt {attempt} blocked: {type(e).__name__}: {e}")
    raise RuntimeError(
        f"script generation blocked twice by gate — refusing to render. "
        f"Last error: {type(last_err).__name__}: {last_err}"
    ) from last_err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--end-date", default=None)
    args = ap.parse_args()

    print("[1/6] 數據包...")
    pack = build_week_pack(end_date=args.end_date)
    print(json.dumps(pack, ensure_ascii=False)[:200])

    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join("output", f"{date_str}_trading_w{pack['week_number']}")
    clips_dir = os.path.join(output_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    print("[2/6] 腳本（含數字對帳 + 禁詞閘門）...")
    script = _generate_script_with_retry(pack)
    print(f"  title: {script['title']}")

    render(pack, script, output_dir, clips_dir)


def render(pack: dict, script: dict, output_dir: str, clips_dir: str) -> str:
    """Steps 3-6: 視覺/TTS/組裝/打包 — 拆出來讓下游可獨立驗證（不依賴 LLM 閘門）。"""
    # metadata.json — export_reel 打包與 QA 都吃這份
    meta = {"zh": {**script, "opening_card": script["title"][:8],
                   "pinned_comment": "", "content_type": "trading"}}
    with open(os.path.join(output_dir, "metadata.json"), "w",
              encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("[3/6] 視覺素材...")
    chart_png = os.path.join(output_dir, "equity_chart.png")
    render_equity_chart(pack, chart_png)
    # 場景圖：noir 桌面/機房氛圍插圖（Imagen，禁真人 prefix），hook 與 outro 用
    from illustration_generator import generate_illustration
    from agents.visual_agent import CRIME_STYLE_PREFIX
    prefix = CRIME_STYLE_PREFIX.replace("cinematic 16:9",
                                        "vertical cinematic composition")
    hook_png = os.path.join(output_dir, "hook_scene.png")
    generate_illustration(
        "glowing computer screen with trading charts in a dark room, "
        "single desk lamp", hook_png, style_prefix=prefix, aspect="9:16")

    # PNG → clips/（沿用 Ken Burns 動態；圖表維持靜態滿版）
    #
    # _make_ken_burns_clip 是為 16:9 landscape 素材設計的：_fit_for_ken_burns
    # 固定把來源放大 1.18 倍再裁切取景，任何一幀都只看得到裁切後的畫面。
    # equity_chart.png 已經是精準的 1080x1920（跟輸出尺寸完全相同），而且角落
    # 燒了「模擬盤實驗」角標（防線 2，合規用途）——套用那個裁切會把角標和部分
    # 座標軸文字裁掉，畫面不可讀也不合規。圖表改成靜態滿版顯示，不做任何裁切；
    # hook 場景圖（Imagen 插畫，無需保留角落文字）維持 Ken Burns 動態。
    from illustration_generator import _make_ken_burns_clip
    from moviepy.editor import ImageClip
    import numpy as np
    from PIL import Image as PILImage
    for i, (png, dur) in enumerate([(hook_png, 8.0), (chart_png, 20.0),
                                    (hook_png, 8.0)]):
        img = np.array(PILImage.open(png).convert("RGB"))
        if png == chart_png:
            clip = ImageClip(img).set_duration(dur).resize((1080, 1920))
        else:
            clip = _make_ken_burns_clip(img, duration=dur,
                                        target_w=1080, target_h=1920)
        clip.write_videofile(os.path.join(clips_dir, f"s{i:02d}_clip1.mp4"),
                             fps=25, codec="libx264", audio=False, logger=None)
        clip.close()

    print("[4/6] TTS + 字幕...")
    full_text = "。".join([script["hook"]]
                          + [s["text"] for s in script["sections"]]
                          + [script["cta"]])
    from tts_generator import generate_voiceover
    vo_path = os.path.join(output_dir, "voiceover_zh.mp3")
    generate_voiceover(full_text, "zh", vo_path)
    from moviepy.editor import AudioFileClip
    a = AudioFileClip(vo_path); vo_dur = a.duration; a.close()
    from subtitle_generator import generate_srt
    generate_srt(full_text, vo_dur, os.path.join(output_dir, "subtitles_zh.srt"))

    print("[5/6] 組裝（fmt=short 9:16）...")
    from video_assembler import assemble_video
    # skip_cinematic=True: 內建的「cinematic effects」是為 crime 頻道調的
    # true-crime 紀錄片 teal-amber 濾鏡 + vignette（刻意壓暗四角、聚焦中央）。
    # 這支頻道的賣點是數據透明，equity_chart.png 角落燒了「模擬盤實驗」角標
    # （防線 2，合規用途）——vignette 壓暗角落會讓角標和座標軸文字幾乎看不見。
    # 交易頻道不套用 crime 的噪點/暗角風格。
    final = assemble_video(output_dir, lang="zh", fmt="short", skip_cinematic=True)
    if not final:
        raise RuntimeError("assemble_video returned None")

    print("[6/6] 打包 upload_package...")
    from export_reel import package
    pkg = package(output_dir)
    if pkg:
        _ensure_disclaimer_first_line(pkg)
    print(f"完成：{pkg}")
    return pkg


def _ensure_disclaimer_first_line(pkg_dir: str) -> None:
    """export_reel.package() 產的 caption 是為 crime 頻道寫的通用模板，不知道
    交易頻道專屬的「模擬盤」免責聲明。這裡補上——保證每份 caption 檔案的
    第一行就是 DISCLAIMER，不依賴 LLM 描述、不能被腳本省略（fail-closed 的
    延伸：閘門保證 description 裡有 DISCLAIMER，這裡保證它出現在使用者
    實際會看到的貼文文案最前面）。
    """
    for name in ("caption_tiktok.txt", "caption_fb.txt"):
        path = os.path.join(pkg_dir, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            body = f.read()
        if body.startswith(DISCLAIMER):
            continue
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{DISCLAIMER}\n\n{body}")


if __name__ == "__main__":
    main()
