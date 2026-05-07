"""
Series 化 — 把每部影片自動分到對應 series, 加描述欄頭部 + YouTube playlist.

5 大系列定位 (依 STRATEGY_2026Q2.md):
  1. 台灣冤案檔案 — 江國慶 / 鄭性澤 / 邱和順 / 蘇建和 / 盧正春 / 王迎先 等
  2. 台灣未解懸案 — 江子翠 / 林宅血案 / 劉邦友 / 彭婉如 / 八德 / 釣魚台 等
  3. 台灣校園黑色史 — 國三生 / 嘉義大學 / 校園 / 大學 / 學生
  4. 台灣政治謀殺疑雲 — 林宅血案 / 陳文成 / 王迎先 / 政治 / 民主
  5. 台灣黑幫往事 — 竹聯 / 四海 / 陳啟禮 / 翁奇楠 / 黑道 / 黑幫

Series tag detection 用 case_name + key_facts 做關鍵字 match.
若 multi-match 取優先序最高(冤案>政治>校園>黑幫>未解).
若無 match 就 default 「真實犯罪檔案」(generic).
"""
import json
import os
import pickle


SERIES_DEFS = [
    {
        "tag": "wrongful_conviction",
        "name": "台灣冤案檔案",
        "playlist_id_file": "series_playlist_wrongful.txt",
        "keywords": ["冤案", "冤獄", "平反", "改判", "誤判", "錯判",
                     "江國慶", "鄭性澤", "邱和順", "蘇建和", "盧正春",
                     "王迎先", "陳龍綺", "鄭信義", "徐自強"],
        "priority": 5,
        "header": "🔖 台灣冤案檔案 — 司法錯誤的代價"
    },
    {
        "tag": "political",
        "name": "台灣政治謀殺疑雲",
        "playlist_id_file": "series_playlist_political.txt",
        "keywords": ["政治", "民主", "黨外", "戒嚴", "美麗島",
                     "林宅血案", "陳文成", "尹清楓", "劉邦友", "彭婉如"],
        "priority": 4,
        "header": "🔖 台灣政治謀殺疑雲 — 體制下的犧牲者"
    },
    {
        "tag": "campus",
        "name": "台灣校園黑色史",
        "playlist_id_file": "series_playlist_campus.txt",
        "keywords": ["校園", "學生", "大學", "高中", "國中", "國小",
                     "新北國三生", "嘉義大學", "教師", "老師", "霸凌"],
        "priority": 3,
        "header": "🔖 台灣校園黑色史 — 那些不該發生的事"
    },
    {
        "tag": "gang",
        "name": "台灣黑幫往事",
        "playlist_id_file": "series_playlist_gang.txt",
        "keywords": ["黑道", "黑幫", "幫派", "竹聯", "四海", "天道盟",
                     "陳啟禮", "翁奇楠", "陳由豪", "兄弟", "幫主"],
        "priority": 2,
        "header": "🔖 台灣黑幫往事 — 黑色江湖實錄"
    },
    {
        "tag": "unsolved",
        "name": "台灣未解懸案",
        "playlist_id_file": "series_playlist_unsolved.txt",
        "keywords": ["懸案", "未解", "至今", "成謎", "謎團",
                     "江子翠", "八德", "白雪枝", "井口真理子"],
        "priority": 1,
        "header": "🔖 台灣未解懸案 — 至今未破的真相"
    },
]

DEFAULT_SERIES = {
    "tag": "default",
    "name": "真實犯罪檔案",
    "playlist_id_file": "",
    "header": "🔖 真實犯罪檔案"
}


def detect_series(case_data: dict, title: str = "") -> dict:
    """根據 case_name / key_facts / title 判斷 series. 取最高 priority."""
    text = " ".join([
        case_data.get("case_name", "") or "",
        title or "",
        " ".join(case_data.get("key_facts", []) or []),
        case_data.get("summary", "") or "",
    ])
    matches = []
    for s in SERIES_DEFS:
        for kw in s["keywords"]:
            if kw in text:
                matches.append(s)
                break
    if not matches:
        return DEFAULT_SERIES
    return max(matches, key=lambda s: s["priority"])


def get_series_count(series_tag: str, video_log_path: str = "video_log.json") -> int:
    """過去同 series 上傳幾部 — 用來編號 #N."""
    if not os.path.exists(video_log_path):
        return 0
    log = json.load(open(video_log_path))
    n = 0
    for v in log.get("videos", []):
        if v.get("series_tag") == series_tag:
            n += 1
    return n


def build_series_description_header(series: dict, episode: int) -> str:
    """生成描述欄頭部. 若有 playlist link 一起放."""
    header = f"{series['header']} #{episode}\n"
    pid_file = series.get("playlist_id_file", "")
    if pid_file and os.path.exists(pid_file):
        pid = open(pid_file).read().strip()
        if pid:
            header += f"📺 完整系列: https://www.youtube.com/playlist?list={pid}\n"
    return header + "\n"


def get_or_create_playlist(youtube, series: dict) -> str | None:
    """確保 playlist 存在. 回傳 playlist_id. 失敗回 None."""
    pid_file = series.get("playlist_id_file", "")
    if not pid_file:
        return None
    if os.path.exists(pid_file):
        pid = open(pid_file).read().strip()
        if pid:
            return pid
    # Create new playlist
    try:
        body = {
            "snippet": {
                "title": series["name"],
                "description": f"{series['header']}\n\n本系列收錄相關真實案件深度解析",
                "defaultLanguage": "zh-Hant",
            },
            "status": {"privacyStatus": "public"},
        }
        resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
        pid = resp["id"]
        with open(pid_file, "w") as f:
            f.write(pid)
        print(f"  [Series] Created playlist '{series['name']}' = {pid}")
        return pid
    except Exception as e:
        print(f"  [Series] Playlist create failed: {e}")
        return None


def add_to_playlist(youtube, video_id: str, playlist_id: str) -> bool:
    """Add uploaded video to series playlist."""
    try:
        youtube.playlistItems().insert(
            part="snippet",
            body={"snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }},
        ).execute()
        print(f"  [Series] ✓ Added to playlist {playlist_id}")
        return True
    except Exception as e:
        print(f"  [Series] Playlist add failed: {e}")
        return False
