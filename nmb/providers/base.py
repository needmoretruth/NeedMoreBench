"""What every route (LM Studio, OpenCode, Anthropic API, OpenRouter) gives the app."""
from __future__ import annotations

import time
from ..i18n import _
from dataclasses import dataclass, field
from typing import Protocol

ROUTE_LABEL = {"opencode": "OpenCode", "openrouter": "OpenRouter", "anthropic": "Anthropic API", "venice": "Venice",
               "lmstudio": "LM Studio"}


@dataclass(frozen=True)
class ModelRef:
    route: str  # opencode | openrouter | anthropic | lmstudio
    provider: str  # the provider id inside the route (opencode-go, opencode, venice, ...); same as route otherwise
    id: str
    variant: str | None = None  # reasoning effort or similar, as the route names it

    @property
    def key(self) -> str:
        return f"{self.route}:{self.provider}/{self.id}" + (f"#{self.variant}" if self.variant else "")

    @staticmethod
    def parse(key: str) -> "ModelRef":
        route, rest = key.split(":", 1)
        rest, _, variant = rest.partition("#")
        provider, _, mid = rest.partition("/")
        return ModelRef(route, provider, mid, variant or None)


@dataclass
class ModelInfo:
    ref: ModelRef
    name: str
    maker: str | None = None
    country: str | None = None
    price_in: float = 0.0  # USD per 1M tokens
    price_out: float = 0.0
    context: int = 0
    free: bool = False
    trains: bool = False  # the provider may train on what it is sent
    variants: list[str] = field(default_factory=list)  # effort levels this route accepts for the model, low to high
    status: str = ""
    created: int = 0  # when the route lists the model as released or added (epoch seconds), 0 when it does not say
    snapshot: str = ""  # a dated build the route names ('1017' of DeepSeek V4.1 Flash 1017), as MMDD
    retiring: str = ""  # the route marks the model deprecated or ending (a date when it gives one)
    beta: bool = False  # the route marks the model as a beta
    special: bool = False  # not a chat model (a classifier, search, translation or screen agent)
    uncensored: bool = False  # the route serves a build with refusals taken out
    # set on merged entries: the other routes' keys for the same model, best first
    alts: list[str] = field(default_factory=list)
    canon: str = ""

    @property
    def key(self) -> str:
        return self.ref.key


class ProviderError(Exception):
    """reason: auth | credit | rate_limit | invalid | overloaded | network | provider | refused (the app will not
    send it: training, too big) | declined (the model or its safety filter refused this request)"""

    def __init__(self, reason: str, message: str = "", status: int | None = None, retry_after: float | None = None):
        super().__init__(message or reason)
        self.reason = reason
        self.status = status
        self.retry_after = retry_after

    @property
    def retryable(self) -> bool:
        return self.reason in ("rate_limit", "overloaded", "network", "provider", "keyring")


STATUS_TEXT = {"auth": "Wrong key", "credit": "No credit", "rate_limit": "Too many requests",
               "network": "No connection", "off": "Turned off", "nokey": "No key", "missing": "Not installed",
               "keyring": "Could not read the keyring", "ok": "Connected"}


@dataclass
class Completion:
    text: str
    ms: int
    tokens_in: int
    tokens_out: int
    estimated: bool  # token counts guessed from characters (the route gave none)
    cost: float
    # the model's own reasoning when its route returns it: kept for the record and the 추론 view, never put
    # into any prompt. summarized: Anthropic's official summary, not the raw trace.
    reasoning: str = ""
    summarized: bool = False
    reasoning_tokens: int | None = None


def estimate_tokens(text: str) -> int:
    """About two characters per token for mixed Korean and English; good enough to show a cost."""
    return max(1, round(len(text) / 2))


def cost_of(info: ModelInfo | None, tin: int, tout: int) -> float:
    if info is None:
        return 0.0
    return (tin * info.price_in + tout * info.price_out) / 1_000_000


class Route(Protocol):
    name: str

    async def models(self) -> list[ModelInfo]: ...

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1200) -> Completion: ...

    async def status(self) -> tuple[str, str]: ...  # (code, text) for the settings page


class Timer:
    def __init__(self) -> None:
        self.t = time.monotonic()

    @property
    def ms(self) -> int:
        return int((time.monotonic() - self.t) * 1000)
