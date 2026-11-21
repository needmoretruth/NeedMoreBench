"""the ledger means the same for every team and starts with what the player knows for certain; the
notebook is one page rewritten whole, sent back once when it is too long, and every version is recorded."""
from __future__ import annotations

import asyncio
import random

from nmb.engine.abilities import in_mafia_team
from nmb.engine.game import Game
from nmb.engine.lineups import CUSTOM
from nmb.engine.roles import COMPLEX
from nmb.engine.setup import GameSetup, seat_players
from nmb.engine.state import NOTE_PAGE
from nmb.harness import AIController
from nmb.providers.base import Completion, ModelInfo, ModelRef

from .helpers import run_game, seats


def first_prompts(log: list[tuple[int, str, str, str]]) -> dict[int, str]:
    out: dict[int, str] = {}
    for seat, _kind, _system, user in log:
        out.setdefault(seat, user)
    return out


def ledger_part(user: str) -> list[str]:
    lines = user.split("\n\n")
    return next(b for b in lines if b.startswith("네 장부")).splitlines()


def test_known_teammates_start_at_zero_and_confirmed() -> None:
    g, log = run_game(GameSetup(kind="simple", seats=seats(8), seed=6, max_nights=1))
    mafia = [p for p in g.players if in_mafia_team(p)]
    assert len(mafia) >= 2
    first = first_prompts(log)
    for p in g.players:
        rows = ledger_part(first[p.seat])[1:]
        for q in g.players:
            if q is p:
                continue
            row = next(r for r in rows if r.startswith(f"- {q.name}:"))
            if p in mafia and q in mafia:
                assert row.startswith(f"- {q.name}: 의심도 0, 추정 마피아, 확인됨"), row
            else:
                assert "확인됨" not in row and "의심도 50, 추정 모름" in row, row
    told = [e for e in g.events if e.kind == "ledger" and e.data["new"].get("known")]
    assert {(e.actor, e.data["name"]) for e in told} == {(p.seat, q.name) for p in mafia for q in mafia if q is not p}
    assert all(e.to == frozenset({e.actor}) for e in told)  # nobody else sees it, a person's own ledger included


def test_lovers_know_each_other_and_police_results_stay_out() -> None:
    setup = GameSetup(kind=COMPLEX, role_mode=CUSTOM, counts={"마피아": 2, "연인": 2, "경찰": 1}, seats=seats(8),
                      seed=2, max_nights=2)
    g, log = run_game(setup)
    lovers = [p for p in g.players if p.start_role == "연인" or p.role == "연인"]
    assert len(lovers) == 2
    first = first_prompts(log)
    a, b = lovers
    assert f"- {b.name}: 의심도 0, 추정 연인, 확인됨" in first[a.seat]
    police = [p for p in g.players if p.start_role == "경찰" or p.role == "경찰"]
    told = {(e.actor, e.data["name"]) for e in g.events if e.kind == "ledger" and e.data["new"].get("known")}
    assert not any(seat == police[0].seat for seat, _ in told)  # a result only the police knows is not filled in


def test_the_suspicion_sentence_is_the_same_for_every_team() -> None:
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=3, max_nights=1))
    heads = {ledger_part(user)[0] for user in first_prompts(log).values()}
    assert len(heads) == 1
    head = heads.pop()
    assert "이 사람이 너와 다른 팀일 가능성" in head and "0은 확실히 같은 팀" in head and "100은 확실히 다른 팀" in head
    assert "믿음" not in head and "의심" not in head.replace("의심도", "")
    assert {in_mafia_team(p) for p in g.players} == {True, False}


class PageRoute:
    """Answers with the pages given, one per call, and keeps every prompt."""
    name = "fake"

    def __init__(self, pages: list[str]):
        self.pages = pages
        self.calls: list[str] = []

    def info(self, ref):
        return ModelInfo(ref, "Fake", context=0)

    async def complete(self, ref, system, user, max_tokens=1200):
        page = self.pages[min(len(self.calls), len(self.pages) - 1)]
        self.calls.append(user)
        return Completion('{"say": "", "notes": "' + page + '"}', 5, 10, 10, False, 0.0)


def ask_once(pages: list[str]) -> tuple[Game, PageRoute]:
    setup = GameSetup(kind="simple", seats=seats(6), seed=1)
    rng = random.Random(1)
    players = seat_players(setup, rng)
    route = PageRoute(pages)
    ctrl = {p.seat: AIController(route, ModelRef("fake", "fake", "m")) for p in players}
    g = Game(setup, players, ctrl, rng=rng)
    from nmb.engine.turn import TurnRequest

    async def go() -> None:
        g.loop = asyncio.get_running_loop()
        await g.ask(players[0], TurnRequest("discuss", "말한다", say=True))
    asyncio.run(go())
    return g, route


def test_notes_over_the_limit_are_sent_back_once() -> None:
    g, route = ask_once(["가" * (NOTE_PAGE + 50), "짧게 줄인 노트"])
    assert len(route.calls) == 2 and "1,200자 이하로 줄여라" in route.calls[1]
    assert g.players[0].notebook.page == "짧게 줄인 노트"
    g, route = ask_once(["가" * (NOTE_PAGE + 50), "나" * (NOTE_PAGE + 1)])
    assert len(route.calls) == 2  # once only: the second long page is not asked again and not kept
    assert g.players[0].notebook.page == ""
    assert not any(e.kind == "note" for e in g.events)


def test_a_page_replaces_the_previous_one_and_every_version_is_recorded() -> None:
    g, _route = ask_once(["첫 장"])
    p = g.players[0]
    g.apply_common(p, {"notes": "둘째 장\n줄을 바꿔 쓴다"})
    assert p.notebook.page == "둘째 장\n줄을 바꿔 쓴다"
    g.apply_common(p, {"say": "노트는 그대로"})  # notes left out: the page stays
    assert p.notebook.page == "둘째 장\n줄을 바꿔 쓴다"
    versions = [e for e in g.events if e.kind == "note" and e.actor == p.seat]
    assert [e.text for e in versions] == ["첫 장", "둘째 장\n줄을 바꿔 쓴다"]
    assert [e.data["version"] for e in versions] == [1, 2] and all(e.to == frozenset({p.seat}) for e in versions)
    from nmb.engine.prompts import build_prompt
    from nmb.engine.turn import TurnRequest
    _system, user = build_prompt(g, p, TurnRequest("discuss", "말한다", say=True))
    assert "둘째 장\n줄을 바꿔 쓴다" in user and "첫 장" not in user.replace("둘째 장", "")
    assert all("둘째 장" not in build_prompt(g, q, TurnRequest("discuss", "말한다", say=True))[1] for q in g.players[1:])
