"""
Title DNA patterns — books channel (Route B: narrative-driven book storytelling).

Hybrid extraction from 15 outlier videos scanned on 2026-04-08.
Source data: books_channel_analysis.json

Scan covered:
- 文森說書 (947K subs) → 11 outliers → 5 hook patterns (pain scene, personal
  testimony, audience command, social proof, elite-cohort question)
- 英雄說書 (340K subs) → 3 outliers → historical myth-busting pattern
  (overlaps with crime DNA 權力揭秘體)
- 啾啾鞋 (1.6M subs) → 1 outlier but it was non-book content → DROPPED from
  DNA source (not a useful signal for this channel)

The 文森 patterns teach us HOW to hook (relatable pain + book as anchor).
The 英雄 pattern teaches us WHAT to pick (dramatic historical events retold).
Combined with our existing crime channel's narrative rhythm, this becomes
the Route B hybrid: narrative-driven retelling of books, biographies, and
historical events — the same dramatic DNA as crime, different subject matter.
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TITLE DNA FORMULAS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TITLE_DNA_BOOKS = {
    "痛苦場景體": {
        "formula": "[觀眾熟悉的痛苦感受/症狀] + [反直覺的真實原因] + 《書名》錨點",
        "avg_views": 113_313,   # (100k + 102k + 437k) / 3 — up-weighted by 437k peak
        "share": "~35% of outliers",
        "templates": [
            "{pain_scene}，這不是{common_framing}，是{hidden_cause}｜《{book}》",
            "{symptom_1}、{symptom_2}，{cause}｜《{book}》",
            "{feeling_list}，這都是我們從{origin}中學到的{thing}｜《{book}》",
        ],
        "examples": [
            ("把對方當作全世界，訊息不回就焦慮，這不是愛，是潛意識在尋找熟悉的痛苦", 437_423),
            ("忽然的低潮、不想依賴別人，這都是我們從原生家庭中學到的生存方式｜《童年情感忽視》", 100_510),
            ("健身無效、記憶力退化，壓力如何搞壞我們的體質｜《壓力》", 102_415),
        ],
        "trigger_words": ["這不是", "是...", "才知道", "潛意識", "都是我們從"],
        "when_to_use": "書的核心是心理學、情感、身心健康、原生家庭、自我成長時最強",
    },

    "個人背書體": {
        "formula": "[第一人稱時間/努力證明] + [對書的超常情感或排名] + 《書名》",
        "avg_views": 171_850,  # (226k + 117k) / 2
        "share": "~20% of outliers",
        "templates": [
            "過了{time}，這本書依然是我的{superlative}｜《{book}》",
            "一本讓我{extreme_action}的書｜《{book}》",
            "這本書改變了我對{topic}的看法｜《{book}》",
            "我讀過最{adjective}的一本書｜《{book}》",
        ],
        "examples": [
            ("過了幾年，這本書依然是我的前三名｜《我生命中的一段歷險》", 226_705),
            ("一本讓我願意花兩個月讀完的書｜《童年情感忽視》", 116_994),
        ],
        "trigger_words": ["過了", "依然是", "前三名", "改變了", "願意"],
        "when_to_use": "書本身已有經典地位，用主觀情感強化說服力",
    },

    "指令閱讀體": {
        "formula": "[特定身份/職業] + 都該看 / 必讀 + 《書名》",
        "avg_views": 114_804,
        "share": "~12% of outliers",
        "templates": [
            "{identity}都該看這本書｜《{book}》",
            "{audience}必讀｜《{book}》",
            "{life_stage}的人一定要讀｜《{book}》",
            "每個{role}都該讀的一本書｜《{book}》",
        ],
        "examples": [
            ("上班的人都該看這本書｜《普通主管才是最強主管》", 114_804),
        ],
        "trigger_words": ["都該看", "必讀", "一定要", "最該", "每個"],
        "when_to_use": "書有明確的目標讀者群（職場/家長/投資人/創業者）時",
    },

    "社會認證體": {
        "formula": "[排名/銷量/權威標記] + 是有原因的 / 都推薦 + 《書名》",
        "avg_views": 169_621,
        "share": "~12% of outliers",
        "templates": [
            "這本書{ranking}是有原因的｜《{book}》",
            "{authority}都推薦｜《{book}》",
            "{prize}得主的代表作｜《{book}》",
            "暢銷{number}年，{descriptor}｜《{book}》",
        ],
        "examples": [
            ("這本書銷售第一名是有原因的｜《我可能錯了》", 169_621),
        ],
        "trigger_words": ["銷售第一", "是有原因", "都推薦", "冠軍", "暢銷"],
        "when_to_use": "書有明確排名、獎項、或廣泛的社會背書時",
    },

    "問句探秘體": {
        "formula": "那些/為什麼 + [優秀族群] + [反直覺問題] + 《書名》",
        "avg_views": 108_317,
        "share": "~12% of outliers",
        "templates": [
            "那些{elite_group}都{action}了什麼？｜《{book}》",
            "為什麼{surprising_observation}？｜《{book}》",
            "{successful_people}跟{normal_people}最大的差別｜《{book}》",
            "為什麼有些人總是能{achievement}？｜《{book}》",
        ],
        "examples": [
            ("那些高成就的人都是掌握了哪些訣竅？｜《開創心態》", 108_317),
        ],
        "trigger_words": ["那些", "都是", "訣竅", "差別", "為什麼"],
        "when_to_use": "書講的是某個菁英族群的秘訣、習慣、心態時",
    },

    # Route B 的核心 — 從英雄說書 + 真實犯罪 DNA 移植
    "歷史揭謊體": {
        "formula": "[公認常識/神話] + 質疑 / 真相 / 騙局 + [書名或歷史章節]",
        "avg_views": 91_405,  # avg of 英雄's 3 outliers
        "share": "~20% of outliers (historical route)",
        "templates": [
            "{common_belief}只是一場騙局嗎？｜《{book}》",
            "為何{entity}如此{adjective}？連{comparison}都無法超越它",
            "{historical_event}的真相比你想像的更{shocking}｜《{book}》",
            "{famous_figure}的{positive_image}，背後藏著{hidden_truth}｜《{book}》",
        ],
        "examples": [
            ("為何印度教如此強大，連佛教都無法超越它在印度的地位？", 99_191),
            ("中國「四大發明」只是一場騙局嗎？", 83_622),
            ("地表最強戰車 M1A2T 加入國軍，能替戰力帶來多大升級？", 91_841),
        ],
        "trigger_words": ["只是騙局", "為何", "連...都無法", "真相", "背後", "其實"],
        "when_to_use": "歷史題材、名人傳記、顛覆大眾認知的非小說時",
        "note": "這個公式與真實犯罪的「權力揭秘體」幾乎同源，Route B 可以混用",
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HIGH-PERFORMANCE TRIGGER WORDS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

POWER_WORDS_BOOKS = {
    "《》書名錨點": {"count": 9, "view_boost": "+40%", "note": "9/9 純書評 outlier 都用"},
    "這本書": {"count": 6, "view_boost": "+35%", "note": "文森的基石詞"},
    "為什麼/為何": {"count": 5, "view_boost": "+32%"},
    "真相/潛意識": {"count": 4, "view_boost": "+30%"},
    "過了幾年/依然": {"count": 2, "view_boost": "+28%", "note": "時間證明"},
    "都該看/必讀": {"count": 2, "view_boost": "+25%"},
    "銷售第一/暢銷": {"count": 2, "view_boost": "+25%"},
    "那些...都": {"count": 2, "view_boost": "+20%"},
    "只是騙局嗎": {"count": 1, "view_boost": "+25%", "note": "英雄的招牌 hook"},
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FAILURE PATTERNS — Things that DIDN'T become outliers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FAILURE_PATTERNS_BOOKS = [
    "純書名 + 類型 → 缺乏 hook（例：『《書名》— 自我成長書』）",
    "作者介紹優先 → 除非是 Adam Grant / Yuval Harari 級名人否則不驅動點擊",
    "摘要式標題（『3 個重點告訴你 X』）→ 內容預期太低、沒懸念",
    "書單/listicle 格式（『5 本必讀的 X 書』）→ 文森 378 支影片裡沒出現在 outlier",
    "太學術/太冷門題材 → 90% 觀眾沒聽過的主題很難突破演算法",
    "標題過短（< 12 字）→ 無法容納 hook + 書名錨點",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Section names for book-storytelling video structure (long-form)
# Maps to the existing 8-section pipeline so _generate_long_scripts() logic
# can be reused verbatim — only the semantic labels differ.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SECTION_NAMES_BOOKS = {
    "hook": "震撼開場",        # corresponds to crime's 案件開場
    "background": "時代背景",   # corresponds to crime's 人物背景
    "crime": "關鍵事件",       # corresponds to crime's 案件經過 — the central story retold
    "investigation": "揭密調查", # corresponds to crime's 調查過程 — research/unveiling
    "twist": "意外轉折",        # corresponds to crime's 關鍵轉折 — turning point / revelation
    "resolution": "結局揭曉",    # corresponds to crime's 結局揭曉 — how it ended
    "reflection": "書中洞察",    # corresponds to crime's 案件反思 — the book's core insight
    "cta": "結語書錨",          # corresponds to crime's 結語 + book-title anchor
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Prompt injection helper — matches title_dna.get_title_prompt_insert()
# so script_generator_books.py (Phase 3) can drop it in verbatim.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_title_prompt_insert() -> str:
    """Return books-channel Title DNA guidance for Claude/Gemini prompt injection."""
    lines = [
        "=== 標題 DNA 公式（從文森說書 94.7萬 + 英雄說書 34萬 outlier 逆向工程）===\n"
    ]
    for name, data in TITLE_DNA_BOOKS.items():
        lines.append(f"【{name}】(平均觀看 {data['avg_views']:,})")
        lines.append(f"  公式：{data['formula']}")
        for tmpl in data['templates'][:2]:
            lines.append(f"  模板：{tmpl}")
        for title, views in data['examples'][:2]:
            lines.append(f"  實例：{title} → {views:,} views")
        if "when_to_use" in data:
            lines.append(f"  適用：{data['when_to_use']}")
        lines.append("")

    lines.append("【高效觸發詞】")
    for word, info in list(POWER_WORDS_BOOKS.items())[:8]:
        note = f" — {info['note']}" if info.get("note") else ""
        lines.append(f"  「{word}」出現{info['count']}次，觀看加成 {info['view_boost']}{note}")

    lines.append("\n【必須避免的失敗模式】")
    for f in FAILURE_PATTERNS_BOOKS[:4]:
        lines.append(f"  ❌ {f}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Smoke test — print the generated prompt insert
    print(get_title_prompt_insert())
