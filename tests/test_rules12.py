"""call names, 귓속말 시간, one call per player at a time, time limit, append-only prompts, compaction."""
from __future__ import annotations

import asyncio
import random
from collections import Counter

from nmb.engine.game import Game
from nmb.engine.names import call_names
from nmb.engine.prompts import build_prompt
from nmb.engine.setup import GameSetup, SeatSpec, seat_players
from nmb.harness import AIController
from nmb.providers.base import Completion, ModelInfo, ModelRef

from .helpers import run_game, seats


def test_call_names_short_and_distinct() -> None:
    got = call_names(["DeepSeek V4.1 Flash 1017", "GLM-5.3-Flash", "Qwen3.8 Flash", "MiMo-V2.6-Flash",
                      "MiniMax M3.1 Flash", "Claude Haiku 5.5", "GPT-6 Luna"])
    assert got == ["DeepSeek", "GLM", "Qwen", "MiMo", "MiniMax", "Claude", "GPT"]
    assert call_names(["Claude Haiku 5.5", "Claude Opus 5.5"]) == ["Claude Haiku", "Claude Opus"]
    assert call_names(["DeepSeek V4.1 Flash", "DeepSeek V4 Pro"]) == ["DeepSeek Flash", "DeepSeek Pro"]
    assert call_names(["DeepSeek V4.1 Flash", "DeepSeek V4.1 Flash"]) == ["DeepSeek A", "DeepSeek B"]
    assert call_names(["GLM 5", "GLM 5.1"]) == ["GLM 5", "GLM 5.1"]


def test_named_game_uses_one_name_everywhere() -> None:
    s = seats(7)
    s[6] = SeatSpec(kind="human", human_name="")
    g, log = run_game(GameSetup(kind="simple", seats=s, seed=3))
    names = [p.name for p in g.players]
    assert names[:6] == ["DeepSeek", "GLM", "Claude", "GPT", "Qwen", "MiniMax"] and names[6] == "Human"
    _, _, system, user = log[0]
    assert "이 이름은 게임 내내 바뀌지 않는다" in system
    assert "2. GLM (GLM-5.3-Flash, Z.ai, 중국)" in user  # call name, then the full model line


def test_whispers_only_in_whisper_time() -> None:
    def chatty(game, p, req):
        others = req.whisper_to
        if req.whispers and others:
            return {"whispers": [{"to": o, "text": f"{p.name}→{o}"} for o in others]}  # asks for more than allowed
        return None

    g, log = run_game(GameSetup(kind="simple", seats=seats(8), seed=5), chatty)
    assert not any(k == "discuss" and "whispers" in u.split("답 형식")[-1] for _, k, _, u in log)
    steps: dict[int, str] = {}
    step = ""
    for e in g.events:
        if e.kind == "step":
            step = e.text
        steps[e.id] = step
    whispers = [e for e in g.events if e.kind == "whisper"]
    assert whispers and all(steps[e.id] == "귓속말 시간" for e in whispers)
    by_day: dict[int, list] = {}
    for e in whispers:
        by_day.setdefault(e.day, []).append(e)
    for day, ws in by_day.items():
        firsts: dict[int, int] = {}
        replies: Counter[tuple[int, int]] = Counter()
        for e in ws:
            if e.actor not in firsts:
                firsts[e.actor] = e.target
            else:
                replies[(e.actor, e.target)] += 1
        senders_to: dict[int, set[int]] = {}
        for a, t in firsts.items():
            senders_to.setdefault(t, set()).add(a)
        for (a, t), n in replies.items():
            assert n == 1 and t in senders_to.get(a, set()), "a reply goes once, only to someone who whispered"


def test_one_call_per_player_at_a_time() -> None:
    running: Counter[int] = Counter()
    worst: Counter[int] = Counter()

    class Slow:
        async def decide(self, game, p, req):
            running[p.seat] += 1
            worst[p.seat] = max(worst[p.seat], running[p.seat])
            await asyncio.sleep(0.001)
            running[p.seat] -= 1
            return {req.field: random.choice(req.options)} if req.field and req.options else {}

    setup = GameSetup(kind="simple", seats=seats(10), seed=8, max_nights=3)  # complex once its abilities land
    rng = random.Random(8)
    players = seat_players(setup, rng)
    g = Game(setup, players, {p.seat: Slow() for p in players}, rng=rng)
    asyncio.run(g.run())
    assert worst and max(worst.values()) == 1


def test_prompt_prefix_is_append_only() -> None:
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=9))
    for seat in range(7):
        users = [u for st, _, _, u in log if st == seat]
        heads = [u.split("\n\n지금: ")[0] for u in users]
        for a, b in zip(heads, heads[1:]):
            assert b.startswith(a), "the roster and log part of a prompt only grows"


class FakeRoute:
    name = "fake"

    def __init__(self, memory: bool = True, delay: float = 0.0):
        self.memory = memory
        self.delay = delay
        self.calls: list[str] = []

    def info(self, ref):
        return ModelInfo(ref, "Fake", context=0)

    async def complete(self, ref, system, user, max_tokens=1200):
        self.calls.append(user)
        if self.delay:
            await asyncio.sleep(self.delay)
        if user.startswith("기억 정리"):
            return Completion('{"memory": "내 기억: 첫날 GLM이 수상했다."}' if self.memory else "몰라", 5, 10, 10, False, 0.0)
        return Completion('{"say": "' + "오늘 누가 수상한지 차근차근 따져 봐요. " * 5 + '"}', 5, 10, 10, False, 0.0)


def _ai_game(route: FakeRoute, **kw) -> Game:
    setup = GameSetup(kind="simple", seats=seats(7), seed=4, max_nights=2, **kw)
    rng = random.Random(4)
    players = seat_players(setup, rng)
    ctrl = {p.seat: AIController(route, ModelRef("fake", "fake", f"m{p.seat}")) for p in players}
    g = Game(setup, players, ctrl, rng=rng)
    asyncio.run(g.run())
    return g


def test_compaction_by_the_model_then_engine_fallback() -> None:
    route = FakeRoute()
    g = _ai_game(route, compact_at=2000)
    done = [e for e in g.events if e.kind == "compaction"]
    assert done and all(e.data["by"] == "model" for e in done)
    p = g.players[done[-1].actor]
    assert p.memory.startswith("내 기억") and p.memory_upto == done[-1].data["upto"]
    later = [u for u in route.calls if not u.startswith("기억 정리") and "네가 정리해 둔 기억" in u]
    assert later, "after compaction the prompt carries the memory in place of the old log"

    fallback = _ai_game(FakeRoute(memory=False), compact_at=2000)
    assert any(e.kind == "compaction" and e.data["by"] == "engine" for e in fallback.events)


def test_call_time_limit_gives_the_safe_default() -> None:
    g = _ai_game(FakeRoute(delay=0.05), call_timeout=0.01)
    errors = [e for e in g.events if e.kind == "error"]
    assert errors and all(e.data["reason"] == "timeout" for e in errors)
    assert g.result is not None
