"""교주팀: 교주 converts on odd nights, a bell rings, the cult hears its leader, wins at half the
living, several cults stay apart, a 광신도 finds its 교주 and takes over; and the setting in 랜덤."""
from __future__ import annotations

import random

from nmb.engine.abilities.base import side
from nmb.engine.lineups import lineup
from nmb.engine.setup import GameSetup, playable

from .helpers import seats
from .test_complex import name, play, private_to, public, seen

BELL = "종소리가 울렸습니다. 누군가 교주 팀이 되었습니다."


def test_leader_converts_a_citizen_rings_the_bell_and_learns_the_role():
    g = play(["교주", "마피아", "경찰", "의사", "시민", "시민"], {(1, "night", 0): {"target": 2}})
    assert side(g.players[2]) == "교주" and g.players[2].state["cult"] == 0
    assert f"{name(g, 2)}님의 직업은 경찰이다" in private_to(g, 0)
    assert f"교주 {name(g, 0)}님에게 포교되어" in private_to(g, 2)
    assert BELL in public(g) and name(g, 2) not in [t for t in public(g).splitlines() if "종소리" in t][0]


def test_the_mafia_and_the_reviver_cannot_be_converted():
    for target, role in ((1, "마피아"), (2, "부활술사")):
        roles = ["교주", "마피아", "경찰", "의사", "시민", "시민"]
        roles[target] = role
        g = play(roles, {(1, "night", 0): {"target": target}})
        assert side(g.players[target]) != "교주" and "포교에 실패했다" in private_to(g, 0) and BELL not in public(g)


def test_only_the_cult_and_the_dead_hear_the_leader_and_none_answer():
    plan = {(1, "night", 0): {"target": 4}, (1, "mafia", 1): {"target": 5}, (2, "night", 0): {"say": "내일 경찰을 찍자"}}
    g = play(["교주", "마피아", "경찰", "의사", "시민", "시민"], plan, days=2)
    assert (2, "night", 4) not in g.asked  # the convert has no night turn of its own
    assert "내일 경찰을 찍자" in seen(g, 4) and "내일 경찰을 찍자" in seen(g, 5)  # the cult and the dead
    for s in (1, 2, 3):
        assert "내일 경찰을 찍자" not in seen(g, s)
    night2 = [u for st, k, _s, u in g.log if st == 0 and k == "night" and "짝수" in u]
    night1 = [u for st, k, _s, u in g.log if st == 0 and k == "night" and "포교할 사람" in u]
    assert '"target"' in night1[0] and night2 and '"target"' not in night2[0]  # even night: no conversion asked


def test_the_cult_wins_at_half_of_the_living_and_the_convert_wins_with_it():
    plan = {(1, "night", 0): {"target": 2}, (1, "mafia", 1): {"target": 3}}
    g = play(["교주", "마피아", "경찰", "시민", "시민"], plan, days=2)
    assert g.result is not None and g.result["team"] == "교주"
    assert g.result["winners"] == [0, 2]


def test_with_the_mafia_dead_a_cult_at_half_wins_before_the_citizens():
    plan = {(1, "night", 0): {"target": 2}} | {(2, "vote", s): {"vote": 1} for s in range(5)}
    plan |= {(2, "verdict", s): {"verdict": "찬성"} for s in range(5)}
    g = play(["교주", "마피아", "경찰", "시민", "시민"], plan, days=2)
    assert not g.players[1].alive and g.result is not None and g.result["team"] == "교주"


def test_two_cults_stay_apart():
    plan = {(1, "night", 0): {"target": 3}, (1, "night", 1): {"target": 4}}
    g = play(["교주", "교주", "마피아", "경찰", "의사", "시민", "시민", "시민"], plan)
    assert g.players[3].state["cult"] == 0 and g.players[4].state["cult"] == 1
    assert public(g).count(BELL) == 1  # one bell a morning


def test_fanatic_finds_its_leader_and_takes_over_converting():
    plan = {(1, "night", 1): {"target": 0}, (1, "mafia", 2): {"target": 0}, (3, "night", 1): {"target": 5}}
    g = play(["교주", "광신도", "마피아", "경찰", "의사", "시민"], plan, days=3)
    assert f"{name(g, 0)}님이 교주다" in private_to(g, 1)
    assert not g.players[0].alive and "포교를 이어받았다" in private_to(g, 1)
    assert g.players[5].state.get("cult") == 0 and f"{name(g, 1)}님에게 포교되어" in private_to(g, 5)


def test_the_setting_puts_the_leader_in_random_from_nine_players_and_the_fanatic_from_twelve():
    def dealt(n: int, cult: bool) -> list[str]:
        s = GameSetup(kind="complex", seats=seats(n), cult=cult, role_pool="full", seed=3)
        return lineup(s, random.Random(3), playable)
    assert "교주" not in dealt(9, False) and "교주" not in dealt(8, True)
    assert dealt(9, True).count("교주") == 1 and "광신도" not in dealt(9, True)
    assert dealt(12, True).count("교주") == 1 and dealt(12, True).count("광신도") == 1
    assert len(dealt(12, True)) == 12
