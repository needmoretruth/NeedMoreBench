"""whose thought, whispers from day 1, the mafia meeting in rounds, every ability use is
an action line, and the mafia may target its own."""
from __future__ import annotations

from nmb.engine.abilities import in_mafia_team
from nmb.engine.setup import GameSetup

from .helpers import run_game, seats


def test_every_thought_has_its_thinker_and_day_one_has_whispers() -> None:
    g, _ = run_game(GameSetup(kind="simple", seats=seats(7), seed=3, max_nights=2))
    thoughts = [e for e in g.events if e.kind in ("thought", "reasoning")]
    assert thoughts and all(e.actor is not None for e in thoughts)  # the row shows that player's avatar and name
    assert any(e.kind == "step" and e.day == 1 and e.data["step"] == "귓속말 시간" for e in g.events)
    assert not any(e.kind == "system" and e.day == 1 and e.text == "투표 시간입니다." for e in g.events)


def test_meeting_runs_rounds_until_the_killers_agree() -> None:
    def fn(game, p, req):
        if req.kind != "mafia" or not req.field:
            return None
        mafia = sorted((q for q in game.alive() if in_mafia_team(q)), key=lambda q: q.seat)
        town = [q.name for q in game.alive() if not in_mafia_team(q)]
        if game.day != 1:
            return {"say": "같이 가요.", "target": town[0]}
        rounds = sum(1 for e in game.events if e.kind == "mafia" and e.actor == p.seat and e.day == 1)
        if rounds == 0:  # the first round: each picks someone different
            return {"say": "저는 다른 사람이요.", "target": town[mafia.index(p) % len(town)]}
        return {"say": f"{town[0]}님으로 맞춰요.", "target": town[0]}

    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=5, max_nights=1), fn)
    lines = [e for e in g.events if e.kind == "mafia" and e.day == 1 and e.actor is not None]
    members = {e.actor for e in lines}
    assert len(members) >= 2
    assert max(e.data["round"] for e in lines) == 2  # disagreed in round 1, agreed in round 2, stopped
    decided = [e for e in g.events if e.kind == "mafia" and e.day == 1 and e.data.get("decided")]
    assert len(decided) == 1 and decided[0].data["decided"] == lines[-1].data["pick"]


def test_mafia_may_pick_a_teammate_and_a_save_reads_the_same() -> None:
    picked: dict[str, str] = {}

    def fn(game, p, req):
        if req.kind == "mafia" and req.field:
            mate = min((q for q in game.alive() if in_mafia_team(q)), key=lambda q: q.seat)  # a teammate, or itself
            assert mate.name in req.options and p.name in req.options  # teammates and oneself are legal
            picked["mafia"] = mate.name
            return {"say": "우리 편을 노려요.", "target": mate.name}
        if req.kind == "night" and p.role == "의사" and "mafia" in picked:
            return {"target": picked["mafia"]}
        return None

    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=7, max_nights=1), fn)
    target = picked["mafia"]
    saved = [e for e in g.events if e.kind == "system" and e.day == 2 and "의사의 치료로" in e.text]
    doctor_alive = any(e.kind == "action" and e.data["role"] == "의사" and e.day == 1 for e in g.events)
    assert doctor_alive
    assert [e.text for e in saved] == [f"의사의 치료로 {target}님이 살아났습니다."]  # the same words as any save


def test_every_ability_use_is_an_action_only_its_actor_reads() -> None:
    g, log = run_game(GameSetup(kind="complex", seats=seats(12), seed=4, max_nights=2, role_pool="classic"))
    nights = [e for e in g.events if e.kind == "action" and e.phase == "night"]
    asked = {s for s, kind, _sys, _u in log if kind == "night"}
    assert asked and asked <= {e.actor for e in nights}  # every night choice (or pass) has its line
    assert all(e.to == frozenset({e.actor}) for e in nights if e.data["role"] != "마피아")
    assert sum(1 for e in nights if e.data["role"] == "마피아") == sum(1 for e in g.events if e.kind == "mafia" and e.data.get("decided"))
    for seat, _kind, system, user in log:  # nobody's prompt carries another player's action
        for e in g.events:
            if e.kind == "action" and e.actor != seat and e.data.get("what") and f"네 행동: {e.data['what']}" in user:
                raise AssertionError((seat, e.text))
    mine = [(s, u) for s, _k, _sy, u in log if "네 행동:" in u]
    assert mine  # the actor keeps its own choice as memory
