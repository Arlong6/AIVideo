import json
import os

from export_reel import package


def _write_metadata(output_dir: str, zh: dict) -> None:
    with open(os.path.join(output_dir, "metadata.json"), "w",
              encoding="utf-8") as f:
        json.dump({"zh": zh}, f, ensure_ascii=False)


def _write_fake_video(output_dir: str) -> None:
    # package() just needs the file to exist to shutil.copy it.
    with open(os.path.join(output_dir, "final_zh.mp4"), "wb") as f:
        f.write(b"\x00" * 16)


def test_trading_content_type_uses_trading_tags_not_crime_tags(tmp_path):
    output_dir = str(tmp_path)
    _write_fake_video(output_dir)
    _write_metadata(output_dir, {
        "title": "AI 操盤第 7 週：+0.27%",
        "opening_card": "AI 操盤第7週",
        "description": "AI 自動交易模擬盤實驗第 7 週紀錄。",
        "hashtags": ["#AI交易", "#量化"],
        "content_type": "trading",
    })

    pkg = package(output_dir)
    assert pkg is not None

    tiktok = open(os.path.join(pkg, "caption_tiktok.txt"), encoding="utf-8").read()
    fb = open(os.path.join(pkg, "caption_fb.txt"), encoding="utf-8").read()

    for caption in (tiktok, fb):
        assert "#真實案件" not in caption
        assert "#懸案" not in caption
        assert "#犯罪紀實" not in caption
        assert "#模擬盤實驗" in caption


def test_trading_content_type_uses_truthful_disclosure(tmp_path):
    output_dir = str(tmp_path)
    _write_fake_video(output_dir)
    _write_metadata(output_dir, {
        "title": "AI 操盤第 7 週：+0.27%",
        "opening_card": "AI 操盤第7週",
        "description": "AI 自動交易模擬盤實驗第 7 週紀錄。",
        "hashtags": ["#AI交易", "#量化"],
        "content_type": "trading",
    })

    pkg = package(output_dir)
    assert pkg is not None

    tiktok = open(os.path.join(pkg, "caption_tiktok.txt"), encoding="utf-8").read()
    fb = open(os.path.join(pkg, "caption_fb.txt"), encoding="utf-8").read()

    for caption in (tiktok, fb):
        assert "模擬盤實驗紀錄" in caption
        assert "公開紀錄查證" not in caption


def test_default_content_type_keeps_crime_tags_backward_compatible(tmp_path):
    """metadata 沒設 content_type（既有 crime 頻道行為）必須完全不變。"""
    output_dir = str(tmp_path)
    _write_fake_video(output_dir)
    _write_metadata(output_dir, {
        "title": "白銀連續殺人案",
        "opening_card": "白銀案",
        "description": "根據公開紀錄改編。",
        "hashtags": ["#刑案", "#紀實"],
    })

    pkg = package(output_dir)
    assert pkg is not None

    tiktok = open(os.path.join(pkg, "caption_tiktok.txt"), encoding="utf-8").read()
    fb = open(os.path.join(pkg, "caption_fb.txt"), encoding="utf-8").read()

    for caption in (tiktok, fb):
        assert "#真實案件" in caption
        assert "#懸案" in caption
        assert "#模擬盤實驗" not in caption
        assert "公開紀錄查證" in caption
        assert "模擬盤實驗紀錄" not in caption
