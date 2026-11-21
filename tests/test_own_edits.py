"""A person edits their own ledger and notes from the screen; the engine checks it and nobody else sees it."""
from __future__ import annotations

from nmb.engine.setup import GameSetup, SeatSpec
from nmb.pools import READY
from nmb.runner import build_game


def game_with_person():  # noqa: ANN201
    setup = GameSetup(seats=[SeatSpec(kind="human")] + [SeatSpec(model_key=k) for k in READY[:5]], seed=4)
    game, _rec, _h = build_game(setup, None, offline=True, record=False)
    events = []
    game.sink = events.append
    return game, events


def test_person_edits_own_ledger_and_notes() -> None:
    game, events = game_with_person()
    me, other = game.players[0], game.players[1]
    game.edit_own(0, {"ledger": [{"name": other.name, "suspicion": 85, "guess": "마피아", "note": "말이 바뀜"}],
                      "notes": "첫날 투표 흐름 보기"})
    row = me.ledger[other.name]
    assert (row.suspicion, row.guess, row.note) == (85, "마피아", "말이 바뀜")
    assert me.notebook.page == "첫날 투표 흐름 보기"
    mine = [e for e in events if e.kind in ("ledger", "note")]
    assert mine and all(e.to == frozenset({0}) for e in mine)
    game.edit_own(0, {"notes": "둘째 날 투표 흐름\n셋째 날 볼 것"})
    assert me.notebook.page == "둘째 날 투표 흐름\n셋째 날 볼 것"
    game.edit_own(0, {"notes": "가" * 1201})  # the screen refuses it; the engine keeps the page anyway
    assert me.notebook.page == "둘째 날 투표 흐름\n셋째 날 볼 것"
    game.edit_own(0, {"notes": ""})
    assert me.notebook.page == "" and me.notebook.version == 3


def test_checked_like_a_model() -> None:
    game, _events = game_with_person()
    me = game.players[0]
    game.edit_own(0, {"ledger": [{"name": "없는 사람", "suspicion": 99}, {"name": me.name, "suspicion": 99}]})
    assert all(r.suspicion == 50 for r in me.ledger.values())
    game.edit_own(0, {"ledger": [{"name": game.players[2].name, "suspicion": 500}]})
    assert 0 <= me.ledger[game.players[2].name].suspicion <= 100


def test_model_seats_and_finished_games_refuse() -> None:
    game, _events = game_with_person()
    bot = game.players[1]
    target = game.players[2].name
    game.edit_own(1, {"ledger": [{"name": target, "suspicion": 90}]})
    assert bot.ledger[target].suspicion == 50
    game.result = {"team": None}
    game.edit_own(0, {"notes": "늦은 메모"})
    assert not game.players[0].notebook.page
