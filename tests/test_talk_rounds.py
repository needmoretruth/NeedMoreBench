"""nobody drops out of the talk silently. In the user's game four models answered hand 0 once and were
never asked again while two named models took every reply turn."""
from __future__ import annotations

from nmb.engine.setup import GameSetup

from .helpers import run_game, seats


def test_quiet_and_named_players_all_speak_again_within_a_round() -> None:
    quiet_once: set[int] = set()

    def fn(game, p, req):
        if req.kind != "discuss":
            return None
        names = [q.name for q in game.alive()]
        a, b = names[0], names[1]  # the two who get named every turn
        if game.day == 2 and p.name in names[2:6] and p.seat not in quiet_once:
            quiet_once.add(p.seat)
            return {"say": "저는 당분간 듣기만 할게요.", "hand": 0}
        target = b if p.name == a else a
        return {"say": f"{target}님 생각은 어때요?", "hand": 1}

    g, _ = run_game(GameSetup(kind="simple", seats=seats(10), seed=11, max_nights=2, turns_per_player=3), fn)
    day2 = [e for e in g.events if e.kind == "say" and e.day == 2 and not e.data.get("defense")]
    assert len(quiet_once) == 4
    alive = {e.actor for e in day2}
    first_pass = len(alive)
    after = day2[first_pass:first_pass + len(alive)]
    assert {e.actor for e in after} == alive  # the next round asks everyone, the quiet four included
    for x, y in zip(day2, day2[1:]):
        assert not (x.actor == y.actor)


def test_no_two_reply_turns_in_a_row_while_others_wait() -> None:
    def fn(game, p, req):
        if req.kind != "discuss":
            return None
        names = [q.name for q in game.alive()]
        target = names[1] if p.name == names[0] else names[0]
        return {"say": f"{target}님, 답해 주세요.", "hand": 2}

    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=12, max_nights=2, turns_per_player=3), fn)
    day2 = [e for e in g.events if e.kind == "say" and e.day == 2 and not e.data.get("defense")]
    assert any(e.data.get("reply") for e in day2)  # named players still get reply turns
    prev: dict[int, bool] = {}
    for e in day2:  # a player's two turns in a row are never both reply turns (everyone keeps a hand up here)
        reply = bool(e.data.get("reply"))
        assert not (reply and prev.get(e.actor)), e.actor
        prev[e.actor] = reply
    n = len({e.actor for e in day2})
    assert {e.actor for e in day2[n:2 * n]} == {e.actor for e in day2}  # the second round reaches everyone


def test_pass_costs_no_turn_and_talk_states_are_shown() -> None:
    def fn(game, p, req):
        if req.kind != "discuss":
            return None
        return {"say": "", "hand": 0} if p.seat % 2 else {"say": "저는 시민입니다.", "hand": 1}

    g, _ = run_game(GameSetup(kind="simple", seats=seats(6), seed=13, max_nights=1), fn)
    turns = [e for e in g.events if e.kind == "turns" and e.day == 1]
    said = [e for e in g.events if e.kind == "say" and e.day == 1 and not e.data.get("intro")]
    assert turns[0].data["total"] - turns[-1].data["left"] == len(said)  # only lines spend turns
    states = [e.data["states"] for e in g.events if e.kind == "talk" and e.day == 1 and e.data["states"]]
    seen = {s for st in states for s in st.values()}
    assert {"thinking", "speaking", "hand", "done"} <= seen
    last = [e for e in g.events if e.kind == "talk" and e.day == 1][-1]
    assert last.data["states"] == {}  # cleared when the talk ends
