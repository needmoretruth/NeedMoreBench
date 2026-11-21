"""Anthropic API direct: the official SDK, key from the keyring, models from the Models API.

Effort per seat goes in `output_config.effort`. The SDK's own retries are off; the harness retries at
most twice per call (billed service). Models with adaptive thinking are asked for Anthropic's official summary of
it (`thinking.display: "summarized"`); the summary is kept for the record and never sent back to any model.
A `refusal` stop is a refused call, never retried with other words.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from .base import Completion, ModelInfo, ModelRef, ProviderError, Timer
from .lists import parse_anthropic
from ..i18n import _

# USD per 1M tokens (input, output), from the Claude API model notes read 2026-11-21. An id missing here gets
# status 가격 모름 and is never counted as free (the automatic bench only spends on free models).
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-haiku-4-5-20251001": (1.0, 5.0),
          "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0),
          "claude-opus-5-5": (4.0, 20.0), "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0),
          "claude-opus-4-7": (5.0, 25.0), "claude-opus-4-6": (5.0, 25.0), "claude-opus-4-5-20251101": (5.0, 25.0),
          "claude-fable-5-2": (8.0, 40.0), "claude-fable-5-1": (10.0, 50.0), "claude-fable-5": (10.0, 50.0)}


def adaptive(model_id: str) -> bool:
    """Adaptive thinking exists from the 4.6 generation on (Opus, Sonnet, Haiku 5.5, Fable); older ids take none."""
    m = re.match(r"claude-[a-z]+-(\d+)(?:-(\d))?(?:-|$)", model_id)
    if not m:
        return False
    major, minor = int(m.group(1)), int(m.group(2) or 0)
    return (major, minor) >= (4, 6)


def _client(key: str, base_url: str | None = None, http_client: Any = None) -> Any:
    import anthropic  # imported only when this route is used
    return anthropic.AsyncAnthropic(api_key=key, max_retries=0, timeout=240, base_url=base_url, http_client=http_client)


def _map(e: Exception) -> ProviderError:
    import anthropic
    msg = str(getattr(e, "message", "") or e)[:300]
    low = msg.lower()
    if isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return ProviderError("auth", _("{who}: wrong key").format(who="Anthropic"), getattr(e, "status_code", None))
    if "credit balance" in low or "billing" in low:
        return ProviderError("credit", _("{who}: no credit").format(who="Anthropic"), getattr(e, "status_code", None))
    if isinstance(e, anthropic.RateLimitError):
        return ProviderError("rate_limit", msg, 429)
    if isinstance(e, anthropic.APIConnectionError):
        return ProviderError("network", msg)
    if isinstance(e, anthropic.InternalServerError) or getattr(e, "status_code", 0) in (529, 503):
        return ProviderError("overloaded", msg, getattr(e, "status_code", None))
    if isinstance(e, anthropic.BadRequestError):
        return ProviderError("invalid", msg, 400)
    return ProviderError("provider", msg, getattr(e, "status_code", None))


class AnthropicRoute:
    name = "anthropic"
    label = "Anthropic API"

    def __init__(self, key: Callable[[], str | None]):
        self._key = key
        self._info: dict[str, ModelInfo] = {}
        self.base_url: str | None = None  # tests point these at a fake server
        self.http_client: Any = None

    def _c(self, key: str) -> Any:
        return _client(key, self.base_url, self.http_client)

    def _need_key(self) -> str:
        key = self._key()
        if not key:
            raise ProviderError("nokey", _("No Anthropic key"))
        return key

    def info(self, ref: ModelRef) -> ModelInfo | None:
        return self._info.get(ModelRef(ref.route, ref.provider, ref.id).key)

    async def models(self) -> list[ModelInfo]:
        key = self._need_key()
        try:
            client = self._c(key)
            items = [m async for m in client.models.list(limit=100)]
        except ProviderError:
            raise
        except Exception as e:
            raise _map(e) from e
        out = parse_anthropic([m.model_dump() if hasattr(m, "model_dump") else dict(m) for m in items])
        self._info.update({m.ref.key: m for m in out})
        return out

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 4000) -> Completion:
        key = self._need_key()
        kwargs: dict[str, Any] = {"model": ref.id, "max_tokens": max_tokens, "system": system,
                                  "messages": [{"role": "user", "content": user}]}
        if ref.variant:
            kwargs["output_config"] = {"effort": ref.variant}
        if adaptive(ref.id):
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
        t = Timer()
        try:
            resp = await self._c(key).messages.create(**kwargs)
        except Exception as e:
            raise _map(e) from e
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        thinking = "\n\n".join(getattr(b, "thinking", "") or "" for b in resp.content if getattr(b, "type", "") == "thinking")
        if getattr(resp, "stop_reason", "") == "refusal":
            raise ProviderError("declined", _("{who}: refused to answer").format(who=ref.id))
        tin, tout = resp.usage.input_tokens, resp.usage.output_tokens
        pin, pout = PRICES.get(ref.id, (0.0, 0.0))
        return Completion(text, t.ms, tin, tout, False, (tin * pin + tout * pout) / 1e6, reasoning=thinking.strip(),
                          summarized=bool(thinking.strip()))

    async def status(self) -> tuple[str, str]:
        """The cheapest real call (Haiku, one token) tells a dead key and an empty balance apart."""
        try:
            key = self._need_key()
            await self._c(key).messages.create(model="claude-haiku-5-5", max_tokens=1,
                                               messages=[{"role": "user", "content": "1"}])
        except ProviderError as e:
            return e.reason, str(e)
        except Exception as e:
            pe = _map(e)
            if pe.reason == "invalid" and "max_tokens" in str(pe).lower():
                return "ok", _("Connected")
            return pe.reason, str(pe)
        return "ok", _("Connected")
