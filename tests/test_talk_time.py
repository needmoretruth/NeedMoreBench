"""the talk ends when there is nothing left to say. The first day has one turn each after the intros,
단축 is a public vote that ends the talk once more than half of the living have pressed it, and silence lowers
the hand."""
from __future__ import annotations

from nmb.engine.setup import GameSetup, SeatSpec

from .helpers import run_game, seats


def talk_lines(g, day: int) -> list:
    return [e for e in g.events if e.kind == "say" and e.day == day and not e.data.get("intro") and not e.data.get("defense")]


def test_first_day_has_one_turn_each() -> None:
    def chatty(game, p, req):  # everyone names the same player, who would reply first under the old order
        if req.kind != "discuss":
            return None
        target = next(q for q in game.alive() if q is not p)
        return {"say": f"{target.name}님은 어떻게 생각해요?", "hand": 3}
    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=3, max_nights=1), chatty)
    first = next(e for e in g.events if e.kind == "turns" and e.day == 1)
    assert first.data["total"] == 8
    lines = talk_lines(g, 1)
    assert len(lines) == 8 and len({e.actor for e in lines}) == 8  # one turn each, nobody left out


def test_majority_cut_ends_the_talk_on_that_turn() -> None:
    pressed: list[int] = []

    def cut(game, p, req):
        if req.kind != "discuss":
            return None
        if game.day == 2:
            pressed.append(p.seat)
            return {"say": "이제 투표로 가요.", "time": "단축", "hand": 3}
        return {"say": "좋아요.", "hand": 3}
    g, _ = run_game(GameSetup(kind="simple", seats=seats(7), seed=4, max_nights=2), cut)
    done = [e for e in g.events if e.kind == "system" and e.data.get("cut_done") and e.day == 2]
    assert len(done) == 1
    alive = sum(1 for e in g.events if e.kind == "turns" and e.day == 2) and \
        next(e for e in g.events if e.kind == "turns" and e.day == 2).data["total"] // 2
    need = alive // 2 + 1
    announced = [e for e in g.events if e.kind == "system" and e.data.get("time") == "단축" and e.day == 2]
    assert len(announced) == need  # every press is public, and the press that makes the majority ends it
    assert announced[-1].data["cut"] == need
    after = [e for e in talk_lines(g, 2) if e.id > done[0].id]
    assert not after  # nobody speaks after the majority
    assert len(talk_lines(g, 2)) == need


def test_silence_lowers_the_hand_and_ends_the_talk() -> None:
    asked: dict[int, int] = {}

    def quiet(game, p, req):
        if req.kind != "discuss":
            return None
        asked[game.day] = asked.get(game.day, 0) + 1
        return {"say": "", "hand": 3}  # a raised hand with nothing said counts as lowered
    setup = GameSetup(kind="simple", seats=seats(6), seed=8, max_nights=2)
    g, _ = run_game(setup, quiet)
    start = next(e for e in g.events if e.kind == "turns" and e.day == 2)
    alive = start.data["total"] // setup.turns_per_player
    assert setup.turns_per_player > 1
    assert asked[2] == alive  # everyone once, then nobody has a hand up: the talk ends with turns left


def test_person_buttons_follow_the_same_rules() -> None:
    sp = seats(5)
    sp[0] = SeatSpec(kind="human", human_name="나")
    log: list[tuple[int, int]] = []

    def fn(game, p, req):
        if req.kind == "discuss" and game.day == 1 and not log:
            game.press_time(0, "단축")
            game.press_time(0, "단축")  # once a day
            game.press_time(0, "연장")
            log.append((len(game.cut_votes), len(game.time_used)))
        if p.kind == "human":
            return {"say": ""} if req.kind == "discuss" else None
        return {"say": "글쎄요.", "hand": 1} if req.kind == "discuss" else None
    run_game(GameSetup(kind="simple", seats=sp, seed=9, max_nights=2), fn)
    assert log == [(1, 1)]
