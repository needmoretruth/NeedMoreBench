"""Call names: one short name per seat that everyone uses for the whole game.

The user saw models call one player GLM, GLM5.3 and 글렘. In 실명 mode each seat is called by its model line's
common English name (DeepSeek, GLM, Claude ...). Two seats of one line get the shortest word of the model name
that tells them apart (Claude Haiku / Claude Opus); identical models get A, B, C.
"""
from __future__ import annotations

import re

# model line → how people write it; matched on the start of a word of the model name or id
LINES: list[tuple[str, str]] = [
    ("deepseek", "DeepSeek"), ("glm", "GLM"), ("qwen", "Qwen"), ("mimo", "MiMo"), ("minimax", "MiniMax"),
    ("claude", "Claude"), ("gpt", "GPT"), ("gemini", "Gemini"), ("gemma", "Gemma"), ("grok", "Grok"),
    ("kimi", "Kimi"), ("longcat", "LongCat"), ("hy", "Hy"), ("muse", "Muse"), ("mistral", "Mistral"),
    ("nemotron", "Nemotron"), ("llama", "Llama"), ("lfm", "LFM"), ("inkling", "Inkling"), ("step", "Step"),
    ("venice", "Venice"), ("ernie", "ERNIE"), ("seed", "Seed"), ("phi", "Phi"), ("command", "Command"),
]
NOISE = {"free", "latest", "preview", "instruct", "chat", "it", "the", "model", "uncensored", "gguf"}
_VERSION = re.compile(r"^v?\d[\d.]*[a-z]?$|^\d+(\.\d+)?[bkm]$|^a\d+b$", re.I)


def words(name: str, noise: set[str] | frozenset[str] = frozenset(NOISE)) -> list[str]:
    """'DeepSeek V4.1 Flash 1017' → ['DeepSeek', 'V4.1', 'Flash']; dates and noise words dropped."""
    out = []
    for w in re.split(r"[\s/_:\-]+", name.replace("(", " ").replace(")", " ")):
        if not w or w.lower() in noise or (w.isdigit() and len(w) >= 4):
            continue
        out.append(w)
    return out


def line_of(name: str) -> str:
    """The model line's common name; unknown lines use the first word without its version digits."""
    ws = words(name)
    for w in ws:
        low = w.lower()
        for key, shown in LINES:
            if low == key or (low.startswith(key) and not low[len(key):].isalpha()):
                return shown
    first = re.sub(r"[\d.]+.*$", "", ws[0]) if ws else ""
    return first or (ws[0] if ws else name.strip())


def _rest(name: str, line: str) -> list[str]:
    """The words after the line name; plain words first, version-like words last (Flash before V4.1)."""
    plain: list[str] = []
    vers: list[str] = []
    key = line.lower()
    for w in words(name):
        low = w.lower()
        if low == key:
            continue
        if low.startswith(key) and not low[len(key):].isalpha():  # 'GLM5.3', 'Qwen3.8': version glued on
            vers.append(w[len(key):])
            continue
        (vers if _VERSION.match(w) else plain).append(w)
    return plain + vers


def call_names(full: list[str | None], fixed: dict[int, str] | None = None) -> list[str]:
    """Call names for seats in 실명 mode. `full` is each seat's model name (None for a seat with a fixed name);
    `fixed` gives seats whose name is set (a typed human name, Human). A seat with no usable model name is
    called by its seat label (P2 ...), never '?' or empty."""
    fixed = fixed or {}
    base: list[str] = []
    for i, f in enumerate(full):
        base.append(fixed[i] if i in fixed else (line_of(f) if f and f.strip() else "") or f"P{i + 1}")
    out = list(base)
    groups: dict[str, list[int]] = {}
    for i, b in enumerate(base):
        groups.setdefault(b.lower(), []).append(i)
    for idx in groups.values():
        if len(idx) < 2:
            continue
        model_seats = [i for i in idx if i not in fixed]
        orig: dict[str, str] = {}
        for i in model_seats:
            orig.setdefault((full[i] or "").strip().lower(), full[i] or "")
        if len(orig) < 2:
            continue
        line = base[model_seats[0]]
        rests = {d: [w.lower() for w in _rest(o, line)] for d, o in orig.items()}
        for d, o in orig.items():
            tag = next((w for w in _rest(o, line) if all(w.lower() not in rests[x] for x in orig if x != d)), None)
            if tag:
                for i in model_seats:
                    if (full[i] or "").strip().lower() == d:
                        out[i] = f"{line} {tag}"
    # whatever still repeats (identical models, a typed name equal to a line name) gets A, B, C
    seen: dict[str, list[int]] = {}
    for i, n in enumerate(out):
        seen.setdefault(n.lower(), []).append(i)
    for idx in seen.values():
        if len(idx) > 1:
            for k, i in enumerate(idx):
                out[i] = f"{out[i]} {chr(ord('A') + k)}"
    return out
