"""One entry per model across routes, the route chosen by the user's order.

The same model reached through several routes is one entrant. Entries are matched by a canonical id made from
the model id: route and maker prefixes dropped, `.` `-` `_` and letter/digit joins read alike, Venice's dotless
versions read with the dot its name shows ('openai-gpt-62-sol' is GPT-6.2 Sol), a trailing '.0' dropped; tags
such as `:free`, `:batch` and `-fast` stay, so those remain entries of their own.

Kept apart even under one canonical id:
- a free tier is a model of its own, never merged with the paid model of the same name: Zen's
  `-free` reads as the `:free` tag, so Zen's and OpenRouter's free tiers of one model are one entry;
- an uncensored build Venice serves under the plain id is tagged `:uncensored` (kind 2);
- dated builds: a date in the id or name ('DeepSeek V4.1 Flash 1017', '-20251001') or OpenRouter's canonical slug
  date is the build. Routes with different dates are different entries; a route that gives no date joins the only
  dated build there is, or, when its own route lists a dated build too, the one other build (kinds 1, 11).
LM Studio models are local and never merged.

The route used is the first that offers the same model in this order: OpenCode 무료 > OpenCode Go > Anthropic API >
Venice (direct, then through the OpenCode server) > OpenRouter > OpenCode Zen paid > any other OpenCode provider.
A route that cannot serve the model now (training not allowed, too big to load) is passed over for the next.
"""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Callable, Iterable

from .base import ModelInfo

# id prefixes a route puts in front of a model's own name (Venice: 'z-ai-glm-5-3', 'openai-gpt-62-sol')
_PREFIXES = ("z-ai-", "zai-org-", "meta-llama-", "mistralai-", "deepseek-ai-", "moonshotai-", "openai-", "xiaomi-",
             "aion-labs-", "google-")
ROUTE_ORDER = ["OpenCode free", "OpenCode Go", "Anthropic", "Venice", "Venice (OpenCode)", "OpenRouter",
               "OpenCode Zen", "OpenCode", "LM Studio"]
_ISO = re.compile(r"[-_](20\d{2})-(\d{2})-(\d{2})$")
_LONG = re.compile(r"[-_]20\d{2}(\d{2})(\d{2})$")
_MMDD = re.compile(r"(?<![\d.])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?![\d.])")


def route_name(m: ModelInfo) -> str:
    """The route as the user names it."""
    r, p = m.ref.route, m.ref.provider
    if r == "opencode":
        if p == "opencode-go":
            return "OpenCode Go"
        if p == "opencode":
            return "OpenCode free" if m.free else "OpenCode Zen"
        if p == "venice":
            return "Venice (OpenCode)"
        return "OpenCode"
    return {"anthropic": "Anthropic", "venice": "Venice", "openrouter": "OpenRouter", "lmstudio": "LM Studio"}.get(r, r)


def rank(m: ModelInfo) -> int:
    name = route_name(m)
    return ROUTE_ORDER.index(name) if name in ROUTE_ORDER else len(ROUTE_ORDER)


def _venice(m: ModelInfo) -> bool:
    return m.ref.route == "venice" or m.ref.route == "opencode" and m.ref.provider == "venice"


def date_of(m: ModelInfo) -> str:
    """The build date the id or the name gives, as MMDD; '' when neither does."""
    ident = m.ref.id.lower().split(":")[0]
    for pat in (_ISO, _LONG):
        got = pat.search(ident)
        if got:
            return got.group(got.lastindex - 1) + got.group(got.lastindex)
    for text in (ident.split("/")[-1], m.name):
        got = _MMDD.search(re.sub(r"\d+(\.\d+)+", " ", text))  # '4.1' is a version, never a date
        if got:
            return got.group(1) + got.group(2)
    return ""


def snapshot(m: ModelInfo) -> str:
    return date_of(m) or m.snapshot


def canon(m: ModelInfo, uncensored_ids: frozenset[str] = frozenset()) -> str:
    """The canonical id without the build date (see snapshot)."""
    if m.ref.route == "lmstudio":
        return "lmstudio:" + m.ref.id
    ident = m.ref.id.lower().split("/")[-1].lstrip("~")
    if m.ref.route == "opencode" and m.ref.provider in ("opencode", "opencode-go") and ident.endswith("-free") \
            and ":" not in ident:  # Zen's free tier: the :free tag
        ident = ident[: -len("-free")] + ":free"
    tag = ""
    if ":" in ident:
        ident, tag = ident.split(":", 1)
    if _venice(m):
        for major, minor in re.findall(r"(\d+)\.(\d+)", m.name):
            ident = re.sub(rf"(?<![\d.]){major}{minor}(?![\d.])", f"{major}.{minor}", ident, count=1)
    for pre in _PREFIXES:
        if ident.startswith(pre):
            ident = ident[len(pre):]
    ident = _LONG.sub("", _ISO.sub("", ident))
    ident = re.sub(r"(?<![\d.])(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?![\d.])", "", ident)  # '-1017'
    ident = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", "-", ident)  # 'qwen3.8' → 'qwen-3.8'
    parts = [w for w in re.split(r"[-._\s]+", ident) if w and not (w.isdigit() and len(w) >= 6)]
    if len(parts) >= 2 and parts[-1] == "0" and parts[-2].isdigit():  # 'mistral-large-4-0' is Mistral Large 4
        parts = parts[:-2] if parts[-2] == "1" else parts[:-1]  # 'muse-wonder-1.0' is Muse Wonder
    if m.uncensored or _venice(m) and m.ref.id in uncensored_ids:
        tag = f"{tag}+uncensored" if tag else "uncensored"
    return "-".join(parts) + (f":{tag}" if tag else "")


def paid_canon(c: str) -> str | None:
    """The canonical id of the paid model a free tier is the free tier of, None for a paid model."""
    base = c.split("@")[0]
    return base[: -len(":free")] if base.endswith(":free") else None


def _same_route(a: ModelInfo, b: ModelInfo) -> bool:
    return a.ref.route == b.ref.route and a.ref.provider == b.ref.provider


NEAR = 3 * 86400  # two routes' release dates this close name the same build


def _builds(group: list[ModelInfo]) -> list[tuple[str, list[ModelInfo]]]:
    """Split one canonical id into its dated builds.

    A date in the id or name is the build. OpenRouter's slug date is when OpenRouter added the model, so it marks
    a build only beside a dated sibling on OpenRouter itself ('deepseek-v4.1-flash' of 0910 next to
    'deepseek-v4.1-flash-1017'); alone it says nothing ('claude-opus-4.5' of 1124 is Anthropic's 20251101).
    A model with no date joins the build whose route lists it within three days of its own release date, else
    the one other build when its own route lists a dated build too, else the only build; otherwise it stays an
    entry of its own, so a fallback never crosses builds."""
    strong = {id(m): date_of(m) for m in group}
    dated: dict[str, list[ModelInfo]] = {}
    undated: list[ModelInfo] = []
    for m in group:
        s = strong[id(m)]
        if not s and m.snapshot and any(_same_route(m, x) and strong[id(x)] for x in group):
            s = m.snapshot
        (dated.setdefault(s, []) if s else undated).append(m)
    if not dated or not undated:
        return list(dated.items()) or [("", group)]
    alone: list[ModelInfo] = []
    for m in undated:
        near = {s: min(abs(m.created - x.created) for x in ms if x.created) for s, ms in dated.items()
                if m.created and any(x.created for x in ms)}
        close = [s for s, d in near.items() if d <= NEAR]
        own = {s for s, ms in dated.items() if any(_same_route(x, m) for x in ms)}
        rest = [s for s in dated if s not in own]
        if close:
            dated[min(close, key=lambda s: near[s])].append(m)
        elif len(rest) == 1 and (own or len(dated) == 1):
            dated[rest[0]].append(m)
        else:  # its own route lists the only dated build, or several builds could be it
            alone.append(m)
    out = [(s, ms) for s, ms in dated.items()]
    return out + ([("", alone)] if alone else [])


def merge(models: Iterable[ModelInfo], usable: Callable[[ModelInfo], bool] = lambda m: True) -> list[ModelInfo]:
    """Entries in first-seen order of their canonical id. Each entry is a copy of the chosen route's model with
    `alts` holding the other routes' keys, best first; every input model is the entry or one of its alts."""
    models = list(models)
    unc = frozenset(m.ref.id for m in models if m.ref.route == "venice" and m.uncensored)
    groups: dict[str, list[ModelInfo]] = {}
    for m in models:
        groups.setdefault(canon(m, unc), []).append(m)
    out = []
    for c, group in groups.items():
        builds = _builds(group)
        for snap, members in builds:
            # a route that is retiring the model or gives no price comes after the routes that still serve it
            ordered = sorted(members, key=lambda m: (not usable(m), bool(m.retiring) or m.status == "가격 모름", rank(m)))
            best = ordered[0]
            seen = {best.key}
            alts = [m.key for m in ordered[1:] if not (m.key in seen or seen.add(m.key))]
            made = [x.created for x in members if x.created]
            key = c if len(builds) == 1 else (f"{c.split(':')[0]}@{snap or 'undated'}" + (f":{c.split(':', 1)[1]}" if ":" in c else ""))
            name = best.name
            if len(builds) > 1 and snap and not date_of(best):  # two builds never show one name
                name = f"{name} {snap}"
            out.append(replace(best, name=name, alts=alts, canon=key, created=min(made) if made else 0,
                               special=any(x.special for x in members), snapshot=snap or best.snapshot))
    return out


def keys_of(entry: ModelInfo) -> list[str]:
    """Every route key an entry stands for, chosen first."""
    return [entry.key] + list(entry.alts)


def index(entries: Iterable[ModelInfo]) -> dict[str, ModelInfo]:
    """Any route key (without its effort) → the entry it belongs to."""
    return {k: e for e in entries for k in keys_of(e)}
