"""Tolerant reading of a model's answer and validation against the legal actions.

The engine never trusts the model: names are matched against the legal list, numbers are clamped, and
anything unknown is dropped with a reason the retry prompt can quote.
"""
from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)
_TRAILING_COMMA = re.compile(r",\s*([}\]])")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_MARKDOWN = re.compile(r"(\*\*|__|`|^#+\s*|^\s*[-*•]\s+)", re.M)
_SMART = str.maketrans({"“": '"', "”": '"'})


def first_json_object(text: str) -> dict[str, Any] | None:
    """The first balanced {...} that parses, after removing code fences and trailing commas."""
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for cand in candidates:
        for start in [i for i, ch in enumerate(cand) if ch == "{"][:8]:
            end = _balanced_end(cand, start)
            if end is None:
                continue
            raw = cand[start:end + 1]
            for attempt in (raw, _TRAILING_COMMA.sub(r"\1", raw), _TRAILING_COMMA.sub(r"\1", raw.translate(_SMART))):
                try:
                    obj = json.loads(attempt, strict=False)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    return obj
    return None


def _balanced_end(s: str, start: int) -> int | None:
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def clean_speech(text: Any, limit: int = 600) -> str:
    """Spoken text as people at a table would see it: no emoji, no markdown marks, one paragraph."""
    if not isinstance(text, str):
        return ""
    t = _EMOJI.sub("", text)
    t = _MARKDOWN.sub("", t)
    t = re.sub(r"\s*\n+\s*", " ", t).strip()
    t = t.strip('"').strip()
    return t[:limit]


def _norm(name: str) -> str:
    n = re.sub(r"\s+", "", str(name)).lower()
    for suffix in ("님", "씨"):
        if n.endswith(suffix) and len(n) > len(suffix):
            n = n[: -len(suffix)]
    return n


def match_name(value: Any, names: list[str]) -> str | None:
    """Exact or forgiving match of a player name ('민지님', ' 민지 ', '3. 민지')."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = re.sub(r"^\s*\d+[.)]\s*", "", value)
    nv = _norm(v)
    table = {_norm(n): n for n in names}
    if nv in table:
        return table[nv]
    hits = [n for k, n in table.items() if k and (k in nv or nv in k)]
    return hits[0] if len(hits) == 1 else None


SKIP_WORDS = {"기권", "없음", "아무도", "아무도없음", "none", "abstain", "skip", "pass", "nobody", "null", ""}


def is_skip(value: Any) -> bool:
    return value is None or (isinstance(value, str) and _norm(value) in SKIP_WORDS)


def read_ledger(raw: Any, others: list[str], guesses: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Valid ledger edits and the problems found (for the observer, not a retry)."""
    edits, problems = [], []
    if isinstance(raw, dict):
        raw = [dict(v, name=k) if isinstance(v, dict) else {"name": k, "suspicion": v} for k, v in raw.items()]
    if not isinstance(raw, list):
        return edits, problems
    for item in raw[:20]:
        if not isinstance(item, dict):
            continue
        name = match_name(item.get("name") or item.get("player") or item.get("이름"), others)
        if name is None:
            problems.append(f"장부에 없는 이름: {item.get('name')}")
            continue
        edit: dict[str, Any] = {"name": name}
        s = item.get("suspicion", item.get("의심도"))
        if s is not None:
            try:
                edit["suspicion"] = max(0, min(100, int(round(float(s)))))
            except (TypeError, ValueError):
                problems.append(f"의심도가 숫자가 아님: {s}")
        g = item.get("guess", item.get("추정"))
        if isinstance(g, str) and g.strip():
            gm = _match_guess(g, guesses)
            if gm:
                edit["guess"] = gm
        n = item.get("note", item.get("비고"))
        if isinstance(n, str):
            edit["note"] = clean_speech(n, 80)
        if len(edit) > 1:
            edits.append(edit)
    return edits, problems


def _match_guess(g: str, guesses: list[str]) -> str | None:
    g = g.strip()
    if g in guesses:
        return g
    for opt in guesses:
        if opt != "모름" and opt in g:
            return opt
    if any(w in g for w in ("모름", "모르", "?", "unknown")):
        return "모름"
    return None


def read_notes(raw: Any) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {"add": [], "edit": [], "delete": []}
    if not isinstance(raw, dict):
        if isinstance(raw, list):
            raw = {"add": raw}
        else:
            return out
    for t in (raw.get("add") or [])[:5] if isinstance(raw.get("add"), list) else []:
        if isinstance(t, str) and t.strip():
            out["add"].append(clean_speech(t, 400))
    for e in (raw.get("edit") or [])[:5] if isinstance(raw.get("edit"), list) else []:
        if isinstance(e, dict) and isinstance(e.get("text"), str):
            try:
                out["edit"].append((int(e.get("id")), clean_speech(e["text"], 400)))
            except (TypeError, ValueError):
                pass
    for d in (raw.get("delete") or [])[:10] if isinstance(raw.get("delete"), list) else []:
        try:
            out["delete"].append(int(d))
        except (TypeError, ValueError):
            pass
    return out


def read_whispers(raw: Any, allowed: list[str], limit: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return out
    for w in raw:
        if len(out) >= limit or not isinstance(w, dict):
            continue
        to = match_name(w.get("to"), allowed)
        text = clean_speech(w.get("text"), 400)
        if to and text:
            out.append((to, text))
    return out


def read_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "예", "네", "공개")
    return False
