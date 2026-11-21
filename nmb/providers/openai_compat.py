"""OpenRouter and LM Studio: both speak OpenAI-style chat completions.

OpenRouter: key from the keyring; when training models are not allowed every request carries
`provider: {"data_collection": "deny"}` so only endpoints that do not keep prompts for training serve it.
LM Studio: the local server, no key; only small local models are used for tests (≤ 4 GB).
"""
from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .base import Completion, ModelInfo, ModelRef, ProviderError, Timer, answer_limit, cost_of, estimate_tokens
from . import lmstudio_ctl
from .lists import POLICY, parse_lmstudio, parse_openrouter, parse_venice  # noqa: F401  POLICY is read through this module
from .lmstudio_ctl import LOAD_LIMIT
from ..i18n import _

OPENROUTER = "https://openrouter.ai/api/v1"


def _error(r: httpx.Response, who: str) -> ProviderError:
    try:
        body = r.json()
    except ValueError:
        body = {}
    err = body.get("error") if isinstance(body, dict) else None
    msg = str((err or {}).get("message") if isinstance(err, dict) else err or r.text[:300])
    low = msg.lower()
    if r.status_code == 401 or r.status_code == 403 and "key" in low:
        return ProviderError("auth", _("{who}: wrong key").format(who=who), r.status_code)
    if r.status_code == 402 or any(w in low for w in ("insufficient credits", "credit balance", "more credits")):
        return ProviderError("credit", _("{who}: no credit").format(who=who), r.status_code)
    if r.status_code == 429:
        ra = r.headers.get("retry-after")
        wait = float(ra) if ra and ra.replace(".", "").isdigit() else None
        reset = r.headers.get("x-ratelimit-reset") or str((((err or {}) if isinstance(err, dict) else {}).get("metadata") or {})
                                                            .get("headers", {}).get("X-RateLimit-Reset", ""))
        if wait is None and reset.isdigit():  # OpenRouter: epoch milliseconds of the reset
            wait = max(0.0, int(reset) / 1000 - time.time())
        return ProviderError("rate_limit", msg, 429, wait)
    if r.status_code in (400, 404, 422):
        return ProviderError("invalid", msg, r.status_code)
    if r.status_code in (502, 503, 529):
        return ProviderError("overloaded", msg, r.status_code)
    return ProviderError("provider", msg, r.status_code)


class ChatRoute:
    """Shared chat-completions call. Subclasses give the base URL, headers and the model list."""

    name = ""
    label = ""

    def __init__(self, timeout: float = 180):
        self.timeout = timeout
        self._info: dict[str, ModelInfo] = {}
        self.transport: httpx.AsyncBaseTransport | None = None  # tests put a fake server here

    def client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=timeout, transport=self.transport)

    def base(self) -> str:
        raise NotImplementedError

    def headers(self) -> dict[str, str]:
        return {}

    def extra_body(self, ref: ModelRef) -> dict[str, Any]:
        return {}

    def info(self, ref: ModelRef) -> ModelInfo | None:
        return self._info.get(ModelRef(ref.route, ref.provider, ref.id).key)

    def limit(self, ref: ModelRef, max_tokens: int) -> int:
        return answer_limit(self.info(ref), max_tokens)

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1500) -> Completion:
        body: dict[str, Any] = {"model": ref.id, "max_tokens": self.limit(ref, max_tokens),
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        body.update(self.extra_body(ref))
        t = Timer()
        try:
            async with self.client(self.timeout) as c:
                r = await c.post(f"{self.base()}/chat/completions", json=body, headers=self.headers())
        except httpx.TimeoutException as e:
            raise ProviderError("network", _("No answer in time")) from e
        except httpx.HTTPError as e:
            raise ProviderError("network" if self.name != "lmstudio" else "off", str(e)) from e
        if r.status_code != 200:
            raise _error(r, self.label)
        data = r.json()
        if isinstance(data, dict) and data.get("error"):
            raise ProviderError("provider", str(data["error"])[:300])
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        text = msg.get("content") or ""
        if choice.get("finish_reason") == "content_filter" and not text:
            raise ProviderError("declined", _("{who}: refused to answer").format(who=ref.id))
        usage = data.get("usage") or {}
        # the model's own reasoning when the route returns it: OpenRouter `reasoning`, DeepSeek, Venice and
        # LM Studio `reasoning_content`; kept for the record only
        reasoning = str(msg.get("reasoning") or msg.get("reasoning_content") or "").strip()
        rtok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        tin, tout = usage.get("prompt_tokens"), usage.get("completion_tokens")
        estimated = tin is None or tout is None
        tin = tin if tin is not None else estimate_tokens(system + user)
        tout = tout if tout is not None else estimate_tokens(text)
        cost = usage.get("cost")
        return Completion(text, t.ms, int(tin), int(tout), estimated,
                          float(cost) if isinstance(cost, (int, float)) else cost_of(self.info(ref), tin, tout),
                          reasoning=reasoning, reasoning_tokens=rtok if isinstance(rtok, int) else None)


class OpenRouterRoute(ChatRoute):
    name = "openrouter"
    label = "OpenRouter"

    def __init__(self, key: Callable[[], str | None], allow_training: Callable[[], bool], timeout: float = 180):
        super().__init__(timeout)
        self._key = key
        self._allow_training = allow_training
        self.free_left: int | None = None  # free-model requests left today, from /key
        self.credit_left: float | None = None

    def base(self) -> str:
        return OPENROUTER

    def headers(self) -> dict[str, str]:
        key = self._key()
        if not key:
            raise ProviderError("nokey", _("No OpenRouter key"))
        return {"Authorization": f"Bearer {key}", "X-Title": "NeedMoreBench"}

    def extra_body(self, ref: ModelRef) -> dict[str, Any]:
        out: dict[str, Any] = {"usage": {"include": True}}
        if not self._allow_training():
            out["provider"] = {"data_collection": "deny"}
        if ref.variant:
            out["reasoning"] = {"effort": ref.variant}
        return out

    async def models(self) -> list[ModelInfo]:
        """The whole list, each model checked against the account's own list (`/models/user`, which leaves out
        models whose every endpoint breaks the account's data policy, such as free models that train on
        prompts). Batch-only entries are left out: they do not answer chat calls."""
        try:
            key = self._key()
        except Exception:  # noqa: BLE001  the keyring can be locked; the public list still works
            key = None
        try:
            async with self.client(30) as c:
                r = await c.get(f"{OPENROUTER}/models")
                ru = await c.get(f"{OPENROUTER}/models/user", headers={"Authorization": f"Bearer {key}"}) if key else None
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise _error(r, self.label)
        allowed: set[str] | None = None
        if ru is not None and ru.status_code == 200:
            allowed = {m.get("id", "") for m in ru.json().get("data", [])}
        out = parse_openrouter(r.json(), allowed)
        self._info.update({m.ref.key: m for m in out})
        return out

    async def status(self) -> tuple[str, str]:
        """Credit left and the day's free-model requests (`/key`: free_model_daily_requests)."""
        try:
            headers = self.headers()
            async with self.client(20) as c:
                r = await c.get(f"{OPENROUTER}/credits", headers=headers)
                rk = await c.get(f"{OPENROUTER}/key", headers=headers)
        except ProviderError as e:
            return e.reason, str(e)
        except httpx.HTTPError as e:
            return "network", str(e)
        if r.status_code != 200:
            e = _error(r, self.label)
            return e.reason, str(e)
        free = ((rk.json().get("data") or {}).get("free_model_daily_requests") or {}) if rk.status_code == 200 else {}
        self.free_left = free.get("remaining") if isinstance(free.get("remaining"), int) else None
        d = r.json().get("data") or {}
        left = float(d.get("total_credits") or 0) - float(d.get("total_usage") or 0)
        self.credit_left = left
        if left <= 0:
            return "credit", _("No credit (free models only)")
        return "ok", _("${left} credit left").format(left=f"{left:.2f}")


VENICE = "https://api.venice.ai/api/v1"


class VeniceRoute(ChatRoute):
    """Venice's OpenAI-compatible API. Prices are USD per 1M tokens in `model_spec.pricing`. Venice marks
    each model `private` (Venice keeps nothing) or `anonymized` (passed on to the maker without who sent it);
    neither says the prompts are trained on, so no Venice model is marked as training. Venice's own system
    prompt is turned off so every route gets the same prompt."""

    name = "venice"
    label = "Venice"

    def __init__(self, key: Callable[[], str | None], timeout: float = 180):
        super().__init__(timeout)
        self._key = key

    def base(self) -> str:
        return VENICE

    def headers(self) -> dict[str, str]:
        key = self._key()
        if not key:
            raise ProviderError("nokey", _("No Venice key"))
        return {"Authorization": f"Bearer {key}"}

    def extra_body(self, ref: ModelRef) -> dict[str, Any]:
        out: dict[str, Any] = {"venice_parameters": {"include_venice_system_prompt": False}}
        if ref.variant:
            out["reasoning_effort"] = ref.variant
        return out

    async def models(self) -> list[ModelInfo]:
        headers = self.headers()
        try:
            async with self.client(30) as c:
                r = await c.get(f"{VENICE}/models", params={"type": "text"}, headers=headers)
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise _error(r, self.label)
        out = parse_venice(r.json())
        self._info.update({m.ref.key: m for m in out})
        return out

    async def status(self) -> tuple[str, str]:
        try:
            models = await self.models()
        except ProviderError as e:
            return e.reason, str(e)
        return "ok", _("Models: {n}").format(n=len(models))


class LMStudioRoute(ChatRoute):
    name = "lmstudio"
    label = "LM Studio"

    def __init__(self, url: Callable[[], str], timeout: float = 300,
                 sizes: Callable[[], dict[str, int]] | None = None):
        super().__init__(timeout)
        self._url = url
        self.sizes = sizes or lmstudio_ctl.sizes

    def base(self) -> str:
        return self._url().rstrip("/")

    async def models(self) -> list[ModelInfo]:
        """Loaded models are always usable; one that is not loaded yet only when small enough to load safely."""
        root = self.base().removesuffix("/v1")
        try:
            async with self.client(5) as c:
                r = await c.get(f"{root}/api/v0/models")
        except httpx.HTTPError as e:
            raise ProviderError("off", _("The LM Studio server is off")) from e
        if r.status_code != 200:
            raise _error(r, self.label)
        out = parse_lmstudio(r.json(), self.sizes(), LOAD_LIMIT)
        self._info.update({m.ref.key: m for m in out})
        return out

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1500) -> Completion:
        info = self.info(ref)
        if info is not None and info.status.startswith("너무 커서"):
            raise ProviderError("refused", f"{info.name}: {info.status}")
        return await super().complete(ref, system, user, max_tokens)

    async def status(self) -> tuple[str, str]:
        try:
            models = await self.models()
        except ProviderError as e:
            return e.reason, str(e)
        ready = sum(1 for m in models if not m.status.startswith("너무 커서"))
        return "ok", _("Models: {n}").format(n=ready)
