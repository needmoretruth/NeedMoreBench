"""any count of any role in 직접, refused only when unplayable, and every role working duplicated."""
from __future__ import annotations

import pytest

from nmb.engine.abilities import in_mafia_team
from nmb.engine.lineups import counted_lineup
from nmb.engine.roles import COMPLEX, GAME_ROLES, MAFIA, ROLES, SIMPLE
from nmb.engine.setup import GameSetup, SeatSpec, playable
from nmb.engine.prompts import rules_text

from .helpers import run_game, seats


def custom(kind: str, n: int, counts: dict[str, int], **kw) -> GameSetup:
    return GameSetup(kind=kind, seats=seats(n), role_mode="custom", counts=counts, **kw)


def test_one_mafia_nine_police_plays_as_set() -> None:
    s = custom(SIMPLE, 10, {"마피아": 1, "경찰": 9}, seed=2, max_nights=3)
    assert s.problem() is None
    g, log = run_game(s)
    assert sorted(p.start_role for p in g.players) == ["경찰"] * 9 + ["마피아"]
    checks = {e.actor for e in g.events if e.kind == "action" and e.data["role"] == "경찰" and e.day == 1}
    assert len(checks) == 9  # every police checks on the first night
    assert "경찰 9명" in log[0][2]  # the lineup is public in the rules


def test_citizens_fill_the_rest_and_seat_choices_still_count() -> None:
    assert counted_lineup({"마피아": 2, "의사": 3}, 8) == ["마피아", "마피아", "의사", "의사", "의사", "시민", "시민", "시민"]
    assert counted_lineup({"마피아": 1}, 6, ["연인"]).count("연인") == 2  # a pair even when one seat asks
    s = custom(SIMPLE, 7, {"마피아": 1, "경찰": 2})
    s.seats[3].role = "의사"
    g, _ = run_game(s)
    assert g.players[3].start_role == "의사" and sorted(p.start_role for p in g.players).count("경찰") == 2


@pytest.mark.parametrize("counts,why", [
    ({"경찰": 3}, "No one is on the mafia team"),
    ({"마피아": 7}, "No one is outside the mafia team"),
    ({"마피아": 2, "경찰": 6}, "More roles than players"),
])
def test_only_unplayable_lineups_are_refused(counts: dict[str, int], why: str) -> None:
    assert custom(SIMPLE, 7, counts).problem() == why
    assert custom(SIMPLE, 7, {"마피아": 5}).problem() is None  # lopsided is allowed: the win chance shows it
    assert custom(COMPLEX, 8, {"마피아": 1, "연인": 3}).problem() == "Lovers come in pairs"
    assert custom(COMPLEX, 8, {"스파이": 1, "경찰": 2}).problem() is None  # a helper is on the mafia team


DUP = [r for r in GAME_ROLES[COMPLEX] if playable(r) and r != "시민"]


@pytest.mark.parametrize("role", DUP)
def test_every_role_works_duplicated(role: str) -> None:
    n = 10
    counts = {"마피아": 3} if role == "마피아" else {"마피아": 2, role: 4 if role == "연인" else 3}
    if ROLES[role].team == MAFIA and role != "마피아":
        counts = {"마피아": 1, role: 3}
    for seed in (1, 2, 3):
        s = custom(COMPLEX, n, counts, seed=seed, max_nights=4)
        assert s.problem() is None
        g, log = run_game(s)
        assert g.result is not None and g.result["team"] in ("시민", "마피아")
        assert sorted(p.start_role for p in g.players).count(role) == counts[role]
        for seat, _k, system, user in log:  # no one's prompt names another's private role result
            assert "(너만 앎)" not in system


def test_duplicates_each_act() -> None:
    def fn(game, p, req):
        if req.kind == "mafia" and req.field:
            town = [q for q in game.alive() if q.role == "복수자"]
            return {"say": "", "target": town[0].name} if town else None
        if req.kind == "night" and p.role == "의사":  # each doctor guards someone else, never an avenger
            others = [q for q in game.alive() if q is not p and not in_mafia_team(q) and q.role != "복수자"]
            return {"target": others[p.seat % len(others)].name}
        return None

    s = custom(COMPLEX, 9, {"마피아": 2, "의사": 3, "복수자": 2}, seed=5, max_nights=3)
    g, _ = run_game(s, fn)
    docs = {e.actor for e in g.events if e.kind == "action" and e.data["role"] == "의사" and e.day == 1}
    assert len(docs) == 3  # every doctor protects
    shots = [e for e in g.events if e.kind == "death" and e.data.get("cause") == "avenger"]
    avengers_killed = [e for e in g.events if e.kind == "death" and e.data.get("role") == "복수자" and e.data.get("cause") == "mafia"]
    assert len(avengers_killed) == 2 and len(shots) == 2  # each avenger killed at night shoots back


def test_rules_tell_the_counts_in_the_simple_game() -> None:
    s = custom(SIMPLE, 8, {"마피아": 1, "의사": 3}, seed=1, max_nights=1)
    g, _ = run_game(s)
    text = rules_text(g)
    assert "마피아 1명" in text and "의사 3명" in text and "시민 4명" in text and "각자 자기 능력" in text


def test_default_lineups_unchanged() -> None:
    s = GameSetup(kind=SIMPLE, seats=[SeatSpec(model_key="test:t/m") for _ in range(7)], counts={"마피아": 5})
    assert s.problem() is None  # counts are kept but unused until 직접 is chosen
    g, _ = run_game(GameSetup(kind=SIMPLE, seats=seats(7), seed=1, max_nights=1, counts={"경찰": 5}))
    assert sorted(p.start_role for p in g.players) == ["경찰", "마피아", "마피아", "시민", "시민", "시민", "의사"]
