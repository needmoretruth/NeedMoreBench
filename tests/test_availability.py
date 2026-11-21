"""a model that cannot answer is known before it is offered, checked before a game starts, and
replaced by the same model through the next route during a game. LM Studio only by hand.

The failures are the recorded answers from the user's first game (20261121-104313-simple-4ff92b) and from
OpenRouter's own lists of 2026-11-21.
"""
from __future__ import annotations

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from nmb import check, i18n
from nmb.engine.setup import GameSetup, SeatSpec
from nmb.harness import AIController
from nmb.pools import automatic, fill_free, pool_models, preset_models
from nmb.providers.base import Completion, ModelInfo, ModelRef, ProviderError
from nmb.providers.health import Health, classify, next_utc_midnight, words
from nmb.providers.opencode import OpenCodeRoute
from nmb.providers.openai_compat import POLICY, OpenRouterRoute, _error
from nmb.providers.registry import Routes

DATA = Path(__file__).parent / "data/openrouter"
NOW = 1_795_000_000.0  # 2026-11-19 UTC, any fixed moment

# --- recorded answers -----------------------------------------------------------------------------------------
ZEN_QUOTA = httpx.Response(502, json={"reason": "rate_limit", "status": 429, "retryAfterMs": 54_000_000, "message":
                                      "Free usage limit reached. Free models work in OpenCode (https://opencode.ai); "
                                      "subscribe to OpenCode Go to keep going: https://opencode.ai/go"})
OR_POLICY = httpx.Response(404, json={"error": {"code": 404, "message": "No endpoints found matching your data policy "
                                                "(Free model training). Configure: https://openrouter.ai/settings/privacy"}})
OR_DAILY = httpx.Response(429, json={"error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day. Add 10 credits "
                                               "to unlock 1000 free model requests per day", "metadata": {"headers": {
                                                   "X-RateLimit-Reset": str(int((NOW + 7200) * 1000))}}}})
OR_BUSY = httpx.Response(429, json={"error": {"code": 429, "message": "Provider returned error: temporarily rate-limited upstream"}},
                         headers={"retry-after": "5"})


def zen_error() -> ProviderError:
    return OpenCodeRoute._error(ZEN_QUOTA)


def test_recorded_failures_are_read_as_their_kind():
    q = classify(zen_error(), NOW)
    assert q.kind == "quota" and q.until == pytest.approx(NOW + 54_000)
    assert classify(_error(OR_POLICY, "OpenRouter"), NOW).kind == "policy"
    daily = _error(OR_DAILY, "OpenRouter")
    d = classify(daily, time.time())
    assert d.kind == "quota" and d.until is not None
    b = classify(_error(OR_BUSY, "OpenRouter"), NOW)
    assert b.kind == "busy" and b.until is not None and b.until <= NOW + 300
    assert classify(ProviderError("auth", "OpenRouter: wrong key", 401), NOW).kind == "auth"
    assert classify(ProviderError("invalid", "model xyz does not exist", 404), NOW).kind == "gone"


def test_error_words_are_plain_sentences_in_both_languages():
    p = classify(zen_error(), NOW)
    kinds = ("rate_limit", "invalid", "auth", "credit", "network", "timeout", "off", "nokey", "provider", "overloaded")
    try:
        i18n.setup("ko")
        ko = words("DeepSeek", p, "opencode", now=NOW)
        pol = words("Nemotron Ultra", classify(_error(OR_POLICY, "OpenRouter")), "openrouter")
        ko_all = [words("X", classify(ProviderError(k, "m"), NOW), "openrouter") for k in kinds]
    finally:
        i18n.setup("en")
    en = words("DeepSeek", p, "opencode", now=NOW)
    assert ko.startswith("DeepSeek: 오늘 무료 사용량을 다 썼습니다.") and "에 풀립니다" in ko
    assert pol == "Nemotron Ultra: 학습을 허용해야 쓸 수 있는 무료 모델입니다"
    assert en.startswith("DeepSeek: today's free use is used up. It opens again at")
    for text in ko_all:  # a Korean sentence, never a reason code
        body = text.split(": ", 1)[1]
        assert body.endswith("니다") and not any(k in body for k in kinds), text


def test_learned_problems_survive_a_restart_and_clear_on_time(tmp_path):
    path = tmp_path / "health.json"
    h = Health(path)
    h.learn("opencode:opencode/deepseek-v4.1-flash-free#max", zen_error())
    h.learn("openrouter:openrouter/x:free", _error(OR_DAILY, "OpenRouter"))
    again = Health(path)
    assert again.problem("opencode:opencode/deepseek-v4.1-flash-free").kind == "quota"
    free_or = ModelInfo(ModelRef("openrouter", "openrouter", "other:free"), "Other", free=True)
    assert again.problem(free_or).kind == "quota"  # the account's free requests are spent for every free model
    paid_or = ModelInfo(ModelRef("openrouter", "openrouter", "paid"), "Paid")
    assert again.problem(paid_or) is None
    assert again.problem("opencode:opencode/deepseek-v4.1-flash-free", now=time.time() + 2 * 86400) is None
    again.ok("opencode:opencode/deepseek-v4.1-flash-free")
    assert Health(path).problem("opencode:opencode/deepseek-v4.1-flash-free") is None


def test_openrouter_marks_policy_blocked_models_up_front_and_drops_batch_only():
    allm, user = (DATA / "models.json").read_text(), (DATA / "models_user.json").read_text()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=user if req.url.path.endswith("/models/user") else allm)
    r = OpenRouterRoute(lambda: "k", lambda: False)
    r.transport = httpx.MockTransport(handler)
    got = {m.ref.id: m for m in asyncio.run(r.models())}
    assert "openai/gpt-5.5:batch" not in got
    ultra = got["nvidia/nemotron-3-ultra-550b-a55b:free"]
    assert ultra.status == POLICY and ultra.trains
    assert got["inclusionai/ling-3.2-flash:free"].status == ""
    routes = Routes({"openrouter": r}, allow_training=True)
    routes.set_models(list(got.values()))
    assert not routes.usable(ultra)  # the account refuses it even with the training switch on
    assert routes.problem(ultra).kind == "policy"


def test_openrouter_free_allowance_is_read_from_the_key():
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/credits"):
            return httpx.Response(200, json={"data": {"total_credits": 10, "total_usage": 1}})
        return httpx.Response(200, json={"data": {"free_model_daily_requests": {"used": 1000, "limit": 1000, "remaining": 0}}})
    r = OpenRouterRoute(lambda: "k", lambda: False)
    r.transport = httpx.MockTransport(handler)
    routes = Routes({"openrouter": r})
    asyncio.run(routes.statuses())
    assert r.free_left == 0
    free = ModelInfo(ModelRef("openrouter", "openrouter", "a:free"), "A", free=True)
    assert routes.problem(free).kind == "quota"


# --- a small world of routes ------------------------------------------------------------------------------------
class Fake:
    """A route whose models answer, or fail with a recorded error."""

    def __init__(self, name: str, models: list[ModelInfo], fail: dict[str, ProviderError] | None = None):
        self.name, self._models, self.fail, self.calls = name, models, fail or {}, []
        self.info_of = {m.key: m for m in models}

    async def models(self) -> list[ModelInfo]:
        return list(self._models)

    def info(self, ref: ModelRef) -> ModelInfo | None:
        return self.info_of.get(ModelRef(ref.route, ref.provider, ref.id).key)

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1200) -> Completion:
        self.calls.append(ref.key)
        err = self.fail.get(ModelRef(ref.route, ref.provider, ref.id).key)
        if err is not None:
            raise err
        return Completion('{"say": "OK"}', 5, 1, 1, True, 0.0)

    async def status(self) -> tuple[str, str]:
        return "ok", ""


def m(route: str, provider: str, mid: str, name: str, free: bool = False, maker: str = "DeepSeek",
      country: str = "중국", variants: list[str] | None = None) -> ModelInfo:
    return ModelInfo(ModelRef(route, provider, mid), name, maker, country, 0 if free else 0.3, 0 if free else 1.2,
                     100_000, free=free, variants=variants or [])


ZEN_DS = m("opencode", "opencode", "deepseek-v4.1-flash-free", "DeepSeek V4.1 Flash Free", True, variants=["max"])
GO_DS = m("opencode", "opencode-go", "deepseek-v4.1-flash", "DeepSeek V4.1 Flash", variants=["low", "high"])
OR_DS = m("openrouter", "openrouter", "deepseek/deepseek-v4.1-flash", "DeepSeek V4.1 Flash")
OR_LING = m("openrouter", "openrouter", "inclusionai/ling-3.2-flash:free", "Ling 3.2 Flash", True, "inclusionAI")
OR_ERNIE = m("openrouter", "openrouter", "baidu/ernie-5.5-flash-preview:free", "ERNIE 5.5 Flash Preview", True, "Baidu")
OR_ULTRA = m("openrouter", "openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", "Nemotron 3 Ultra", True, "NVIDIA", "미국")
OR_ULTRA.status, OR_ULTRA.trains = POLICY, True
OR_GEMMA = m("openrouter", "openrouter", "google/gemma-4-31b-it:free", "Gemma 4 31B", True, "Google", "미국")
LM = m("lmstudio", "lmstudio", "lfm3-1.7b-uncensored", "lfm3-1.7b-uncensored", True, "Liquid", "미국")
LM2 = m("lmstudio", "lmstudio", "qwen3.8-4b", "qwen3.8-4b", True, "Alibaba")


def world(fail: dict[str, ProviderError] | None = None, health: Health | None = None) -> Routes:
    fail = fail or {}
    oc = Fake("opencode", [ZEN_DS, GO_DS], fail)
    orr = Fake("openrouter", [OR_DS, OR_LING, OR_ERNIE, OR_ULTRA, OR_GEMMA], fail)
    lm = Fake("lmstudio", [LM, LM2], fail)
    r = Routes({"opencode": oc, "openrouter": orr, "lmstudio": lm}, health=health)
    asyncio.run(r.models())
    return r


def test_one_entry_per_model_and_the_next_route_once_the_first_is_used_up():
    r = world()
    ds = sorted((e for e in r.entries() if e.canon.startswith("deepseek")), key=lambda e: e.canon)
    # the free tier is a model of its own: never merged with the paid model of the same name
    assert [(e.key, e.alts) for e in ds] == [(GO_DS.key, [OR_DS.key]), (ZEN_DS.key, [])]
    r.health.learn(GO_DS.key, ProviderError("credit", "OpenCode Go: no credit", 402))
    paid = r.entry(GO_DS.key)
    assert paid.key == OR_DS.key  # the next route in the user's order
    assert r.others(GO_DS.key) == [OR_DS.key]
    assert r.others(ZEN_DS.key) == [] and r.paid_twin(ZEN_DS.key) == OR_DS.key
    assert r.paid_twin(GO_DS.key) is None


def test_every_automatic_choice_skips_known_problems_and_lm_studio():
    r = world()
    r.health.learn(OR_ERNIE.key, _error(OR_POLICY, "OpenRouter"))
    entries = r.entries()
    for pool in ("all", "free", "latest"):
        keys = {x.key for x in pool_models(entries, pool, r.usable)}
        assert LM.key not in keys and LM2.key not in keys, pool
        assert OR_ULTRA.key not in keys and OR_ERNIE.key not in keys, pool
    user_pool = {"filters": {"free": True}, "include": [LM.key]}
    assert LM.key not in {x.key for x in pool_models(entries, "mine", r.usable, user_pool)}
    filled = fill_free(entries, 10, r.usable, random.Random(3))
    assert filled and not {x.key for x in filled} & {LM.key, LM2.key, OR_ULTRA.key, OR_ERNIE.key}
    for preset in ("major", "free", "china", "usa"):
        got, _missing = preset_models(entries, preset, r.usable)
        assert not {x.key for x in got} & {LM.key, LM2.key, OR_ULTRA.key, OR_ERNIE.key}, preset
    assert not automatic(LM) and automatic(OR_LING)


def test_random_seats_and_redraws_never_take_lm_studio_but_a_hand_seated_one_stays():
    r = world()
    setup = GameSetup(seats=[SeatSpec(model_key=LM.key)] + [SeatSpec(pool="free") for _ in range(5)] +
                      [SeatSpec(pool="all")])
    for seed in range(20):
        drawn = check.draw(setup, r, allow_repeat=True, rng=random.Random(seed))
        assert drawn.seats[0].model_key == LM.key
        assert all(ModelRef.parse(s.model_key).route != "lmstudio" for s in drawn.seats[1:])
        again = drawn.again()
        assert again.seats[0].model_key == LM.key and all(s.model_key is None for s in again.seats[1:])


def test_start_check_finds_each_problem_and_offers_the_fixes():
    fail = {ZEN_DS.key: zen_error(), OR_LING.key: _error(OR_BUSY, "OpenRouter")}
    r = world(fail)
    setup = GameSetup(seats=[SeatSpec(model_key=ZEN_DS.key + "#max", model_name="DeepSeek"),
                             SeatSpec(model_key=OR_LING.key, model_name="Ling"),
                             SeatSpec(model_key=OR_ERNIE.key, model_name="ERNIE"),
                             SeatSpec(model_key=OR_ERNIE.key, model_name="ERNIE")])
    checks = asyncio.run(check.run(r, check.seats_to_check(setup, r)))
    by = {c.index: c for c in checks}
    assert by[0].state == "problem" and by[0].problem.kind == "quota" and by[0].fixes == ["paid", "replace"]
    assert by[0].other_route is None  # a free tier has no other route of its own
    assert by[0].paid == GO_DS.key + "#high"  # offered by name and price: the paid model on OpenCode Go, closest effort
    assert "오늘" in by[0].text or "free use" in by[0].text
    assert by[1].state == "problem" and by[1].problem.kind == "busy"
    assert by[2].state == by[3].state == "ready"
    orr = r.routes["openrouter"]
    assert orr.calls.count(OR_ERNIE.key) == 1  # one request per distinct model
    check.apply(setup, r, by[0], by[0].paid)
    assert setup.seats[0].model_key == GO_DS.key + "#high" and setup.seats[0].model_name == "DeepSeek V4.1 Flash"
    asyncio.run(check.run(r, [by[0]]))
    assert by[0].state == "ready"
    cands = asyncio.run(check.candidates(r, setup, by[1], random.Random(1)))
    fresh = [x for x in cands if not x.seated]
    assert fresh and cands[:len(fresh)] == fresh  # the user picks; models already seated come last, marked
    assert all(ModelRef.parse(x.key).route != "lmstudio" and x.key != OR_LING.key for x in cands)
    assert [x.key for x in cands if x.seated] == [OR_ERNIE.key]  # ERNIE sits twice and just answered
    # what the check learned now shapes every chooser
    assert ZEN_DS.key not in {x.key for x in pool_models(r.entries(), "free", r.usable)}


class Table:
    """The parts of a game the controller touches."""

    class S:
        call_timeout = 30.0

    def __init__(self) -> None:
        self.setup, self.errors, self.events = self.S(), [], []

    def record_error(self, p: Any, err: Exception, attempt: int, text: str | None = None, **data: Any) -> None:
        self.errors.append((getattr(err, "reason", ""), text))

    def observe(self, kind: str, text: str = "", actor: int | None = None, **data: Any) -> None:
        self.events.append((kind, text, data))


class P:
    name, seat = "DeepSeek", 0


def test_mid_game_the_same_model_goes_on_through_the_next_route():
    r = world({GO_DS.key: ProviderError("credit", "OpenCode Go: no credit", 402)})
    ref = ModelRef.parse(GO_DS.key + "#high")
    ctl = AIController(r.route(ref), ref, routes=r)
    table = Table()
    comp = asyncio.run(ctl.call(table, P(), "s", "u"))
    assert comp.text
    assert ctl.ref.route == "openrouter"  # Go without credit, OpenRouter answers
    routes = [e for e in table.events if e[0] == "route"]
    assert len(routes) == 1 and routes[0][2]["new"].startswith("openrouter:")
    assert "OpenRouter" in routes[0][1] and "OpenCode Go: no credit" not in routes[0][1]  # plain words, not the raw error
    assert r.health.problem(GO_DS.key).kind == "credit"


def test_mid_game_a_used_up_free_tier_never_turns_into_the_paid_model():
    r = world({ZEN_DS.key: zen_error()})
    ref = ModelRef.parse(ZEN_DS.key + "#max")
    ctl = AIController(r.route(ref), ref, routes=r)
    table = Table()
    with pytest.raises(ProviderError):
        asyncio.run(ctl.call(table, P(), "s", "u"))
    assert ctl.ref == ref and not [e for e in table.events if e[0] == "route"]
    assert r.health.problem(ZEN_DS.key).kind == "quota"


def test_mid_game_with_no_route_left_the_default_applies_in_plain_words():
    r = world({OR_LING.key: _error(OR_POLICY, "OpenRouter")})
    ref = ModelRef.parse(OR_LING.key)
    ctl = AIController(r.route(ref), ref, routes=r)
    table = Table()
    with pytest.raises(ProviderError):
        asyncio.run(ctl.call(table, P(), "s", "u"))
    shown = [t for _r, t in table.errors if t]
    assert len(shown) == 1 and "training" in shown[0] and "invalid" not in shown[0]
    assert next_utc_midnight(NOW) > NOW


def test_a_policy_blocked_seat_reaches_the_check_instead_of_stopping_the_start():
    r = world()
    setup = GameSetup(seats=[SeatSpec(model_key=OR_ULTRA.key, model_name="Nemotron Ultra"), SeatSpec(pool="free")])
    drawn = check.draw(setup, r, allow_repeat=False, rng=random.Random(2))
    checks = asyncio.run(check.run(r, check.seats_to_check(drawn, r)))
    ultra = next(c for c in checks if c.key == OR_ULTRA.key)
    assert ultra.state == "problem" and ultra.problem.kind == "policy" and ultra.fixes == ["replace"]
    assert ultra.text == "Nemotron Ultra: this free model works only when training on prompts is allowed"


def test_other_model_offers_only_a_model_that_just_answered():
    r = world({OR_GEMMA.key: _error(OR_BUSY, "OpenRouter"), OR_LING.key: zen_error()})
    setup = GameSetup(seats=[SeatSpec(model_key=OR_ULTRA.key, model_name="Nemotron Ultra")])
    c = check.seats_to_check(setup, r)[0]
    c.replace_pool = "free"
    for seed in range(6):
        keys = {x.key for x in asyncio.run(check.candidates(r, setup, c, random.Random(seed)))}
        assert keys and keys <= {ZEN_DS.key, OR_ERNIE.key}, keys  # Gemma was busy and Ling used up: never offered
    assert setup.seats[0].model_key == OR_ULTRA.key  # nothing is put in by itself
    assert r.health.problem(OR_LING.key).kind == "quota"


def test_each_route_count_is_checked_and_an_empty_or_failed_route_is_named():
    r = world()
    assert r.counts() == {"opencode": (2, 2), "openrouter": (5, 5), "lmstudio": (2, 2)}
    assert r.broken() == []
    r.errors["openrouter"], r.received["openrouter"] = ProviderError("network", "down"), 0
    r.errors["lmstudio"] = ProviderError("off", "LM Studio is not running")
    assert r.broken() == ["openrouter"]  # LM Studio off is expected, not a broken route
