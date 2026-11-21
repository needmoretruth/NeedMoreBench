"""The user's own roles: 복수자 shoots back at the mafia member who set the night's target;
사냥꾼, executed by vote, takes any one living player along after the 찬반. Each with the interactions
names: 의사, 방패병, 부활술사, 연인, 시장."""
from __future__ import annotations

from nmb.engine.roles import ROLES, pool_roles
from nmb.engine.setup import GameSetup

from .helpers import run_game, seats
from .test_complex import name, play, private_to, public


def executed(target: int, n: int, skip: tuple[int, ...] = ()) -> dict:
    """Day 2: everyone else votes `target` up and says guilty."""
    plan: dict = {}
    for s in range(n):
        if s != target and s not in skip:
            plan[(2, "vote", s)] = {"vote": target}
            plan[(2, "verdict", s)] = {"verdict": "찬성"}
    return plan


# ---- 복수자 -------------------------------------------------------------------------------------------------
def test_avenger_takes_the_mafia_who_named_it_and_the_morning_tells_both():
    g = play(["복수자", "마피아", "경찰", "의사", "시민", "시민", "시민"], {(1, "mafia", 1): {"target": 0}})
    assert not g.players[0].alive and not g.players[1].alive
    text = public(g)
    assert f"복수자 {name(g, 0)}님이 죽기 전에 쏜 총에 {name(g, 1)}님이 맞았습니다" in text
    assert f"밤사이 {name(g, 0)}님이 죽었습니다" in text and f"밤사이 {name(g, 1)}님이 죽었습니다" in text
    death = {e.target: e.data["cause"] for e in g.events if e.kind == "death"}
    assert death == {0: "mafia", 1: "avenger"}
    assert g.result is not None and g.result["team"] == "시민"  # the only mafia is gone


def test_avenger_shoots_the_first_member_whose_pick_set_the_target():
    roles = ["복수자", "마피아", "마피아", "경찰", "의사", "시민", "시민", "시민", "시민"]
    g = play(roles, {(1, "mafia", 1): {"target": 0}, (1, "mafia", 2): {"target": 0}})
    order = [e.actor for e in g.events if e.kind == "mafia" and e.actor is not None]
    first, second = order[0], order[1]
    assert not g.players[first].alive and g.players[second].alive
    g = play(roles, {(1, "mafia", 1): {"target": 0}, (1, "mafia", 2): {"target": 5}})  # a split
    first = [e.actor for e in g.events if e.kind == "mafia" and e.actor is not None][0]
    if first == 1:  # seat 1 named the 복수자 first: it is the one shot
        assert not g.players[0].alive and not g.players[1].alive and g.players[2].alive
    else:  # seat 2's pick stood: a citizen died and nobody shot back
        assert not g.players[5].alive and g.players[1].alive and g.players[2].alive and g.players[0].alive


def test_avenger_saved_by_the_doctor_fires_nothing():
    g = play(["복수자", "마피아", "경찰", "의사", "시민", "시민"], {(1, "mafia", 1): {"target": 0}, (1, "night", 3): {"target": 0}})
    assert g.players[0].alive and g.players[1].alive
    assert "복수자" not in public(g)


def test_avenger_revived_by_the_priest_leaves_the_mafia_dead():
    roles = ["복수자", "마피아", "마피아", "경찰", "의사", "부활술사", "시민", "시민", "시민"]
    plan = {(1, "mafia", 1): {"target": 0}, (1, "mafia", 2): {"target": 0}, (2, "night", 5): {"target": 0}}
    g = play(roles, plan, days=3)
    shot = next(e.target for e in g.events if e.kind == "death" and e.data["cause"] == "avenger")
    assert g.players[0].alive and not g.players[shot].alive
    assert f"부활술사가 {name(g, 0)}님을 되살렸습니다" in public(g)


def test_a_lover_dying_for_a_partner_is_no_avenger_and_a_soldier_never_shoots():
    g = play(["연인", "마피아", "경찰", "의사", "연인", "시민"], {(1, "mafia", 1): {"target": 0}})
    assert g.players[1].alive and not g.players[4].alive
    g = play(["방패병", "마피아", "경찰", "의사", "시민", "시민"], {(1, "mafia", 1): {"target": 0}})
    assert g.players[0].alive and g.players[1].alive


def test_the_avenger_learns_nothing_in_advance_and_has_no_night_call():
    g = play(["복수자", "마피아", "경찰", "의사", "시민", "시민"], {})
    assert (1, "night", 0) not in g.asked
    assert "마피아" not in private_to(g, 0)


# ---- 사냥꾼 -------------------------------------------------------------------------------------------------
def test_hunter_executed_takes_anyone_after_the_verdict_in_public():
    roles = ["사냥꾼", "마피아", "경찰", "의사", "시민", "시민", "시민"]
    g = play(roles, {**executed(0, 7), (2, "shot", 0): {"target": 2}}, days=2)
    assert not g.players[0].alive and not g.players[2].alive  # anyone, here a citizen-team 경찰
    assert f"사냥꾼 {name(g, 0)}님이 {name(g, 2)}님을 함께 데려갔습니다" in public(g)
    kinds = [e.kind for e in g.events if e.day == 2]
    assert kinds.index("verdict_result") < max(i for i, k in enumerate(kinds) if k == "death")  # after the 찬반
    assert (2, "shot", 0) in g.asked and (2, "defense", 0) in g.asked


def test_hunter_may_take_nobody_and_never_shoots_when_killed_at_night():
    roles = ["사냥꾼", "마피아", "경찰", "의사", "시민", "시민", "시민"]
    g = play(roles, {**executed(0, 7), (2, "shot", 0): {"target": "없음"}}, days=2)
    assert sum(not p.alive for p in g.players) == 1
    g = play(roles, {(1, "mafia", 1): {"target": 0}}, days=2)
    assert not g.players[0].alive and not any(k == "shot" for _d, k, _s in g.asked)


def test_hunter_shot_kills_the_last_mafia_and_the_town_wins():
    roles = ["사냥꾼", "마피아", "경찰", "의사", "시민", "시민", "시민"]
    g = play(roles, {**executed(0, 7), (2, "shot", 0): {"target": 1}}, days=2)
    assert not g.players[1].alive and g.result is not None and g.result["team"] == "시민"


def test_hunter_shot_ignores_the_doctor_the_soldier_the_lover_and_the_politician():
    for role, at in (("방패병", 2), ("시장", 2), ("연인", 2)):
        roles = ["사냥꾼", "마피아", role, "의사", "시민", "시민", "시민", "시민"]
        if role == "연인":
            roles[4] = "연인"
        plan = {**executed(0, 8), (2, "shot", 0): {"target": at}, (1, "night", 3): {"target": at}}
        g = play(roles, plan, days=2)
        assert not g.players[at].alive, role
        if role == "연인":
            assert g.players[4].alive  # a partner dies only for a mafia attack


def test_a_politician_hunter_cannot_exist_but_a_vote_saving_politician_stops_the_shot():
    roles = ["사냥꾼", "마피아", "시장", "의사", "시민", "시민", "시민"]
    plan = {**executed(2, 7), (2, "shot", 2): {"target": 1}}
    g = play(roles, plan, days=2)
    assert g.players[2].alive and (2, "shot", 2) not in g.asked


def test_both_roles_are_in_the_classic_pool_and_the_rules_text():
    from nmb.engine.prompts import rules_text
    assert {"복수자", "사냥꾼"} <= set(pool_roles("classic"))
    assert ROLES["복수자"].classic and ROLES["사냥꾼"].classic
    g = play(["복수자", "사냥꾼", "마피아", "경찰", "의사", "시민"], {})
    text = rules_text(g)
    assert ROLES["복수자"].text in text and ROLES["사냥꾼"].text in text


def test_whole_games_with_both_roles_end_cleanly():
    fired: set[str] = set()
    for seed in range(1, 25):
        setup = GameSetup(kind="complex", seats=seats(10), seed=seed)
        setup.seats[0].role, setup.seats[1].role = "복수자", "사냥꾼"
        g, _ = run_game(setup)
        assert g.result is not None
        for e in g.events:
            if e.kind == "death" and e.data["cause"] in ("avenger", "hunter"):
                assert e.to is None  # every such death is public
                fired.add(e.data["cause"])
    assert fired == {"avenger", "hunter"}  # random play reaches both shots
