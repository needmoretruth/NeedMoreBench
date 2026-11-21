"""a playing person speaks whenever they want in 토론. A line typed while a model answers goes in right
after that model, ahead of named replies and hands, and the person is never starved."""
from __future__ import annotations

import asyncio

from nmb.engine.game import Game
from nmb.engine.setup import GameSetup, SeatSpec
from nmb.engine.state import Event, Player
from nmb.engine.turn import TurnRequest
from nmb.harness import HumanController

from .helpers import run_game, seats


def setup_with_person(n: int = 8) -> GameSetup:
    sp = seats(n)
    sp[0] = SeatSpec(kind="human", human_name="나")
    return GameSetup(seats=sp, seed=11, turns_per_player=2)


def test_typed_line_lands_right_after_the_current_speaker() -> None:
    typed: list[tuple[str, str]] = []  # (model that was answering, the person's line)
    asked: list[TurnRequest] = []

    def fn(game: Game, p: Player, req: TurnRequest) -> dict | None:
        if p.kind == "human":
            asked.append(req)
            return {"say": ""} if req.kind == "discuss" else None
        if req.kind != "discuss":
            return None
        # every model names another model, so replies alone could fill the whole discussion (the 2026-11-21 case)
        others = [q for q in game.alive() if q is not p and q.kind != "human"]
        if game.day <= 2 and game.players[0].alive and len(typed) < 6:
            line = f"내 말 {len(typed) + 1}"
            game.queue_line(0, line)  # the person types while this model is answering
            typed.append((p.name, line))
        return {"say": f"{others[0].name}님 생각은 어때요?", "hand": 3}

    g, _log = run_game(setup_with_person(), fn)
    says = [e for e in g.events if e.kind == "say"]
    assert typed, "the person never typed"
    for model, line in typed:
        i = next(k for k, e in enumerate(says) if e.actor == 0 and e.text == line)
        assert says[i - 1].actor == g.by_name(model).seat, f"{line} did not follow {model}"
    queued = [e for e in g.events if e.kind == "queued" and not e.data.get("dropped")]
    assert all(e.to == frozenset({0}) and not e.log for e in queued)  # nobody else sees it
    for req in asked:
        if req.kind == "discuss":
            assert req.limit > 0  # a reply turn has a time bar


def test_person_named_gets_a_reply_turn_with_who_named_them() -> None:
    got: list[TurnRequest] = []

    def fn(game: Game, p: Player, req: TurnRequest) -> dict | None:
        if p.kind == "human":
            if req.kind == "discuss":
                got.append(req)
                return {"say": "저요? 저는 시민입니다."}
            return None
        if req.kind == "discuss":
            return {"say": f"{game.players[0].name}님 어떻게 생각해요?", "hand": 1}
        return None

    run_game(setup_with_person(6), fn)
    assert any(r.named_by for r in got)


def test_person_turn_passes_when_time_runs_out() -> None:
    async def go() -> tuple[dict, list[Event]]:
        events: list[Event] = []
        sp = setup_with_person(4)
        from nmb.engine.setup import seat_players
        import random
        players = seat_players(sp, random.Random(1))
        h = HumanController()
        g = Game(sp, players, {0: h}, sink=events.append)
        req = TurnRequest("discuss", "토론", say=True, limit=0.05)
        return await h.decide(g, players[0], req), events

    obj, events = asyncio.run(go())
    assert obj == {}
    assert [e.kind for e in events] == ["human_turn", "human_done"]


def test_line_outside_discussion_or_from_a_model_seat_is_ignored() -> None:
    g, _ = run_game(setup_with_person(5))
    before = len(g.events)
    g.queue_line(0, "늦은 말")  # the game is over
    g.queue_line(1, "모델 자리")
    assert len(g.events) == before and not g.queued
