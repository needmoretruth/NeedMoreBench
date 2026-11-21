"""Model pools for 랜덤 seats, the ready lineup of a first open, filling seats
with free models, and the built-in lineup presets.

Every choice made here is automatic, so LM Studio models never enter it: they reach a seat
only when the user picks one by hand. Pools draw from merged entries, so each model is one candidate
whatever number of routes offer it.

계열별 최신판만 groups models by maker and the name without its version (Claude Opus, Claude Fable, DeepSeek
Flash, GLM Flash ...) and keeps the newest of each line: with Opus 5.5 present Opus 5 is hidden and Fable 5.2
still shows because it is another line. Newest is the route's own release date when both models have one, since
a version number read as a decimal misleads (Grok 4.20 came out before Grok 4.7), then the version in the name.
A size (27B, 2.4T, A3B) and an uncensored build are lines of their own, so a smaller or uncensored model never
hides the maker's plain one.
"""
from __future__ import annotations

import random
import re
from functools import cmp_to_key
from typing import Callable, Iterable

from .engine.names import _VERSION, NOISE, line_of, words
from .providers.base import ModelInfo, ModelRef
from .providers.merge import keys_of, rank

BUILTIN = ("all", "free", "latest")
# OpenCode Go models that played well in the first real games of 2026-11-21 (cheap, fast, no format problems)
READY = ["opencode:opencode-go/deepseek-v4.1-flash#low", "opencode:opencode-go/glm-5.3-flash#low",
         "opencode:opencode-go/qwen3.8-flash#none", "opencode:opencode-go/mimo-v2.6-flash",
         "opencode:opencode-go/minimax-m3.1-flash#low", "opencode:opencode-go/claude-haiku-5-5#none",
         "opencode:opencode-go/gpt-6-luna#none"]
# rough size of one seat's game, measured on the first 7-player game (15 calls, 4.7k tokens in, 0.4k out each)
CALLS_PER_SEAT, TOKENS_IN, TOKENS_OUT = 15, 4700, 400
# built-in presets: name → which makers or countries, in seat order
MAJOR = ["DeepSeek", "OpenAI", "Anthropic", "Google", "Alibaba", "Z.ai", "Moonshot AI", "xAI"]
PRESETS = {"major": "Major models", "free": "Free models", "china": "Chinese models", "usa": "American models"}


def automatic(m: ModelInfo) -> bool:
    """May an automatic choice (presets, pools, fills, the bench) take this model? Never a local LM Studio model
   never one its route is retiring or calls a beta, one built for something other than conversation, or
    one without a known price. The user can still pick any of them by hand."""
    return (m.ref.route != "lmstudio" and not m.status.startswith("너무 커서") and m.status != "가격 모름"
            and not m.retiring and not m.beta and not m.special)


_SIZE = re.compile(r"^\d+(\.\d+)?[bkmt]$|^a\d+(\.\d+)?b$", re.I)  # 27B, 2.4T, A3B
LINE_NOISE = frozenset(NOISE - {"uncensored"})  # a call name drops 'uncensored'; a line keeps it


def version_of(name: str) -> tuple[float, ...]:
    """'Claude Opus 5.5' → (5, 5); 'DeepSeek V4.1 Flash' → (4, 1); 'Qwen3.8 Flash' → (3, 8); none → ()."""
    name = re.sub(r"\d{4}-\d{2}-\d{2}", " ", name)  # 'GPT-4o (2024-11-20)': a date is not a version
    for w in words(name):
        m = re.search(r"(\d+(?:[.\-]\d+)*)([a-z]?)$", w, re.I)
        if m and (m.group(2).lower() in ("b", "k", "m", "t") or _SIZE.match(w)):  # a size such as 120b
            continue
        if m and (_VERSION.match(w) or not w[: m.start()].isdigit()):
            return tuple(float(x) for x in re.split(r"[.\-]", m.group(1)) if x)
    return ()


def line_key(m: ModelInfo) -> tuple[str, str]:
    """(maker, line words): the version digits and noise words taken out, the size and 'uncensored' kept.
    Entries are merged across routes already, so the route is not part of a line."""
    line = line_of(m.name)
    rest = []
    for w in words(m.name, LINE_NOISE):
        low = w.lower()
        if low == line.lower() or (low.startswith(line.lower()) and not low[len(line):].isalpha()):
            continue
        if low == (m.maker or "").lower():  # 'Google Gemma 4 31B' is the line of 'Gemma 4 31B'
            continue
        if _SIZE.match(w):
            rest.append(low)
            continue
        if _VERSION.match(w) or re.fullmatch(r"[\d.\-]+", w):
            continue
        rest.append(re.sub(r"[\d.]+$", "", w).lower())
    # a free tier is a line beside the paid model, so neither hides the other
    return (m.maker or "", " ".join([line.lower()] + [r for r in rest if r] + ([":free"] if m.free else [])))


def compare(a: ModelInfo, b: ModelInfo, price: bool = False) -> int:
    """Which of two models of one line is newer: the routes' release dates when both give one, then the version
    in the name; on a tie the better route, the larger model when `price`, then the plainer name."""
    if a.created and b.created and a.created != b.created:
        return 1 if a.created > b.created else -1

    def k(m: ModelInfo) -> tuple:
        return (version_of(m.name), -rank(m)) + ((m.price_in + m.price_out,) if price else ()) + (-len(m.name),)
    ka, kb = k(a), k(b)
    return (ka > kb) - (ka < kb)


def latest_only(models: Iterable[ModelInfo]) -> list[ModelInfo]:
    """The newest model of each line (see compare)."""
    best: dict[tuple[str, str], ModelInfo] = {}
    for m in models:
        k = line_key(m)
        if k not in best or compare(m, best[k]) > 0:
            best[k] = m
    return list(best.values())


# words that mark a side line (a tuned, faster, smaller or special-purpose build), not a maker's main model
SIDE = {"uncensored", "abliterated", "heretic", "aggressive", "fast", "ultrafast", "highspeed", "code", "codex",
        "coder", "vision", "vl", "omni", "oss", "safeguard", "turbo", "multi", "agent", "custom", "tools",
        "legal", "exp", "thinking", "mini", "nano", "lite", "tiny", "small", "haiku", "flash", "flashx", "air",
        "spark", "fp8", "e2ee"}


def main_model(cands: list[ModelInfo]) -> ModelInfo | None:
    """A maker's main model for 주요 모델: side lines left out when anything else is there, then the
    newest version; on a tie the better route, then the larger model (higher price), then the plainer name."""
    def side(m: ModelInfo) -> bool:
        return bool(SIDE & set(re.split(r"[\s/_:\-().]+", m.name.lower())))
    main = [m for m in cands if not side(m)] or cands
    return max(main, key=cmp_to_key(lambda a, b: compare(a, b, price=True)), default=None)


def pool_models(models: list[ModelInfo], pool: str, usable: Callable[[ModelInfo], bool] = lambda m: True,
                user: dict | None = None) -> list[ModelInfo]:
    """The entries a 랜덤 seat of `pool` may draw. `user` is a saved user pool: filters plus include/exclude
    (by any route key of an entry)."""
    ok = [m for m in models if usable(m) and automatic(m)]
    if pool == "free":
        return [m for m in ok if m.free]
    if pool == "latest":
        return latest_only(ok)
    if user is not None:
        f = user.get("filters", {})
        sel = [m for m in ok if (not f.get("free") or m.free) and (not f.get("route") or any(ModelRef.parse(k).route in f["route"] for k in keys_of(m)))
               and (not f.get("maker") or (m.maker or "") in f["maker"])]
        if f.get("latest"):
            sel = latest_only(sel)
        chosen = {m.key for m in sel}
        inc, exc = set(user.get("include", [])), set(user.get("exclude", []))
        return [m for m in ok if (m.key in chosen or inc & set(keys_of(m))) and not exc & set(keys_of(m))]
    return ok


USER = "user:"  # a seat's pool naming one of the user's saved pools: 'user:<name>'
BUILT_IN = ("all", "free", "latest")


def pool_keys(models: list[ModelInfo], usable: Callable[[ModelInfo], bool],
              user_pools: dict[str, dict] | None = None) -> dict[str, list[str]]:
    """Every pool a 랜덤 seat may name, built-in and saved, as the model keys it draws from now."""
    out = {name: [m.key for m in pool_models(models, name, usable)] for name in BUILT_IN}
    for name, d in (user_pools or {}).items():
        out[USER + name] = [m.key for m in pool_models(models, "user", usable, d)]
    return out


def fill_free(models: list[ModelInfo], n: int, usable: Callable[[ModelInfo], bool], rng: random.Random) -> list[ModelInfo]:
    """무료 모델로 채우기: n free entries, different ones first."""
    free = pool_models(models, "free", usable)
    rng.shuffle(free)
    return [free[i % len(free)] for i in range(n)] if free else []


def preset_models(models: list[ModelInfo], preset: str, usable: Callable[[ModelInfo], bool],
                  limit: int = 12) -> tuple[list[ModelInfo], list[str]]:
    """A built-in preset filled from what the routes offer now: (entries, makers left out because no route
    offers them). One model per line, the latest version, the cheapest route's line first."""
    ok = latest_only(m for m in models if usable(m) and automatic(m))
    if preset == "major":
        out, missing = [], []
        for maker in MAJOR:
            m = main_model([x for x in ok if x.maker == maker])
            (out.append(m) if m is not None else missing.append(maker))
        return out, missing
    if preset == "free":
        cands = [m for m in ok if m.free]
    elif preset == "china":
        cands = [m for m in ok if m.country == "중국"]
    else:
        cands = [m for m in ok if m.country == "미국"]
    out = []
    for maker in sorted({m.maker or "" for m in cands}):  # one per maker first, then more lines
        m = main_model([x for x in cands if (x.maker or "") == maker])
        if m is not None:
            out.append(m)
    rest = sorted((m for m in cands if m not in out), key=lambda m: (not m.free, rank(m), m.name))
    return (out + rest)[:limit], []


def seat_cost(m: ModelInfo | None) -> float:
    if m is None or m.free:
        return 0.0
    return CALLS_PER_SEAT * (TOKENS_IN * m.price_in + TOKENS_OUT * m.price_out) / 1e6
