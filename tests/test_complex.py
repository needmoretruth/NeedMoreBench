"""복잡한 마피아, classic pool: each ability sets up a night or a day and checks the outcome
and who learns what. Seats get fixed roles; answers are scripted per (day, call kind, seat)."""
from __future__ import annotations

import asyncio
import random
from typing import Any

from nmb.engine.abilities import ability_for, in_mafia_team
from nmb.engine.game import Game
from nmb.engine.setup import GameSetup, seat_players

from .helpers import Spy, run_game, seats


def play(roles: list[str], plan: dict[tuple[int, str, int], Any], days: int = 1, seed: int = 7):
    """Play the first day and nights 1..days, until the discussion of day days+1 starts. plan[(day, kind, seat)] is an answer (or a list of answers
    taken in turn); an int value names that seat's player. Unplanned calls answer nothing (no pick, no vote)."""
    setup = GameSetup(kind="complex", seats=seats(len(roles)), seed=seed, named=False)
    for s, r in zip(setup.seats, roles):
        s.role = r
    rng = random.Random(seed)
    players = seat_players(setup, rng)
    log: list = []
    asked: list[tuple[int, str, int]] = []

    def fn(game, p, req):
        asked.append((game.day, req.kind, p.seat))
        if req.kind == "discuss" and game.day > days:  # day first: day days+1 follows night days
            game.stop()
            return {}
        ans = plan.get((game.day, req.kind, p.seat), {})
        if isinstance(ans, list):
            ans = ans.pop(0) if ans else {}
        return {k: (game.players[v].name if isinstance(v, int) and k != "hand" else v) for k, v in ans.items()}

    g = Game(setup, players, {p.seat: Spy(seed, log, fn) for p in players}, rng=rng)
    asyncio.run(g.run())
    g.asked = asked
    g.log = log
    return g


def seen(g: Game, seat: int, day: int | None = None) -> str:
    return "\n".join(e.text for e in g.events if e.log and e.visible_to(seat) and (day is None or e.day == day))


def public(g: Game) -> str:
    return "\n".join(e.text for e in g.events if e.to is None)


def private_to(g: Game, seat: int) -> str:
    return "\n".join(e.text for e in g.events if e.to is not None and seat in e.to)


def name(g: Game, seat: int) -> str:
    return g.players[seat].name


# ---- 마피아 보조 ---------------------------------------------------------------------------------------------
def test_spy_contacts_on_finding_the_mafia_and_checks_again():
    g = play(["스파이", "마피아", "경찰", "의사", "시민", "시민"], {(1, "night", 0): [{"target": 1}, {"target": 2}]})
    spy, mafia = g.players[0], g.players[1]
    assert spy.contacted and in_mafia_team(spy)
    assert f"{name(g, 1)}님의 직업은 마피아" in private_to(g, 0)
    assert f"{name(g, 2)}님의 직업은 경찰" in private_to(g, 0)  # the second check
    assert f"{spy.name}(스파이)이(가) 마피아 팀과 접선했다" in private_to(g, 1)
    for other in (2, 3, 4, 5):
        assert "직업은 마피아" not in seen(g, other) and "접선" not in seen(g, other)
    assert mafia.alive


def test_spy_check_on_the_soldier_shows_the_spy_to_it():
    g = play(["스파이", "마피아", "군인", "의사", "경찰", "시민"], {(1, "night", 0): {"target": 2}})
    assert f"{name(g, 0)}님이 너를 조사했다" in private_to(g, 2)
    assert not g.players[0].contacted


def test_beast_is_tamed_when_the_mafia_kills_its_mark_and_then_picks_kills():
    plan = {(1, "night", 0): {"target": 4}, (1, "mafia", 1): {"target": 4}}
    g = play(["짐승인간", "마피아", "경찰", "의사", "시민", "시민"], plan)
    beast = g.players[0]
    assert not g.players[4].alive and beast.contacted
    assert ability_for(beast).is_killer(g, beast)


def test_the_mafia_cannot_kill_the_beast():
    g = play(["짐승인간", "마피아", "경찰", "의사", "시민", "시민"], {(1, "mafia", 1): {"target": 0}})
    assert g.players[0].alive
    assert "조용하게 밤이 지나갔습니다" in public(g)


def test_madam_seduces_by_vote_blocking_the_night_and_silencing_the_next_day():
    plan = {(2, "vote", 0): {"vote": 2}, (2, "night", 2): {"target": 4}}
    g = play(["마담", "마피아", "경찰", "의사", "시민", "시민"], plan, days=2)
    assert (2, "night", 2) not in g.asked  # the seduced 경찰 is not asked at night
    assert "능력을 쓰지 못한다" in private_to(g, 2)
    assert g.players[2].silenced_day == 3
    assert "유혹" not in public(g)
    assert not g.players[0].contacted


def test_madam_seducing_the_mafia_contacts():
    g = play(["마담", "마피아", "경찰", "의사", "시민", "시민"], {(2, "vote", 0): {"vote": 1}}, days=2)
    assert g.players[0].contacted and not g.blocked_next


def test_thief_steals_by_day_and_uses_the_ability_that_night():
    plan = {(2, "vote", 0): {"vote": 4, "steal": 2}, (2, "night", 0): {"target": 1}}
    g = play(["도둑", "마피아", "경찰", "의사", "시민", "시민"], plan, days=2)
    vote_prompt = next(u for st, k, _s, u in g.log if st == 0 and k == "vote")
    assert "steal" in vote_prompt
    assert f"{name(g, 1)}님은 마피아입니다" in private_to(g, 0)  # the stolen 경찰 check
    assert "steal" not in next(u for st, k, _s, u in g.log if st == 4 and k == "vote")


def test_thief_stealing_the_mafia_contacts():
    g = play(["도둑", "마피아", "경찰", "의사", "시민", "시민"], {(2, "vote", 0): {"steal": 1}}, days=2)
    assert g.players[0].contacted


# ---- 시민 팀 특수 ---------------------------------------------------------------------------------------------
def test_soldier_survives_one_mafia_attack_in_public():
    g = play(["군인", "마피아", "경찰", "의사", "시민", "시민"], {(1, "mafia", 1): {"target": 0}, (2, "mafia", 1): {"target": 0}},
             days=3)
    assert f"군인 {name(g, 0)}님이 마피아의 공격을 버텨냈습니다" in public(g)
    assert g.players[0].revealed and not g.players[0].alive and g.players[0].died_day == 2


def test_politician_counts_twice_and_is_not_executed():
    plan = {(2, "vote", 0): {"vote": 4}, (2, "vote", 4): {"vote": 0}, (2, "vote", 5): {"vote": 0},
            (2, "verdict", 4): {"verdict": "찬성"}, (2, "verdict", 5): {"verdict": "찬성"}}
    g = play(["정치인", "마피아", "경찰", "의사", "시민", "시민"], plan, days=2)
    res = next(e for e in g.events if e.kind == "vote_result")
    assert res.data["counts"][name(g, 4)] == 2 and res.data["counts"][name(g, 0)] == 2  # tie: straight to night
    plan[(2, "vote", 3)] = {"vote": 0}
    plan[(2, "verdict", 2)] = plan[(2, "verdict", 3)] = {"verdict": "찬성"}
    g = play(["정치인", "마피아", "경찰", "의사", "시민", "시민"], plan, days=2)
    assert g.players[0].alive and "투표로 처형되지 않습니다" in public(g)


def test_medium_hears_the_dead_and_lays_one_to_rest():
    plan = {(1, "mafia", 1): {"target": 4}, (2, "dead", 4): {"say": "나는 시민이었어"}, (2, "night", 0): {"target": 4}}
    g = play(["영매", "마피아", "경찰", "의사", "시민", "시민"], plan, days=3)
    chat = [e for e in g.events if e.kind == "dead"]
    assert chat and all(e.to == frozenset({0, 4}) for e in chat)
    assert "나는 시민이었어" in seen(g, 0) and "나는 시민이었어" not in seen(g, 2)
    assert f"{name(g, 4)}님의 직업은 시민" in private_to(g, 0)
    assert g.players[4].at_rest
    assert (3, "dead", 4) not in g.asked  # laid to rest: silent from then on


def test_lovers_talk_alone_at_night_and_one_dies_for_the_other():
    plan = {(1, "lover", 0): {"say": "우리 둘만 아는 말"}, (1, "mafia", 1): {"target": 0}}
    g = play(["연인", "마피아", "경찰", "의사", "연인", "시민"], plan)
    assert g.players[0].alive and not g.players[4].alive
    assert f"연인 {name(g, 4)}님이 {name(g, 0)}님을 대신해 죽었습니다" in public(g)
    assert "우리 둘만 아는 말" in seen(g, 4) and "우리 둘만 아는 말" not in seen(g, 1)
    assert f"너의 연인은 {name(g, 4)}님이다" in private_to(g, 0)


def test_thug_takes_a_vote_for_the_next_day():
    g = play(["건달", "마피아", "경찰", "의사", "시민", "시민"], {(1, "night", 0): {"target": 4}}, days=2)
    assert (2, "vote", 4) not in g.asked and (2, "vote", 5) in g.asked
    assert "투표할 수 없다" in private_to(g, 4)


def test_reporter_waits_for_the_second_night_then_publishes():
    g = play(["기자", "마피아", "경찰", "의사", "시민", "시민"], {(2, "night", 0): {"target": 1}}, days=3)
    assert (1, "night", 0) not in g.asked
    assert f"특종입니다! {name(g, 1)}님의 직업은 마피아입니다" in public(g)
    assert g.players[1].revealed


def test_detective_learns_whom_another_used_an_ability_on():
    plan = {(1, "night", 0): {"target": 3}, (1, "night", 3): {"target": 5}}
    g = play(["사립탐정", "마피아", "경찰", "의사", "시민", "시민"], plan)
    assert f"{name(g, 3)}님은 오늘 밤 {name(g, 5)}님에게 능력을 썼다" in private_to(g, 0)
    g = play(["사립탐정", "마피아", "경찰", "의사", "시민", "시민"], {(1, "night", 0): {"target": 1}, (1, "mafia", 1): {"target": 4}})
    assert f"{name(g, 1)}님은 오늘 밤 {name(g, 4)}님에게 능력을 썼다" in private_to(g, 0)


def test_graverobber_inherits_the_first_mafia_victims_role():
    g = play(["도굴꾼", "마피아", "경찰", "의사", "시민", "시민"], {(1, "mafia", 1): {"target": 2}}, days=2)
    assert g.players[0].role == "경찰" and g.players[0].start_role == "도굴꾼"
    assert "이제 너는 경찰이다" in private_to(g, 0)
    assert (2, "night", 0) in g.asked  # it checks as the 경찰 now


def test_terrorist_takes_the_mafia_along_at_night_and_at_execution():
    plan = {(1, "night", 0): {"target": 1}, (1, "mafia", 1): {"target": 0}}
    g = play(["테러리스트", "마피아", "경찰", "의사", "시민", "시민", "시민"], plan)
    assert not g.players[0].alive and not g.players[1].alive
    votes = {(2, "vote", s): {"vote": 0} for s in range(1, 7)}
    verdicts = {(2, "verdict", s): {"verdict": "찬성"} for s in range(1, 7)}
    g = play(["테러리스트", "마피아", "경찰", "의사", "시민", "시민", "시민"], {**votes, **verdicts, (2, "defense", 0): {"take": 1}},
             days=2)
    assert not g.players[0].alive and not g.players[1].alive
    assert f"테러리스트 {name(g, 0)}님이 {name(g, 1)}님과 함께 죽었습니다" in public(g)


def test_priest_revives_once_in_public():
    plan = {(1, "mafia", 1): {"target": 4}, (2, "night", 0): {"target": 4}}
    g = play(["성직자", "마피아", "경찰", "의사", "시민", "시민", "시민"], plan, days=3)
    assert g.players[4].alive
    assert f"성직자의 기도로 {name(g, 4)}님이 되살아났습니다" in public(g)
    assert (3, "night", 0) not in g.asked or g.players[0].state.get("used")


def test_doctor_save_and_police_check_still_work_in_complex():
    plan = {(1, "mafia", 1): {"target": 4}, (1, "night", 3): {"target": 4}, (1, "night", 2): {"target": 1}}
    g = play(["시민", "마피아", "경찰", "의사", "시민", "시민"], plan)
    assert g.players[4].alive and f"의사의 치료로 {name(g, 4)}님이 살아났습니다" in public(g)
    assert f"{name(g, 1)}님은 마피아입니다" in private_to(g, 2)


# ---- whole games --------------------------------------------------------------------------------------------
def test_every_private_line_reaches_only_its_audience():
    for seed in (3, 11, 29):
        g, log = run_game(GameSetup(kind="complex", seats=seats(12), seed=seed))
        prompts = {s: "\n".join(u for st, _k, _s, u in log if st == s) for s in range(12)}
        for e in g.events:
            if not e.log or e.to is None or not e.text:
                continue
            for s in range(12):
                if s not in e.to and e.text not in seen(g, s):
                    assert e.text not in prompts[s], (seed, e.kind, e.text, s)


def test_complex_games_end_and_draw_only_built_roles():
    from nmb.engine.setup import playable
    for seed in range(1, 40):
        n = 4 + seed % 13
        g, _ = run_game(GameSetup(kind="complex", seats=seats(n), seed=seed, role_pool="full"))
        assert g.result is not None and g.result["team"] is not None or g.result["label"] == "무승부"
        assert all(playable(p.start_role) for p in g.players)
