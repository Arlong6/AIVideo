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
    """一個數值的所有可接受書寫形（含四捨五入到 0/1/2 位、絕對值）。"""
    out = set()
    for x in {v, abs(v)}:
        for nd in (0, 1, 2, 3):
            r = round(x, nd)
            s = f"{r:.{nd}f}".rstrip("0").rstrip(".") or "0"
            out.add(s)
            out.add(f"{float(s):,.{nd}f}".rstrip("0").rstrip("."))
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
            # 日期等字串：拆出所有數字片段（2026-06-10 → 2026/06/6/10）
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
