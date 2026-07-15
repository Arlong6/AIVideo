"""數字對帳閘門 — 腳本裡每個阿拉伯數字必須能在數據包裡找到出處。

這是「假內容」的結構性解法：LLM 只能敘述我們給的數字。任何多出來的
數字（幻覺、誇大、記憶殘留）都會被逐 token 攔下，fail-closed 拒絕渲染。
0-10 的小整數放行（「3 個重點」這類結構性計數）。
"""
import re

_SMALL_INT_WHITELIST = set(range(0, 11))
_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


class NumberMismatch(Exception):
    pass


def _formats_of(v: float) -> set[str]:
    """一個數值的所有可接受書寫形（含四捨五入到 0-3 位、絕對值）。

    For nd > 0, adds BOTH the unstripped fixed-decimal format (e.g. "-0.10")
    and the stripped version (e.g. "-0.1"), since charts use {:+.2f} formatting.
    """
    out = set()
    for x in {v, abs(v)}:
        for nd in (0, 1, 2, 3):
            r = round(x, nd)
            s = f"{r:.{nd}f}"
            # Always add the unstripped fixed-decimal format
            out.add(s)
            # For nd > 0, also add the stripped version
            if nd > 0:
                s_stripped = s.rstrip("0").rstrip(".") or "0"
                out.add(s_stripped)

            # Same for thousand-separator versions
            comma = f"{float(s):,.{nd}f}"
            out.add(comma)
            if nd > 0:
                comma_stripped = comma.rstrip("0").rstrip(".")
                out.add(comma_stripped)
    return out


def _allowed_tokens(pack) -> set[str]:
    allowed = set()

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, bool):
            pass
        elif isinstance(v, (int, float)):
            allowed.update(_formats_of(float(v)))
        elif isinstance(v, str):
            # 只對日期形字串拆出數字片段（2026-06-10 → 2026/06/6/10）；
            # 其他敘述性字串一律忽略，避免其中數字被靜默放行。
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                for m in _TOKEN_RE.findall(v):
                    allowed.add(m)
                    allowed.add(m.lstrip("0") or "0")
    walk(pack)
    return allowed


def verify_numbers(text: str, pack: dict) -> list[str]:
    allowed = _allowed_tokens(pack)
    violations = []
    for tok in _TOKEN_RE.findall(text):
        plain = tok.replace(",", "")
        if plain in allowed or tok in allowed:
            continue
        try:
            if float(plain) in _SMALL_INT_WHITELIST and "." not in plain:
                continue
        except ValueError:
            pass
        violations.append(plain)
    return violations


def assert_numbers_ok(text: str, pack: dict) -> None:
    v = verify_numbers(text, pack)
    if v:
        raise NumberMismatch(
            f"script contains numbers with no source in the data pack: {v} "
            f"— refusing to render (fail-closed)")
