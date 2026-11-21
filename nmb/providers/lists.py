"""The routes' model lists read into the app's models, one pure function per route so a test can run them over the
recorded lists (tests/data/raw). Each keeps what the route itself says about a model and guesses nothing the
route states:
- effort levels are the route's own list for that model (OpenRouter `reasoning.supported_efforts`, Venice
  `reasoningEffortOptions`, Anthropic `capabilities.effort`), never one list for every model (kind 6);
- a dated build is kept as `snapshot` (OpenRouter `canonical_slug`, a date in the id or name), so a fallback never
  swaps one build for another (kinds 1, 11);
- deprecation, expiry and beta marks are kept, and models built for something other than conversation are marked,
  so automatic picks leave them out (kind 8);
- the maker part a route writes before the name is the maker, not part of the name (kinds 4, 5);
- Venice's uncensored builds and end-to-end encrypted builds keep that in their name (kinds 2, 4).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .base import ModelInfo, ModelRef
from .catalog import efforts, maker_of, special_purpose, split_maker

DEFAULT_EFFORTS = ["low", "medium", "high"]  # a route says it takes effort but lists no levels
POLICY = "account_policy"  # OpenRouter: every endpoint of the model breaks the account's data policy
_SLUG_DATE = re.compile(r"-(20\d{2})(\d{2})(\d{2})$")


def _epoch(text: Any) -> int:
    if not text:
        return 0
    try:
        return int(datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def alias(mid: str) -> bool:
    """OpenRouter's moving aliases ('~openai/gpt-sol-latest', 'openai/gpt-chat-latest') point at whatever model is
    newest; a benchmark entrant must stay one model, so they are not offered (kind 3)."""
    return mid.startswith("~") or mid.endswith("-latest")


def parse_openrouter(data: dict, allowed: set[str] | None = None) -> list[ModelInfo]:
    """OpenRouter's `/models`; `allowed` is the account's `/models/user` (a model missing there breaks the account's
    data policy on every endpoint). Batch-only entries, routers, aliases and picture or sound makers are left out."""
    out = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        outs = (m.get("architecture") or {}).get("output_modalities") or ["text"]
        if "text" not in outs or "audio" in outs or "image" in outs:  # music and picture makers are not players
            continue
        if mid.startswith("openrouter/") or alias(mid):  # routers and aliases pick some model per call
            continue
        ends = m.get("endpoints")
        if isinstance(ends, list) and ends and "/api/v1/chat/completions" not in ends:
            continue
        p = m.get("pricing") or {}
        try:
            pin, pout = float(p.get("prompt") or 0) * 1e6, float(p.get("completion") or 0) * 1e6
        except ValueError:
            continue
        if pin < 0 or pout < 0:  # router entries with variable prices
            continue
        maker_text, name = split_maker(m.get("name") or mid)
        maker, country = maker_of(mid, name, maker_text)
        blocked = allowed is not None and mid not in allowed
        params = m.get("supported_parameters") or []
        listed = (m.get("reasoning") or {}).get("supported_efforts")
        levels = efforts(listed) if listed else (DEFAULT_EFFORTS if "reasoning" in params else [])
        slug = _SLUG_DATE.search(m.get("canonical_slug") or "")
        out.append(ModelInfo(ModelRef("openrouter", "openrouter", mid), name, maker, country, pin, pout,
                             int(m.get("context_length") or 0), free=(pin == 0 and pout == 0), trains=blocked,
                             variants=levels, status=POLICY if blocked else "", created=int(m.get("created") or 0),
                             snapshot=slug.group(2) + slug.group(3) if slug else "",
                             retiring=str(m.get("expiration_date") or ""),
                             special=special_purpose(name, str(m.get("description") or ""))))
    return out


def parse_venice(data: dict) -> list[ModelInfo]:
    """Venice's `/models?type=text`. Prices are USD per 1M tokens in `model_spec.pricing`."""
    out = []
    for m in data.get("data", []):
        spec = m.get("model_spec") or {}
        if m.get("type", "text") != "text" or spec.get("offline"):
            continue
        mid, name = m.get("id", ""), spec.get("name") or m.get("id", "")
        price = spec.get("pricing") or {}
        try:
            pin = float((price.get("input") or {}).get("usd") or 0)
            pout = float((price.get("output") or {}).get("usd") or 0)
        except (TypeError, ValueError):
            continue
        caps = spec.get("capabilities") or {}
        unc = bool(spec.get("uncensored"))
        if unc and not re.search(r"uncensored|abliterated|heretic", f"{mid} {name}", re.I) and not maker_build(mid):
            name += " Uncensored"
        if caps.get("supportsE2EE") and "e2ee" not in name.lower():
            name += " (E2EE)"
        maker, country = maker_of(mid, name)
        levels = efforts(caps.get("reasoningEffortOptions")) or (DEFAULT_EFFORTS if caps.get("supportsReasoningEffort") else [])
        dep = spec.get("deprecation") or {}
        out.append(ModelInfo(ModelRef("venice", "venice", mid), name, maker, country, pin, pout,
                             int(spec.get("availableContextTokens") or m.get("context_length") or 0),
                             free=(pin == 0 and pout == 0), trains=False, variants=levels,
                             status="" if price else "가격 모름", created=int(m.get("created") or 0),
                             retiring=str(dep.get("date") or dep.get("removesAt") or "deprecated") if dep else "",
                             beta=bool(spec.get("betaModel")), uncensored=unc and not maker_build(mid),
                             special=special_purpose(name, str(spec.get("description") or ""))))
    return out


# makers whose own models are served unfiltered: Venice marks them uncensored, but it is the maker's model, the same
# one other routes serve (Aion Labs on OpenRouter), so it is not a separate build
_UNFILTERED_MAKERS = ("aion-labs-",)


def maker_build(venice_id: str) -> bool:
    return venice_id.startswith(_UNFILTERED_MAKERS)


def parse_lmstudio(data: dict, sizes: dict[str, int], load_limit: int) -> list[ModelInfo]:
    """LM Studio's `/api/v0/models`: loaded models are always usable; one not loaded yet only when small enough
    to load safely. Embedding models are not chat models."""
    out = []
    for m in data.get("data", []):
        mid = m.get("id", "")
        if m.get("type") == "embeddings":
            continue
        loaded = m.get("state") == "loaded"
        name = mid.split("/")[-1]
        maker, country = maker_of(mid, name)
        status = "" if loaded else ("너무 커서 LM Studio에서 직접 올려야 합니다" if sizes.get(mid, 0) > load_limit else "부를 때 올림")
        out.append(ModelInfo(ModelRef("lmstudio", "lmstudio", mid), name, maker, country, 0, 0,
                             int(m.get("loaded_context_length") or m.get("max_context_length") or 0),
                             free=True, status=status))
    return out


def parse_anthropic(items: list[dict]) -> list[ModelInfo]:
    """The Models API list (as dicts). Effort levels and the input limit are per model; prices come from PRICES."""
    from .anthropic_api import PRICES
    out = []
    for m in items:
        mid = m.get("id", "")
        eff = (m.get("capabilities") or {}).get("effort") or {}
        levels = efforts([k for k, v in eff.items() if isinstance(v, dict) and v.get("supported")]) if eff.get("supported") else []
        pin, pout = PRICES.get(mid, (0.0, 0.0))
        out.append(ModelInfo(ModelRef("anthropic", "anthropic", mid), m.get("display_name") or mid, "Anthropic", "미국",
                             pin, pout, int(m.get("max_input_tokens") or 0), free=False, trains=False, variants=levels,
                             status="" if mid in PRICES else "가격 모름", created=_epoch(m.get("created_at")),
                             retiring=str(m.get("retires_at") or m.get("deprecated_at") or "")))
    return out
