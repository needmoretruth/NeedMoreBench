"""a 랜덤 lineup of 복잡한 마피아 is drawn again until the win chance fitted on recorded games is fair, once
enough games stand behind it; with few games, other lineups or no record folder the draw is plain."""
from __future__ import annotations

import json
import random
from pathlib import Path

from nmb import balance
from nmb.engine.lineups import FAIR, lineup
from nmb.engine.setup import GameSetup, SeatSpec, playable
from nmb.runner import build_game, draw_judge


def complex_setup(n: int = 10, **kw) -> GameSetup:  # noqa: ANN003
    return GameSetup(kind="complex", seats=[SeatSpec(kind="ai") for _ in range(n)], **kw)


def record(folder: Path, i: int, roles: list[str], mafia_won: bool) -> None:
    header = {"game": "complex", "seats": [{"seat": k, "model": f"opencode:x/m{k}"} for k in range(len(roles))]}
    result = {"record": "result", "team": "마피아" if mafia_won else "시민", "roles": {str(k): r for k, r in enumerate(roles)}}
    (folder / f"g{i:03}.nmb.jsonl").write_text(json.dumps(header, ensure_ascii=False) + "\n"
                                               + json.dumps(result, ensure_ascii=False) + "\n", encoding="utf-8")


def history(folder: Path, games: int) -> None:
    """Recorded games where a lineup with 폭탄마 always goes to the mafia and the others are even."""
    s = complex_setup()
    for i in range(games):
        roles = lineup(s, random.Random(1000 + i), playable)
        record(folder, i, roles, "폭탄마" in roles or i % 2 == 0)


def test_the_judged_draw_stays_fair_and_the_plain_draw_does_not(tmp_path: Path) -> None:
    history(tmp_path, 60)
    judge = draw_judge(complex_setup(), tmp_path, record=False)
    assert judge is not None
    plain = [lineup(complex_setup(), random.Random(i), playable) for i in range(40)]
    judged = [lineup(complex_setup(), random.Random(i), playable, judge) for i in range(40)]
    unfair = [r for r in plain if not FAIR[0] <= (judge(10, r) or 0.5) <= FAIR[1]]
    assert len(unfair) >= 5  # the plain draw does land outside often
    assert all(FAIR[0] <= (judge(10, r) or 0.0) <= FAIR[1] for r in judged)
    assert sum("폭탄마" in r for r in judged) < sum("폭탄마" in r for r in plain)


def test_too_few_games_other_lineups_and_no_folder_draw_plainly(tmp_path: Path) -> None:
    history(tmp_path, balance.ENOUGH - 1)
    judge = draw_judge(complex_setup(), tmp_path, record=False)
    assert judge is not None and judge(10, ["마피아"] * 10) is None  # too few games: the plain draw
    assert draw_judge(complex_setup(role_mode="named"), tmp_path, record=False) is None
    assert draw_judge(GameSetup(kind="simple", seats=[SeatSpec() for _ in range(6)]), tmp_path, record=False) is None
    assert draw_judge(complex_setup(), None, record=False) is None


def test_a_built_game_uses_the_judge_of_its_record_folder(tmp_path: Path) -> None:
    history(tmp_path, 60)
    judge = draw_judge(complex_setup(), tmp_path, record=False)
    assert judge is not None
    for seed in range(8):
        s = complex_setup(seed=seed)
        game, _rec, _h = build_game(s, None, offline=True, folder=tmp_path, record=False)
        roles = [p.role for p in game.players]
        assert FAIR[0] <= (judge(10, roles) or 0.0) <= FAIR[1]


def test_the_lobby_expects_a_fair_chance_for_random_once_the_draw_is_judged(tmp_path: Path) -> None:
    import time
    history(tmp_path, 60)
    started = time.monotonic()
    est = balance.drawn_estimate(complex_setup(), tmp_path)
    assert time.monotonic() - started < 1.0  # the lobby computes it on every change
    assert FAIR[0] <= est.p <= FAIR[1] and est.games == 60 and est.lo < est.p < est.hi
    few = tmp_path / "few"
    few.mkdir()
    history(few, 10)
    assert balance.drawn_estimate(complex_setup(), few).games == 10  # plain draws, the estimate stays rough


def test_below_30_games_the_lobby_shows_no_number_that_reads_like_a_fact(tmp_path: Path) -> None:
    """X1: with no 복잡 game recorded the lobby read 66~77 % for 랜덤, which was the prior alone (b1 8 around a
    quarter on the mafia team; the 복잡 table puts a third there). Its 40 % mafia share at 8 seats made 73 %."""
    import pytest
    pytest.importorskip("gi")
    from nmb.ui.lineup import chance_text
    empty = tmp_path / "none"
    empty.mkdir()
    assert balance.drawn_estimate(complex_setup(8), empty).p > 0.7  # what it used to show: the prior's number
    value, words, sure = chance_text(complex_setup(8), None, empty)
    assert (value, words, sure) == ("0/30 games", "Shows once games are recorded", False) and "%" not in value
    few = tmp_path / "few"
    few.mkdir()
    history(few, 29)
    assert chance_text(complex_setup(), None, few)[0] == "29/30 games"
    history(tmp_path, 60)
    value, words, sure = chance_text(complex_setup(), None, tmp_path)
    assert sure and value.endswith("%") and "60" in words
    assert chance_text(complex_setup(), ["마피아", "경찰", "의사"] + ["시민"] * 7, tmp_path)[2]
