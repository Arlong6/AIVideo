"""
Title DNA patterns extracted from successful Chinese true crime channels.

Based on forensic analysis of: 腦洞烏托邦, 老高與小茉, 曉涵哥來了, 魚老師
"""

# Proven title formulas with fill-in-the-blank templates
TITLE_PATTERNS = [
    # Time + Resolution (best CTR)
    "她失蹤了{time}，真相揭開後{reaction}",
    "{time}後終於破案，兇手竟然是{reveal}",
    "這個案件過了{time}，至今無人能解",
    # Authority + Failure
    "{authority}都無法破解的案件，結局讓所有人{reaction}",
    "警察追了{time}，卻始終找不到{mystery}",
    # Superlative + Mystery
    "史上最{adjective}的{crime_type}，{mystery_element}",
    "{region}最轟動的{crime_type}，{shocking_fact}",
    # Contrast / Identity Reveal
    "他白天是{positive_identity}，夜晚卻{dark_truth}",
    "看似{positive}的{person}，背後藏著{dark_truth}",
    # Detail-based Resolution
    "看似完美的犯罪，一個{detail}暴露了兇手",
    "所有證據都指向他，但真相卻{twist}",
    # Emotional Impact
    "真相揭開後，所有人都沉默了",
    "這個案件改變了{region}的法律",
    "{number}條人命，{result}",
]

# High-performing title keywords ranked by engagement
POWER_WORDS = [
    "懸案", "真相", "離奇", "震驚", "揭開", "至今",
    "竟然", "恐怖", "失蹤", "連環", "深度解析", "全程高能",
    "監控", "改變", "沉默", "心碎", "毛骨悚然",
]

# Section names for 8-part structure (Chinese)
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
    """Return title DNA guidance text to inject into Claude prompt."""
    patterns_text = "\n".join(f"  - {p}" for p in TITLE_PATTERNS[:8])
    return f"""=== 標題 DNA 公式（從百萬訂閱頻道提取）===
請從以下經過驗證的高 CTR 標題公式中選一個使用：
{patterns_text}

高效關鍵字：{'、'.join(POWER_WORDS[:12])}
"""
