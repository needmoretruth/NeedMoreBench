"""The day and night flow, played offline with random legal answers."""
from __future__ import annotations

import pytest

from nmb.engine.roles import simple_lineup
from nmb.engine.setup import GameSetup

from .helpers import run_game, seats


@pytest.mark.parametrize("n", range(4, 13))
def test_simple_games_end_with_a_winner(n):
    for seed in range(8):
        g, _ = run_game(GameSetup(kind="simple", seats=seats(n), seed=seed))
        assert g.result and g.result["team"] in ("마피아", "시민"), g.result
        assert g.day <= g.setup.max_nights + 1  # the morning after the last night


def test_simple_lineup_follows_the_table():
    assert simple_lineup(5)["마피아"] == 1 and simple_lineup(6)["마피아"] == 1
    assert simple_lineup(7)["마피아"] == 2 and simple_lineup(9)["마피아"] == 2
    assert simple_lineup(10)["마피아"] == 3
    assert sum(simple_lineup(8).values()) == 8
    assert simple_lineup(4) == {"마피아": 1, "경찰": 1, "의사": 1, "시민": 1}
    assert simple_lineup(12)["마피아"] == 3


def test_player_counts_follow_13_4():
    from nmb.engine.roles import COMPLEX_SLOTS, PLAYER_RANGE
    assert PLAYER_RANGE == {"simple": (4, 12), "complex": (4, 16)}
    assert COMPLEX_SLOTS[4] == (1, 0, 1, 1, 1, 0) and COMPLEX_SLOTS[5] == (1, 0, 1, 1, 2, 0)
    assert all(sum(COMPLEX_SLOTS[n]) == n for n in range(4, 17))
    assert GameSetup(kind="simple", seats=seats(3)).problem()
    assert GameSetup(kind="complex", seats=seats(3)).problem()


def test_game_starts_in_the_day_with_introductions_and_no_vote():
    """Day first: 1번째 낮 is 소개 in seat order, then 토론, then 1번째 밤 with no vote."""
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=2))
    phases = [e for e in g.events if e.kind == "phase"]
    assert (phases[0].data["phase"], phases[0].day) == ("day", 1) and (phases[1].data["phase"], phases[1].day) == ("night", 1)
    assert (phases[2].data["phase"], phases[2].day) == ("day", 2)
    steps = [e.data["step"] for e in g.events if e.kind == "step" and e.day == 1]
    assert steps == ["소개", "토론", "귓속말 시간"]  # whispers from the first day
    intros = [e for e in g.events if e.kind == "say" and e.data.get("intro")]
    assert [e.actor for e in intros] == list(range(7))  # each once, in seat order
    assert not any(e.kind in ("vote_result", "verdict_result") and e.day == 1 for e in g.events)
    assert "첫날은 투표 없이 밤이 됩니다." in [e.text for e in g.events if e.day == 1]
    assert not any(e.data.get("will") for e in g.events)
    system = log[0][2]
    assert "참일 수도 거짓일 수도 있다" in system and "게임은 낮으로 시작한다" in system


def test_day_order_is_discussion_vote_defense_verdict():
    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=4))
    kinds = [e.text if e.kind == "system" else e.kind for e in g.events if e.day == 2 and e.phase == "day" and e.log]
    i_vote_call = kinds.index("투표 시간입니다.")
    i_result = kinds.index("vote_result")
    assert i_vote_call < i_result
    if "verdict_result" in kinds:
        defense = [e for e in g.events if e.kind == "say" and e.data.get("defense") and e.day == 2]
        assert len(defense) <= 1
        assert kinds.index("verdict_result") > i_result


def test_quiet_night_line():
    def nobody_dies(game, p, req):
        if req.kind == "mafia":
            return {"say": "오늘은 쉬자", "target": "없음"}
        return None
    g, _ = run_game(GameSetup(kind="simple", seats=seats(6), seed=1, max_nights=2), nobody_dies)
    assert any(e.text == "조용하게 밤이 지나갔습니다." for e in g.events)


def test_tie_for_most_votes_goes_to_night():
    order: list[str] = []

    def split(game, p, req):
        if req.kind == "vote":
            alive = [q.name for q in game.alive()]
            return {"vote": alive[p.seat % 2]}
        return None
    g, _ = run_game(GameSetup(kind="simple", seats=seats(6), seed=3), split)
    first = [e for e in g.events if e.kind == "vote_result"][0]
    counts = list(first.data["counts"].values())
    if len(counts) > 1 and counts[0] == counts[1]:
        later = [e.text for e in g.events if e.id > first.id][:3]
        assert "최다 득표가 동점이라 밤이 됩니다." in later
        assert not any(e.kind == "verdict_result" and e.day == first.day for e in g.events)
    del order


def test_verdict_tie_executes_and_abstain_counts_against():
    def tie(game, p, req):
        if req.kind == "vote":
            return {"vote": game.players[0].name if game.players[0].alive else game.alive()[0].name}
        if req.kind == "verdict":
            voters = [q for q in game.alive() if q.name != game.players[0].name]
            half = len(voters) // 2
            return {"verdict": "찬성" if voters.index(p) < half else "반대"}
        return None
    g, _ = run_game(GameSetup(kind="simple", seats=seats(7), seed=5, max_nights=2), tie)
    v = [e for e in g.events if e.kind == "verdict_result"]
    if v and v[0].data["yes"] == v[0].data["no"]:
        assert any(e.kind == "death" and e.data["cause"] == "execution" for e in g.events)


def test_extend_adds_turns_once_a_day():
    used: dict[int, int] = {}

    def extend(game, p, req):
        if req.kind == "discuss":
            used[p.seat] = used.get(p.seat, 0) + 1
            return {"say": "조금 더 얘기해요.", "time": "연장", "hand": 1}
        return None
    g, _ = run_game(GameSetup(kind="simple", seats=seats(5), seed=6, max_nights=2), extend)
    lines = [e for e in g.events if e.kind == "system" and "토론 시간을 늘렸습니다" in e.text and e.day == 1]
    assert len(lines) == len({e.data["actor_seat"] for e in lines}) <= 5
    first = next(e for e in g.events if e.kind == "turns" and e.day == 1)
    dead_before = sum(1 for e in g.events if e.kind == "death" and e.id < first.id)
    assert first.data["left"] == first.data["total"] == 1 * (5 - dead_before)  # the first day: one turn each
    # each extension adds two turns: the day's turn count is the start plus two per extension
    said = [e for e in g.events if e.kind == "say" and e.day == 1 and not e.data.get("defense") and not e.data.get("intro")]
    assert len(said) == first.data["total"] + 2 * len(lines)


def test_turns_warning_and_vote_call():
    g, _ = run_game(GameSetup(kind="simple", seats=seats(7), seed=7))
    texts = [e.text for e in g.events if e.kind == "system"]
    assert "투표 시간입니다." in texts
    assert "토론 시간이 얼마 남지 않았습니다." in texts


def test_discussion_prompt_states_turns_and_poll():
    def poll_first(game, p, req):
        if req.kind == "discuss":
            return {"say": "저는 첫 번째 사람이 수상해요.", "poll": game.alive()[0].name, "hand": 1}
        return None
    g, log = run_game(GameSetup(kind="simple", seats=seats(6), seed=8, max_nights=2), poll_first)
    discuss = [u for _, k, _, u in log if k == "discuss"]
    assert all("남은 발언 차례:" in u for u in discuss)
    assert any("여론 조사:" in u and "1명" in u for u in discuss[1:])
    system = log[0][2]
    assert "연장" in system and "단축" in system and "여론 조사" in system


def test_tenth_night_cap():
    def peace(game, p, req):
        if req.kind == "mafia":
            return {"say": "", "target": "없음"}
        if req.kind in ("vote",):
            return {"vote": "기권"}
        return None
    g, _ = run_game(GameSetup(kind="simple", seats=seats(7), seed=9), peace)
    assert g.result["team"] == "마피아" and "10번째 밤" in g.result["reason"] and g.day == 11
