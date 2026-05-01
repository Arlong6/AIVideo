"""
Title DNA patterns — data-driven, extracted from Opus 4.6 forensic analysis.

Source: 腦洞烏托邦 (252萬訂閱) — 200 videos analyzed, 49 outliers identified.
Each pattern traced to specific videos with 3x+ median view performance.
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TITLE DNA FORMULAS (from forensic analysis, ranked by view performance)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TITLE_DNA = {
    "權力揭秘體": {
        "formula": "[人名/身份] + [極端反差/隱藏真相] + [權力暗示] + [99%沒看懂]",
        "avg_views": 1_082_543,
        "share": "40%+ of outliers",
        "templates": [
            "{person}的背景有多強大？{shocking_fact}的驚人真相",
            "{event}水有多深？真正的黑手並沒有被揪出",
            "冒死深扒！{person}被封殺的真相…99%的人都沒看懂",
            "{person}從{positive}到一夜消失…背後的驚天內幕",
        ],
        "examples": [
            ("范冰冰案水有多深？真正的黑手並沒有被揪出", 2_244_851),
            ("馮小剛的背景有多強大？中國頂級導演的驚人上位史", 1_619_838),
            ("趙本山被封殺的真相…本山帝國", 1_128_002),
        ],
        "trigger_words": ["背景", "水有多深", "99%", "真相", "冒死深扒", "封殺"],
    },

    "預言末日體": {
        "formula": "[年份/時間] + [顛覆性宣告] + [與觀眾切身危機] + [數字佐證]",
        "avg_views": 1_013_286,
        "share": "~20% of outliers",
        "templates": [
            "{year}真正要發生的事將顛覆你的想像！{region}是核心？",
            "{year}普通人唯一的機會…{number}年前他預言這一切",
            "准到可怕的{source}預言，{number}個中已實現{achieved}個！",
            "{year}像極了{historical_year}…{crisis_hint}",
        ],
        "examples": [
            ("2025年7月5日真正要發生的事將顛覆你的想像！台灣香港是核心？", 2_823_824),
            ("准到可怕的佛教預言，14個中已實現12個！", 1_173_462),
            ("2026普通人唯一的機會！10年前他預言這一切", 1_421_706),
        ],
        "trigger_words": ["顛覆", "預言", "准到可怕", "普通人", "唯一的機會"],
    },

    "禁區探秘體": {
        "formula": "[地點+最XX] + [詭異事件] + [科學無法解釋] + [真相揭曉]",
        "avg_views": 1_044_937,
        "share": "~15% of outliers",
        "templates": [
            "{region}最邪門的地方，進去就別想出來，科學根本無法解釋！",
            "{region}最恐怖的禁區…{number}人有去無回，究竟藏著什麼秘密？",
            "{location}的真相…{number}年來無數人失蹤",
        ],
        "examples": [
            ("西藏最邪門的地方，進去就別想出來，科學根本無法解釋！", 2_042_472),
            ("中國最恐怖的禁區…羅布泊究竟藏著什麼秘密？", 1_183_176),
            ("藏地最邪門古墓…九層妖墓的真相", 869_373),
        ],
        "trigger_words": ["最邪門", "禁區", "無法解釋", "有去無回", "秘密"],
    },

    "國家解剖體": {
        "formula": "[國家極端定語] + [荒誕反差] + [制度性病灶] + [與已知國家對標]",
        "avg_views": 878_445,
        "share": "~12% of outliers",
        "templates": [
            "全球唯一能在{aspect}上碾壓{comparison_country}的國家！{shocking_fact}",
            "{country}繁華表象下的吃人真相…{stat}",
            "{country}如何從{past}淪為{present}？",
        ],
        "examples": [
            ("全球唯一能在「髒亂差」上全面碾壓印度的國家！孟加拉經濟有多魔幻", 1_688_854),
            ("迪拜繁華表象下的吃人真相", 1_082_968),
        ],
        "trigger_words": ["碾壓", "真相", "表象下", "人間煉獄"],
    },

    # Crime-specific patterns (for our channel focus)
    "懸案追蹤體": {
        "formula": "[時間跨度] + [懸念] + [未解/震驚] + [觀眾情感鉤]",
        "avg_views": 847_521,
        "share": "~10% of outliers",
        "templates": [
            "她失蹤了{time}，真相揭開後{reaction}",
            "{time}後終於破案，兇手竟然是{reveal}…{reaction}",
            "這個案件過了{time}，至今無人能解",
            "警察追了{time}，卻始終找不到{mystery}的真相",
            "{region}最轟動的{crime_type}，{shocking_fact}",
        ],
        "examples": [
            ("台灣最匪夷所思案件", 873_540),
            ("馬航MH370…大國博弈", 821_969),
            ("蘿莉島…愛潑斯坦根本沒死？", 1_354_176),
        ],
        "trigger_words": ["懸案", "至今", "真相", "震驚", "失蹤", "離奇"],
    },

    "獵奇反轉體": {
        "formula": "[年齡/身份反差] + [極端細節] + [制度荒誕結局]",
        "avg_views": 920_000,
        "share": "~15% of competitor outliers",
        "templates": [
            "{age}歲{identity}竟{extreme_action}，{outcome}",
            "{region}最惡毒事件！{victim}被{detail}，兇手竟{ending}",
            "{identity}活活{action}，事後竟{absurd_result}",
            "找{role}招來活閻王！{shocking_detail}",
        ],
        "examples": [
            ("12歲女孩用可樂毒殺閨蜜", 1_200_000),
            ("保姆電鋸分屍雇主，嬰兒至今下落不明", 980_000),
            ("14歲兇手挑釁警察，出獄後竟出書賺版稅", 850_000),
        ],
        "trigger_words": ["竟", "活活", "惡魔", "究竟", "甚至", "事後"],
    },

    "舊案新線體": {
        "formula": "[案件定位最XX] + [年份/最新進展] + [核心獵奇細節]",
        "avg_views": 890_000,
        "share": "~10% of competitor outliers",
        "templates": [
            "{region}{crime_type}第一懸案，{year}最新進展！",
            "失蹤{time}終於有線索，真相浮出水面後{reaction}",
            "{region}史上最{superlative}案件，至今無人敢碰",
            "{time}前的懸案，{year}終於真相大白",
            "就剛剛，{event}！全{country}轟動，{detail}",
        ],
        "examples": [
            ("中國第一懸案，2026終於有新線索", 1_100_000),
            ("消失30年的兇手，DNA技術讓真相浮出水面", 920_000),
            ("台灣史上最離奇失蹤案，至今無人敢碰", 780_000),
            ("就剛剛，FBI公布了嫌犯視頻！全美轟動", 253_281),  # UCzut 2026-04
        ],
        "trigger_words": ["最新進展", "至今未解", "終於", "浮出水面", "史上最", "就剛剛"],
    },

    # New — from 5-channel competitor analysis 2026-05-01
    # 3/3 outliers (387k, 253k, 364k views) shared this DNA: 微小荒誕誘因 → 毀滅後果
    "荒誕對比體": {
        "formula": "[微小荒誕誘因(購物卡/幾美元/想有爸爸)] + [保護者身份] + [毀滅後果] + [第三方情緒佐證]",
        "avg_views": 335_000,
        "share": "100% of 2026-04 outliers",
        "templates": [
            "為了{trivial_thing}，{protector}竟把{victim}{horror}！{authority}{reaction}",
            "{trivial_amount}換來{huge_loss}，{protector}的{shocking_action}",
            "想{innocent_wish}，{protector}卻{horror_action}，連{authority}都{reaction}",
            "{trivial_trigger}就要{victim}的命？{location}{absurd_case}全紀錄",
        ],
        "examples": [
            ("為了一張購物卡，媽媽竟把女兒送到惡魔手中！？驗屍官崩潰", 364_250),
            ("單親媽媽養兒4年，他想有個爸爸，卻在生父手中…被整沒了", 387_285),
            ("因沒付幾美元訂閱費，兇手差點消失！FBI 24小時直播", 253_281),
        ],
        "trigger_words": ["為了", "竟把", "想要", "卻在", "差點", "崩潰", "全紀錄"],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIGH-PERFORMANCE TRIGGER WORDS (from 49 outlier titles)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POWER_WORDS = {
    "冒死深扒": {"count": 3, "view_boost": "+55%"},
    "顛覆": {"count": 4, "view_boost": "+48%"},
    "年份數字": {"count": 9, "view_boost": "+44%"},
    "99%的人": {"count": 8, "view_boost": "+42%"},
    "封殺/禁封": {"count": 5, "view_boost": "+38%"},
    "真相": {"count": 21, "view_boost": "+35%"},
    "背後/幕後": {"count": 14, "view_boost": "+31%"},
    "沒人敢說": {"count": 6, "view_boost": "+28%"},
    "驚人/驚天": {"count": 12, "view_boost": "+20%"},
    # New — from competitor analysis (2026-04)
    "竟/竟然": {"count": 15, "view_boost": "+40%"},
    "活活": {"count": 6, "view_boost": "+35%"},
    "惡魔": {"count": 8, "view_boost": "+33%"},
    "細思極恐": {"count": 5, "view_boost": "+30%"},
    "至今未解": {"count": 7, "view_boost": "+28%"},
    "甚至/居然": {"count": 10, "view_boost": "+25%"},
    "最新進展": {"count": 4, "view_boost": "+22%"},
    # New — 2026-05 5-channel analysis (avg 335k outliers all use these)
    "為了": {"count": 3, "view_boost": "+45%"},      # 荒誕小因前置
    "就剛剛": {"count": 2, "view_boost": "+40%"},    # 即時感
    "崩潰/震怒": {"count": 4, "view_boost": "+33%"},  # 第三方情緒
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAILURE PATTERNS (from bottom 30 — what to AVOID)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FAILURE_PATTERNS = [
    "「震驚！」單一開頭 + 短句 → 缺乏具體人物/事件",
    "純生理/身體類話題 → 引發不適壓制點擊",
    "心理學/純科學類 → 太學術缺乏衝突",
    "標題太短（< 15字）→ 無法構建心理缺口",
    "純冷知識無爭議元素 → 不涉及觀眾切身利益",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Section names for video structure
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION_NAMES = {
    "hook": "案件開場",
    "background": "人物背景",
    "crime": "案件經過",
    "investigation": "調查過程",
    "twist": "關鍵轉折",
    "resolution": "結局揭曉",
    "reflection": "案件反思",
    "cta": "結語",
}


def get_title_prompt_insert() -> str:
    """Return Title DNA guidance for Claude/Gemini prompt injection."""
    lines = ["=== 標題 DNA 公式（從腦洞烏托邦 252萬訂閱頻道 49 部爆款影片提取）===\n"]
    for name, data in TITLE_DNA.items():
        lines.append(f"【{name}】(平均觀看 {data['avg_views']:,})")
        lines.append(f"  公式：{data['formula']}")
        for tmpl in data['templates'][:2]:
            lines.append(f"  模板：{tmpl}")
        for title, views in data['examples'][:2]:
            lines.append(f"  實例：{title} → {views:,} views")
        lines.append("")

    lines.append("【高效觸發詞（必須至少使用 1 個）】")
    for word, info in POWER_WORDS.items():
        lines.append(f"  「{word}」觀看加成 {info['view_boost']}")

    lines.append("\n【必須避免的失敗模式】")
    for f in FAILURE_PATTERNS[:3]:
        lines.append(f"  ❌ {f}")

    lines.append("\n【標題長度硬性規定】")
    lines.append("  ⚠️ 標題必須 ≤25 個中文字（含標點）。根據頻道數據分析：")
    lines.append("  短標題(≤25字) 平均 46 views vs 長標題(>40字) 平均 21 views。")
    lines.append("  絕對禁止超過 30 字。寧可精煉用詞，不要塞太多資訊。")
    lines.append("  好的例子：「林宅血案」(4字)、「台灣林于如保險金殺人案」(11字)")
    lines.append("  壞的例子：「陳金火案：2003年駭人聽聞的殺人分屍焚屍案其殘忍手法...」(54字)")

    lines.append("\n【標題自檢清單（生成後必須通過全部）】")
    lines.append("  ✅ 包含至少 1 個高效觸發詞")
    lines.append("  ✅ ≤25 字（含標點）")
    lines.append("  ✅ 不是「案件名：說明」的冒號格式")
    lines.append("  ✅ 製造好奇缺口（讀完標題想知道更多）")
    lines.append("  ✅ 有身份/年齡/數字等具體細節（不要太抽象）")
    lines.append("  ✅ 禁止用「震驚」單獨開頭")
    lines.append("  ✅ **強烈建議**：含具體數字 OR 台灣地名/機構（@mystery2018 367k 中位數的關鍵）")

    lines.append("\n【2026-05 競品爆款共同 DNA（3 個 outlier 全中）】")
    lines.append("  📌 荒誕小因前置：把案件中最荒誕、最不成比例的微小細節放標題前半")
    lines.append("     範例：「為了一張購物卡，媽媽把女兒…」(364k views)")
    lines.append("  📌 保護者反轉：父母/老師/醫生/警察當加害者時，標題要明示身份落差(用「竟」「卻」)")
    lines.append("  📌 第三方情緒佐證：用「驗屍官崩潰」「全美轟動」比直接寫殘忍更有衝擊")

    return "\n".join(lines)
