"""Korean particles for engine lines. Player names always take 님, so only role words need a choice."""
from __future__ import annotations


def has_batchim(word: str) -> bool:
    for ch in reversed(word.strip()):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isdigit():
            return ch in "013678"
        if ch.isalpha():
            return ch.lower() in "lmnr"
    return False


def josa(word: str, with_b: str, without_b: str) -> str:
    """josa('경찰', '이었', '였') → '경찰이었'."""
    return word + (with_b if has_batchim(word) else without_b)


def ro(word: str) -> str:
    """ro('의사') → '의사로', ro('시민') → '시민으로', ro('경찰') → '경찰로' (a final ㄹ takes 로)."""
    last = next((ch for ch in reversed(word.strip()) if "가" <= ch <= "힣"), "")
    if last and (ord(last) - 0xAC00) % 28 == 8:
        return word + "로"
    return josa(word, "으로", "로")


def nim(name: str) -> str:
    return f"{name}님"
