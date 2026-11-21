"""말, 속마음, 추론: each route's reasoning is read, kept for the god view and the record only, never
put into a prompt; Claude seats ask for the official summary; a refusal is said plainly and never asked again."""
from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import httpx
import httpx2
import pytest

from nmb.engine.game import Game
from nmb.engine.prompts import build_prompt
from nmb.engine.setup import GameSetup, seat_players
from nmb.engine.turn import TurnRequest
from nmb.harness import AIController
from nmb.providers.anthropic_api import AnthropicRoute, adaptive
from nmb.providers.base import Completion, ModelRef, ProviderError
from nmb.providers.health import classify, words
from nmb.providers.openai_compat import OpenRouterRoute, VeniceRoute
from nmb.store import HOW_TO_READ, event_record
from nmb.view import ViewState

from .helpers import run_game, seats

ROOT = Path(__file__).resolve().parent.parent
SECRET = "I suspect seat three because their vote moved late."


def run(c):  # type: ignore[no-untyped-def]
    return asyncio.run(c)


def anthropic(handler) -> AnthropicRoute:  # type: ignore[no-untyped-def]
    r = AnthropicRoute(lambda: "sk-ant-test")
    r.base_url = "http://fake.anthropic"
    r.http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return r


def message(content: list[dict], stop: str = "end_turn") -> dict:
    return {"id": "m", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}


def test_claude_seats_ask_for_the_summary_and_keep_it() -> None:
    seen: list[dict] = []

    def ok(req: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(req.content))
        return httpx2.Response(200, json=message([{"type": "thinking", "thinking": SECRET, "signature": "sig"},
                                                  {"type": "text", "text": "{\"say\": \"네\"}"}]))
    c = run(anthropic(ok).complete(ModelRef("anthropic", "anthropic", "claude-opus-5-5", "high"), "s", "u"))
    assert seen[0]["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert c.text == "{\"say\": \"네\"}" and c.reasoning == SECRET and c.summarized


def test_older_claude_models_get_no_thinking_field() -> None:
    assert adaptive("claude-opus-5-5") and adaptive("claude-sonnet-5") and adaptive("claude-sonnet-4-6")
    assert adaptive("claude-fable-5-2") and adaptive("claude-haiku-5-5")
    assert not adaptive("claude-haiku-4-5-20251001") and not adaptive("claude-opus-4-5-20251101")
    seen: list[dict] = []

    def ok(req: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(req.content))
        return httpx2.Response(200, json=message([{"type": "text", "text": "{}"}]))
    c = run(anthropic(ok).complete(ModelRef("anthropic", "anthropic", "claude-haiku-4-5-20251001"), "s", "u"))
    assert "thinking" not in seen[0] and c.reasoning == "" and not c.summarized


def test_a_claude_refusal_is_said_plainly() -> None:
    def no(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message([], stop="refusal"))
    with pytest.raises(ProviderError) as e:
        run(anthropic(no).complete(ModelRef("anthropic", "anthropic", "claude-opus-5-5"), "s", "u"))
    assert e.value.reason == "declined" and not e.value.retryable
    p = classify(e.value)
    assert p.kind == "refused" and "refused" in words("Opus", p)


@pytest.mark.parametrize("field", ["reasoning", "reasoning_content"])
def test_chat_routes_read_the_reasoning_field(field: str) -> None:
    body = {"choices": [{"message": {"content": "{}", field: SECRET}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 50, "completion_tokens_details": {"reasoning_tokens": 40}}}
    for route in (OpenRouterRoute(lambda: "k", lambda: False), VeniceRoute(lambda: "k")):
        route.transport = httpx.MockTransport(lambda req: httpx.Response(200, json=body))
        c = run(route.complete(ModelRef(route.name, route.name, "m"), "s", "u"))
        assert c.reasoning == SECRET and c.reasoning_tokens == 40 and not c.summarized


def test_a_content_filter_stop_is_a_refusal() -> None:
    route = OpenRouterRoute(lambda: "k", lambda: False)
    route.transport = httpx.MockTransport(lambda req: httpx.Response(200, json={
        "choices": [{"message": {"content": ""}, "finish_reason": "content_filter"}], "usage": {}}))
    with pytest.raises(ProviderError) as e:
        run(route.complete(ModelRef("openrouter", "openrouter", "m"), "s", "u"))
    assert e.value.reason == "declined"


class Reasoner:
    """A route that answers with reasoning, or refuses."""
    name = "fake"

    def __init__(self, refuse: bool = False) -> None:
        self.refuse, self.calls = refuse, 0

    async def complete(self, ref, system, user, max_tokens=1200):  # type: ignore[no-untyped-def]
        self.calls += 1
        assert SECRET not in system + user  # never fed back, to this seat or any other
        if self.refuse:
            raise ProviderError("declined", "refused to answer")
        return Completion(json.dumps({"say": "안녕하세요", "thought": "조용히 본다"}), 5, 10, 5, False, 0.0,
                          reasoning=SECRET, summarized=True, reasoning_tokens=30)


def game_with(route: Reasoner) -> Game:
    setup = GameSetup(kind="simple", seats=seats(5), seed=3)
    rng = random.Random(3)
    players = seat_players(setup, rng)
    ref = ModelRef("anthropic", "anthropic", "claude-opus-5-5")
    return Game(setup, players, {p.seat: AIController(route, ref) for p in players}, rng=rng)  # type: ignore[arg-type]


def test_reasoning_is_kept_for_the_god_view_only_and_never_prompted() -> None:
    route = Reasoner()
    g = game_with(route)
    p = g.players[0]
    run(g.ask(p, TurnRequest("discuss", "토론", say=True)))
    ev = [e for e in g.events if e.kind == "reasoning"]
    assert len(ev) == 1 and ev[0].text == SECRET and ev[0].to == frozenset() and not ev[0].log
    rec = event_record(ev[0])
    assert rec["seen_by"] == "god" and rec["in_prompts"] is False
    assert rec["details"]["summarized"] is True and rec["details"]["route"] == "anthropic" and rec["details"]["tokens"] == 30
    for q in g.players:  # no prompt of any seat carries it
        system, user = build_prompt(g, q, TurnRequest("discuss", "토론", say=True))
        assert SECRET not in system + user
    run(g.ask(g.players[1], TurnRequest("discuss", "토론", say=True)))  # the next call's prompt is checked inside
    god = ViewState.from_header({"seats": [{"seat": q.seat, "name": q.name} for q in g.players]})
    seat = ViewState.from_header({"seats": [{"seat": q.seat, "name": q.name} for q in g.players]}, viewer=0)
    assert god.apply(ev[0]) and god.seats[0].reasonings[0][1] == SECRET
    assert not seat.apply(ev[0]) and not seat.seats[0].reasonings  # not even its own seat's player sees it
    assert "reasoning" in HOW_TO_READ and "summarized" in HOW_TO_READ


def test_a_refusal_is_not_asked_again() -> None:
    route = Reasoner(refuse=True)
    g = game_with(route)
    run(g.ask(g.players[0], TurnRequest("discuss", "토론", say=True)))
    assert route.calls == 1  # no retry, no other route, no reworded prompt
    err = [e for e in g.events if e.kind == "error"]
    assert err and "refused" in err[0].text and err[0].data["reason"] == "declined"


def test_no_prompt_asks_for_hidden_reasoning() -> None:
    """Nothing any model is sent could read as extracting reasoning: no request to repeat, translate or write out
    its reasoning or thinking (Anthropic's distillation classifier). Every prompt of a simple and a complex
    game, and the memory prompt of compaction, are read."""
    import inspect

    from nmb import harness
    banned = ("추론", "생각 과정", "사고 과정", "reasoning", "chain of thought", "thinking", "verbatim", "번역",
              "translate")
    texts = [inspect.getsource(harness.AIController.compact)]
    for kind, n in (("simple", 7), ("complex", 10)):
        _g, log = run_game(GameSetup(kind=kind, seats=seats(n), seed=2))
        texts += [system + user for _s, _k, system, user in log]
    for t in texts:
        hit = [b for b in banned if b in t.lower()]
        assert not hit, (hit, t[:200])
    assert any("속마음" in t for t in texts)  # the thought stays a player's own note
