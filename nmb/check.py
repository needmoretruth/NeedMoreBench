"""The check before a game starts: every distinct model in the lineup gets one tiny request, all at
once, and each seat comes back ready or with its problem in plain words and the fixes that apply.

No GTK here; the lobby shows the result (ui/check.py). Free models cost nothing; a paid one a few tokens.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from .engine.setup import GameSetup, SeatSpec
from .pools import USER, pool_keys, pool_models
from .providers.base import ModelRef, ProviderError
from .providers.health import Problem, classify, words
from .providers.registry import Routes

PROBE_TIMEOUT = 40.0
PROBE_TOKENS = 20
PROBE_THINK_TOKENS = 1200  # above OpenRouter's smallest thinking budget (1024)


@dataclass
class SeatCheck:
    index: int  # place in setup.seats
    key: str  # the model key the seat will use
    name: str
    state: str = "checking"  # checking | ready | problem
    problem: Problem | None = None
    text: str = ""  # the problem in plain words
    other_route: str | None = None  # the same model through the next route, ready to use
    paid: str | None = None  # a free tier's paid twin, offered with its price
    replace_pool: str = "all"  # where 바꾸기 draws from
    replace_user: dict | None = None  # a saved pool's filters when the seat drew from one
    fixes: list[str] = field(default_factory=list)  # route | paid | replace
    looking: str = ""  # "" | finding | shown: the 다른 모델 list
    picks: list["Candidate"] = field(default_factory=list)


async def probe(routes: Routes, key: str) -> ProviderError | None:
    """One tiny call. None when the model answered."""
    ref = ModelRef.parse(key)
    try:
        route = routes.route(ref)
        # with the effort level the seat will play at, so a level the route does not take shows here and not in
        # the game; room for a short think, since a budget above the tokens asked is
        # refused by some routes
        thinking = ref.variant not in (None, "none", "minimal")
        await asyncio.wait_for(route.complete(ref, "", "Reply with the single word OK.",
                                              PROBE_THINK_TOKENS if thinking else PROBE_TOKENS), PROBE_TIMEOUT)
    except asyncio.TimeoutError:
        return ProviderError("timeout", "no answer in time")
    except ProviderError as e:
        return e
    except Exception as e:  # noqa: BLE001  any broken answer is a problem for this seat, not a crash
        return ProviderError("provider", str(e)[:300])
    return None


def draw(setup: GameSetup, routes: Routes, allow_repeat: bool, rng: random.Random | None = None,
         user_pools: dict[str, dict] | None = None) -> GameSetup:
    """A copy of the setup with every 랜덤 seat drawn now, so the check covers the models that will play. The
    pool stays on the seat, so 같은 설정으로 다시 draws again."""
    from .runner import fill_seats
    s = GameSetup.from_json(setup.to_json())
    pools = pool_keys(routes.entries(), routes.usable, user_pools)
    fill_seats(s, routes, pools, rng or random.Random(), allow_repeat, strict=False)
    return s


def seats_to_check(setup: GameSetup, routes: Routes, user_pools: dict[str, dict] | None = None) -> list[SeatCheck]:
    out = []
    for i, s in enumerate(setup.seats):
        if s.kind != "ai" or not s.model_key:
            continue
        info = routes.info(s.model_key)
        name = s.model_name or (info.name if info else ModelRef.parse(s.model_key).id)
        pool = s.pool or ("free" if info is not None and info.free else "all")
        user = (user_pools or {}).get(pool[len(USER):]) if pool.startswith(USER) else None
        if pool.startswith(USER) and user is None:  # a saved pool deleted since: the pools the routes give now
            pool = "free" if info is not None and info.free else "all"
        out.append(SeatCheck(i, s.model_key, name, replace_pool=pool, replace_user=user))
    return out


async def run(routes: Routes, checks: list[SeatCheck], fresh: bool = False) -> list[SeatCheck]:
    """Probe each distinct model once (one that answered in the last minutes is not asked again) and fill
    every seat's state, words and fixes."""
    keys = sorted({c.key for c in checks})
    todo = [k for k in keys if fresh or not routes.health.recently_ok(k)]
    got = await asyncio.gather(*(probe(routes, k) for k in todo))
    errors = dict(zip(todo, got))
    for k, err in errors.items():
        if err is None:
            routes.health.ok(k)
        else:
            routes.health.learn(k, err)
    for c in checks:
        settle(routes, c, errors.get(c.key))
    return checks


def settle(routes: Routes, c: SeatCheck, err: ProviderError | None) -> None:
    info = routes.info(c.key)
    known = routes.problem(info) if info is not None else None
    if err is None and (known is None or known.kind == "busy"):
        c.state, c.problem, c.text, c.fixes, c.other_route, c.paid = "ready", None, "", [], None, None
        return
    p = classify(err) if err is not None else known
    c.state, c.problem = "problem", p
    c.text = words(c.name, p, ModelRef.parse(c.key).route) if p is not None else ""
    variant = ModelRef.parse(c.key).variant
    others = routes.others(c.key)
    c.other_route = routes.with_effort(others[0], variant) if others else None
    twin = routes.paid_twin(c.key) if c.other_route is None else None
    c.paid = routes.with_effort(twin, variant) if twin else None
    c.fixes = (["route"] if c.other_route else []) + (["paid"] if c.paid else []) + ["replace"]


def _pool(routes: Routes, c: SeatCheck) -> list:
    if c.replace_user is not None:
        return pool_models(routes.entries(), "user", routes.usable, c.replace_user)
    return pool_models(routes.entries(), c.replace_pool, routes.usable)


@dataclass
class Candidate:
    key: str
    name: str
    seated: bool  # another seat already plays this model


async def candidates(routes: Routes, setup: GameSetup, c: SeatCheck, rng: random.Random | None = None,
                     batch: int = 6) -> list[Candidate]:
    """다른 모델: models from the seat's pool that answered just now, for the user to pick from.
    Nothing is put in by itself. Models already in the lineup are listed last and marked, so two seats share a
    model only when the user picks that."""
    rng = rng or random.Random()
    seated = {ModelRef.parse(s.model_key).id for i, s in enumerate(setup.seats) if s.model_key and i != c.index}
    own = ModelRef.parse(c.key).id
    pool = [m for m in _pool(routes, c) if routes.problem(m) is None and m.ref.id != own]
    fresh = [m for m in pool if m.ref.id not in seated]
    picks = rng.sample(fresh, min(batch, len(fresh)))
    got = await asyncio.gather(*(probe(routes, m.key) for m in picks))
    out = []
    for m, err in zip(picks, got):
        if err is None:
            routes.health.ok(m.key)
            out.append(Candidate(routes.with_effort(m.key, None), m.name, False))
        else:
            routes.health.learn(m.key, err)
    out.sort(key=lambda x: x.name.lower())
    taken = [m for m in pool if m.ref.id in seated and routes.health.recently_ok(m.key)]
    return out + [Candidate(routes.with_effort(m.key, None), m.name, True) for m in sorted(taken, key=lambda m: m.name.lower())]


def apply(setup: GameSetup, routes: Routes, c: SeatCheck, key: str) -> None:
    """Put `key` in the checked seat (keeping its pool, role, effort choice and expert switch). The name follows
    the route's own catalog ('DeepSeek V4.1 Flash Free' on Zen is 'DeepSeek V4.1 Flash' on Go)."""
    s: SeatSpec = setup.seats[c.index]
    info = routes.info(key)
    s.model_key = key
    if info is not None:
        s.model_name, s.maker, s.country = info.name, info.maker, info.country
    s.variant = ModelRef.parse(key).variant
    c.key, c.name = key, s.model_name or c.name
    c.state, c.problem, c.text, c.fixes, c.other_route, c.paid = "checking", None, "", [], None, None
    c.looking, c.picks = "", []
