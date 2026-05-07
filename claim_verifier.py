"""
Claim verifier — runs AFTER script_agent generates the script.
Extracts specific factual claims (years, person names, locations, numbers)
and checks they appear in the source case_data. Flags unverified claims
that LLM may have hallucinated.

Returns dict with `verified_ratio` and `unverified_claims` list.
If ratio falls below MIN_VERIFIED_RATIO, caller should ABORT upload
and notify Telegram for human review.
"""
import json
import re

MIN_VERIFIED_RATIO = 0.50  # below = Telegram warn for human review (not auto-abort)


# Chinese surname seed (covers ~95% of TW/CN names)
_SURNAMES = (
    "王李張劉陳楊黃趙周吳徐孫朱馬胡郭林何高梁鄭羅宋謝唐韓曹許鄧蕭"
    "馮曾程蔡彭潘袁於董余蘇葉呂魏蔣田杜丁沈姜范江傅鍾盧汪戴崔任"
    "陸廖姚方金邱夏譚韋賈鄒石熊孟秦閻薛侯雷白龍段郝孔邵史毛常萬"
    "顧賴武康賀嚴尹錢施牛洪龔湯翁倪嚴"
)

# Career/role markers — boundary signal that preceding chars are a name
_ROLE_MARKERS = (
    "先生女士男子女子受害嫌被告教授律師醫生護士警察議員市長縣長"
    "立委課長處長隊長部長校長老師學生員工員工司機店員老闆"
)


def _extract_years(text: str) -> list[str]:
    return list(set(re.findall(r"(19\d{2}|20\d{2})年", text)))


def _extract_people(text: str) -> list[str]:
    """Find 2-3 char Chinese names followed by a role marker."""
    pattern = rf"([{_SURNAMES}][一-鿿]{{1,2}})(?=[{_ROLE_MARKERS}])"
    return list(set(re.findall(pattern, text)))


def _extract_locations(text: str) -> list[str]:
    """Find city/county/district names ending in 市/縣/區/鄉/路/街.
    Negative lookbehind avoids capturing preceding char as part of name
    (e.g. avoid "燕在台北市" → only capture "台北市").
    """
    pattern = r"(?<![一-鿿])([一-鿿]{2,4}(?:市|縣|區|鄉|大學|醫院|車站))"
    matches = re.findall(pattern, text)
    stop = {"城市", "縣市", "區域", "本市", "本鄉", "本區"}
    return list(set(m for m in matches if m not in stop))


def _extract_specific_numbers(text: str) -> list[str]:
    """Find specific quantities (e.g. 17歲, 5人, 100萬元) — exclude vague ones."""
    pattern = r"(\d+(?:歲|名|人|死|傷|億|萬|千萬|公斤|公分|公尺|刀))"
    return list(set(re.findall(pattern, text)))


def verify_script_claims(script_text: str, case_data: dict) -> dict:
    """Extract claims from script and verify each appears in case_data.

    Returns:
        {
            "total": int,
            "verified": int,
            "verified_ratio": float,
            "unverified": list[{"type", "value"}],
        }
    """
    case_text = json.dumps(case_data, ensure_ascii=False)

    claims = []
    for y in _extract_years(script_text):
        claims.append({"type": "year", "value": y})
    for p in _extract_people(script_text):
        claims.append({"type": "person", "value": p})
    for loc in _extract_locations(script_text):
        claims.append({"type": "location", "value": loc})
    for n in _extract_specific_numbers(script_text):
        claims.append({"type": "number", "value": n})

    verified = []
    unverified = []
    for c in claims:
        if c["value"] in case_text:
            verified.append(c)
        else:
            unverified.append(c)

    total = len(claims)
    ratio = len(verified) / total if total > 0 else 1.0

    return {
        "total": total,
        "verified": len(verified),
        "verified_ratio": ratio,
        "unverified": unverified,
    }


def check_and_warn(script_text: str, case_data: dict, topic: str = "") -> bool:
    """Run verification and print/notify warning. Return True if safe to proceed."""
    result = verify_script_claims(script_text, case_data)
    ratio = result["verified_ratio"]
    total = result["total"]

    print(f"  [Claims] {result['verified']}/{total} 經 case_data 驗證 ({ratio:.0%})")

    if total < 5:
        print(f"  [Claims] sample 太小 (<5),跳過警示")
        return True

    if ratio >= MIN_VERIFIED_RATIO:
        return True

    # Below threshold — print first 5 unverified
    print(f"  [Claims] ⚠️ 驗證率 {ratio:.0%} < {MIN_VERIFIED_RATIO:.0%} 門檻,可能有幻想細節:")
    for u in result["unverified"][:5]:
        print(f"    - [{u['type']}] {u['value']}")

    # Telegram alert (non-blocking)
    try:
        from telegram_notify import _send_raw
        msg = (f"⚠️ <b>幻想細節警示</b>\n"
               f"案件: {topic[:40]}\n"
               f"驗證率: {ratio:.0%} ({result['verified']}/{total})\n"
               f"未驗證 claims (前 5):\n")
        for u in result["unverified"][:5]:
            msg += f"  • [{u['type']}] {u['value']}\n"
        msg += "\n建議人工審查此影片"
        _send_raw(msg)
    except Exception as e:
        print(f"  [Claims] Telegram alert failed: {e}")

    return False  # Caller decides whether to abort or just warn
