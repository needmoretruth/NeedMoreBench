"""All routes in one place: which route serves a model key, and the combined model list."""
from __future__ import annotations

import asyncio
from typing import Callable

from .base import ModelInfo, ModelRef, ProviderError, Route
from .health import Health, Problem
from .opencode import OpenCodeRoute
from ..i18n import _


class Routes:
    def __init__(self, routes: dict[str, Route] | None = None, allow_training: bool = False,
                 health: Health | None = None):
        self.routes: dict[str, Route] = routes if routes is not None else {"opencode": OpenCodeRoute()}
        self.allow_training = allow_training
        self.health = health if health is not None else Health()
        self._models: dict[str, ModelInfo] = {}
        self.errors: dict[str, ProviderError] = {}
        self.received: dict[str, int] = {}  # models each route returned on the last load (check)
        self._entries: tuple[tuple[int, int, bool], list[ModelInfo]] | None = None
        self._loads = 0

    @staticmethod
    def standard(allow_training: bool = False, lmstudio_url: str = "http://127.0.0.1:1234/v1",
                 key: Callable[[str], str | None] | None = None, health: Health | None = None) -> "Routes":
        """All four routes. Keys are read from the keyring at call time, never stored here."""
        from .anthropic_api import AnthropicRoute
        from .openai_compat import LMStudioRoute, OpenRouterRoute, VeniceRoute
        if key is None:
            from .. import keys
            key = keys.get
        lookup = key
        r = Routes({}, allow_training, health)
        r.add(OpenCodeRoute())
        r.add(AnthropicRoute(lambda: lookup("anthropic")))
        r.add(VeniceRoute(lambda: lookup("venice")))
        r.add(OpenRouterRoute(lambda: lookup("openrouter"), lambda: r.allow_training))
        r.add(LMStudioRoute(lambda: lmstudio_url))
        return r

    async def statuses(self) -> dict[str, tuple[str, str]]:
        names = list(self.routes)
        got = await asyncio.gather(*(self.routes[n].status() for n in names), return_exceptions=True)
        out = {n: (g if isinstance(g, tuple) else ("provider", str(g))) for n, g in zip(names, got)}
        self.learn_statuses(out)
        return out

    def learn_statuses(self, statuses: dict[str, tuple[str, str]]) -> None:
        """Route-wide facts read up front: a wrong key, no credit, no free requests left today."""
        import time
        from .health import Problem, next_utc_midnight
        now = time.time()
        for name, (code, text) in statuses.items():
            if code == "auth":
                self.health.set(f"{name}:*", Problem("auth", now + 86400, text, now))
            elif code == "credit" and name == "openrouter":
                self.health.set("openrouter:*paid", Problem("credit", now + 3600, text, now))
        orr = self.routes.get("openrouter")
        if getattr(orr, "free_left", None) == 0:
            self.health.set("openrouter:*free", Problem("quota", next_utc_midnight(now), "free_model_daily_requests", now))

    def add(self, route: Route) -> None:
        self.routes[route.name] = route

    def route(self, ref: ModelRef) -> Route:
        if ref.route not in self.routes:
            raise ProviderError("invalid", _("No route called {route}").format(route=ref.route))
        return self.routes[ref.route]

    async def models(self, refresh: bool = False) -> list[ModelInfo]:
        """Every route's own list, one row per route and model (merge.merge makes the entries)."""
        if self._models and not refresh:
            return list(self._models.values())

        async def one(name: str, r: Route) -> list[ModelInfo]:
            try:
                got = await r.models()
                self.errors.pop(name, None)
                return got
            except ProviderError as e:
                self.errors[name] = e
                return []
            except Exception as e:  # noqa: BLE001  a broken answer must show as a broken route, not an empty one
                self.errors[name] = ProviderError("provider", str(e)[:300])
                return []

        lists = await asyncio.gather(*(one(n, r) for n, r in self.routes.items()))
        self.received = {n: len(lst) for n, lst in zip(self.routes, lists)}
        self.set_models([m for lst in lists for m in lst])
        return list(self._models.values())

    def counts(self) -> dict[str, tuple[int, int]]:
        """Per route: (models received, models reachable in the choosers through some entry)."""
        from .merge import keys_of
        reach: dict[str, int] = {}
        for e in self.entries():
            for k in keys_of(e):
                route = ModelRef.parse(k).route
                reach[route] = reach.get(route, 0) + 1
        return {n: (self.received.get(n, 0), reach.get(n, 0)) for n in self.routes}

    def broken(self) -> list[str]:
        """Routes that returned nothing or failed, leaving out the expected cases: no key stored, a program that is
        not installed, LM Studio off."""
        out = []
        for n in self.routes:
            err = self.errors.get(n)
            if err is not None and (err.reason in ("nokey", "missing") or n == "lmstudio" and err.reason == "off"):
                continue
            if err is not None or self.received.get(n, 0) == 0:
                out.append(n)
        return out

    def set_models(self, models: list[ModelInfo]) -> None:
        self._models = {m.key: m for m in models}
        self._loads += 1

    def info(self, key: str) -> ModelInfo | None:
        ref = ModelRef.parse(key)
        return self._models.get(ModelRef(ref.route, ref.provider, ref.id).key)

    def entries(self) -> list[ModelInfo]:
        """One entry per model with its best usable route chosen; made again when the lists, what the
        app has learned about availability, or the training switch change."""
        from .merge import merge
        self.health.drop_expired()
        stamp = (self._loads, self.health.version, self.allow_training)
        if self._entries is None or self._entries[0] != stamp:
            self._entries = (stamp, merge(self._models.values(), self.usable))
        return self._entries[1]

    def entry(self, key: str) -> ModelInfo | None:
        """The merged entry a route key belongs to."""
        from .merge import keys_of
        base = self.info(key)
        if base is None:
            return None
        for e in self.entries():
            if base.key in keys_of(e):
                return e
        return None

    def problem(self, m: ModelInfo) -> Problem | None:
        """Why this model cannot be used now, if it cannot."""
        from .openai_compat import POLICY
        if m.status == POLICY:
            return Problem("policy", None, m.status)
        if m.trains and not self.allow_training:
            return Problem("trains", None)
        if m.status.startswith("너무 커서"):
            return Problem("big", None, m.status)
        return self.health.problem(m)

    def usable(self, m: ModelInfo) -> bool:
        """Training models only when allowed; a big LM Studio model only when the user loaded it; nothing
        the app has learned is out of reach now. A model kept as busy for a minute still counts."""
        p = self.problem(m)
        return p is None or p.kind == "busy"

    def others(self, key: str) -> list[str]:
        """The same model through the other routes that can serve it now, in the user's order."""
        from .merge import keys_of, rank
        e = self.entry(key)
        base = self.info(key)
        if e is None or base is None:
            return []
        alts = [k for k in keys_of(e) if k != base.key]
        infos = [self.info(k) for k in alts]
        return [i.key for i in sorted((i for i in infos if i is not None and self.usable(i)), key=rank)]

    def paid_twin(self, key: str) -> str | None:
        """For a free tier, the paid model of the same name through its best usable route; None otherwise. Never
        used on its own: the user chooses it, seeing its price."""
        from .merge import NEAR, paid_canon, rank, snapshot
        e = self.entry(key)
        c = paid_canon(e.canon) if e is not None else None
        if c is None or e is None:
            return None
        twins = [x for x in self.entries() if ":" not in x.canon and x.canon.split("@")[0] == c and self.usable(x)]

        def same_build(x: ModelInfo) -> bool:
            s = snapshot(e)
            return bool(s) and s == snapshot(x) or bool(e.created and x.created and abs(e.created - x.created) <= NEAR)
        # the free tier's own build first (its date, or the routes' release dates), then the user's route order
        twins.sort(key=lambda x: (not same_build(x), rank(x)))
        return twins[0].key if twins else None

    def with_effort(self, key: str, variant: str | None) -> str:
        """`key` with the closest effort level its route offers."""
        info, ref = self.info(key), ModelRef.parse(key)
        levels = info.variants if info is not None else []
        v = None
        if levels and variant:
            ladder = ["none", "minimal", "low", "medium", "high", "xhigh", "max"]
            want = ladder.index(variant) if variant in ladder else ladder.index("medium")
            v = variant if variant in levels else min(
                levels, key=lambda x: (abs((ladder.index(x) if x in ladder else 3) - want), ladder.index(x) if x in ladder else 3))
        return ModelRef(ref.route, ref.provider, ref.id, v).key

    def check_allowed(self, key: str) -> None:
        """B3: a model that may train on what it is sent is never called while that is not allowed. Other known
        problems (a spent quota, a policy refusal the route itself enforces) do not stop a start the user chose."""
        from .openai_compat import POLICY
        m = self.info(key)
        if m is not None and m.trains and not self.allow_training and m.status != POLICY:
            raise ProviderError("refused", _("{name} trains on what it is sent; allow such models in Settings to use it").format(name=m.name))
