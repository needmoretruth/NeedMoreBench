"""복잡한 마피아, the rest of the full pool: each ability set up with fixed roles and scripted answers,
then the outcome and who learns what."""
from __future__ import annotations

from nmb.engine.abilities import in_mafia_team

from .test_complex import name, play, private_to, public, seen

BASE = ["마피아", "경찰", "의사", "시민", "시민"]  # seats 1..5 after the role under test at seat 0


# ---- 마피아 보조 ---------------------------------------------------------------------------------------------
def test_witch_frogs_the_mayor_who_then_counts_once():
    roles = ["마녀", "마피아", "시장", "의사", "시민", "시민"]
    g = play(roles, {(1, "night", 0): {"target": 2}, (2, "vote", 2): {"vote": 4}}, days=2)
    assert "개구리가 되었다" in private_to(g, 2) and "개구리로 만들었다" in private_to(g, 0)
    assert "개구리" not in seen(g, 4)  # private: only the witch and the frog know
    res = next(e for e in g.events if e.kind == "vote_result")
    assert res.data["counts"][name(g, 4)] == 1  # the 시장's double vote is gone for the day
    assert not g.players[2].state.get("frog")  # the next night lifted it


def test_witch_picking_the_mafia_contacts_instead():
    g = play(["마녀", *BASE], {(1, "night", 0): {"target": 1}})
    assert g.players[0].contacted and not g.players[1].state.get("frog")


def test_undying_comes_back_once_when_the_next_night_ends():
    g = play(["불사신", *BASE], {(1, "mafia", 1): {"target": 0}}, days=3)
    u = g.players[0]
    assert u.alive and u.revealed and u.contacted and in_mafia_team(u)
    assert f"불사신 {u.name}님이 되살아났습니다" in public(g)
    rise = next(e for e in g.events if e.kind == "revive")
    assert (rise.day, rise.phase) == (2, "night")  # when night 2 ends, not night 1


def test_masquerader_knows_a_citizen_and_escapes_its_first_execution():
    plan = {(2, "vote", s): {"vote": 0} for s in range(1, 6)} | {(2, "verdict", s): {"verdict": "찬성"} for s in range(1, 6)}
    g = play(["위장꾼", *BASE], plan, days=2)
    m = g.players[0]
    cover = g.by_name(m.state["cover"])
    assert cover is not None and f"직업은 {cover.role}" in private_to(g, 0)
    assert m.alive and m.contacted and f"{m.name}님은 처형되지 않았습니다" in public(g)


def test_assassin_kills_two_when_both_roles_are_right():
    plan = {(2, "night", 0): [{"target": 2, "role": "경찰"}, {"target": 3, "role": "의사"}]}
    g = play(["암살자", *BASE], plan, days=2)
    assert (1, "night", 0) not in g.asked  # from the second night
    assert not g.players[2].alive and not g.players[3].alive


def test_assassin_with_one_wrong_role_kills_nobody():
    plan = {(2, "night", 0): [{"target": 2, "role": "경찰"}, {"target": 3, "role": "시민"}]}
    g = play(["암살자", *BASE], plan, days=2)
    assert g.players[2].alive and g.players[3].alive
    assert "둘 다 맞히지 못해" in private_to(g, 0)


def test_godfather_contacts_on_the_third_night_and_the_kill_goes_through_the_doctor():
    plan = {(1, "mafia", 1): {"target": 4}, (1, "night", 3): {"target": 4},
            (3, "mafia", 0): {"target": 5}, (3, "mafia", 1): {"target": 5}, (3, "night", 3): {"target": 5}}
    g = play(["대부", *BASE], plan, days=3)
    assert g.players[4].alive  # night 1: the doctor's save holds
    assert g.players[0].contacted and not g.players[5].alive  # night 3: it does not


# ---- 시민 팀 ----------------------------------------------------------------------------------------------------
def test_vigilante_checks_once_by_day_and_kills_the_mafia_found():
    g = play(["자경단원", *BASE], {(2, "vote", 0): {"check": 1}, (2, "night", 0): {"target": 1}}, days=2)
    assert "마피아입니다" in private_to(g, 0)
    assert not g.players[1].alive and g.result is not None and g.result["team"] == "시민"
    vote_prompts = [u for st, k, _s, u in g.log if st == 0 and k == "vote"]
    assert "check" in vote_prompts[0]


def test_informant_learns_a_citizen_each_morning():
    g = play(["정보원", *BASE], {}, days=2)
    assert private_to(g, 0).count("정보:") == 2 and "마피아" not in private_to(g, 0).replace("마피아 팀", "")


def test_liaison_links_with_the_same_team_only():
    g = play(["연락관", *BASE], {(1, "night", 0): {"target": 2}, (2, "night", 0): {"target": 1}}, days=2)
    assert f"{name(g, 2)}님은 경찰이다" in private_to(g, 0) and "연락관" in private_to(g, 2)
    assert f"{name(g, 1)}님과는 이어지지 않았다" in private_to(g, 0) and "연락관" not in private_to(g, 1)


def test_flagbearer_alive_on_day_four_wins_for_its_team():
    g = play(["기수", *BASE], {}, days=4)
    assert g.result is not None and g.result["team"] == "시민" and g.result["day"] == 4
    assert "4번째 낮까지 살아남았습니다" in g.result["reason"]


def test_foreman_turns_the_verdict_and_then_decides_alone():
    plan = {(2, "vote", s): {"vote": 4} for s in range(6) if s != 4}
    plan |= {(2, "verdict", s): {"verdict": "찬성"} for s in (1, 2, 3, 5)} | {(2, "verdict", 0): {"verdict": "반대"}}
    g = play(["배심장", *BASE], plan, days=2)
    assert g.players[4].alive and g.players[0].revealed and g.players[0].state.get("ruling")
    assert f"배심장 {name(g, 0)}님이 찬반 결과를 뒤집었습니다" in public(g)


def test_assistant_finds_the_doctor_and_saves_in_its_place():
    g = play(["조수", *BASE], {(1, "night", 0): {"target": 3}})
    assert f"{name(g, 3)}님이 의사다" in private_to(g, 0) and "조수" in private_to(g, 3)
    g = play(["조수", "마피아", "경찰", "시민", "시민", "시민"], {(1, "night", 0): {"target": 4}, (1, "mafia", 1): {"target": 4}})
    assert g.players[4].alive  # no 의사: the assistant saves


def test_illusionist_attacked_lets_the_tricked_player_die_instead():
    g = play(["환술사", *BASE], {(1, "night", 0): {"target": 4}, (1, "mafia", 1): {"target": 0}})
    assert g.players[0].alive and not g.players[4].alive
    assert "대신 죽었다" in private_to(g, 0)


def test_fixer_kills_each_night_after_its_client_dies_at_night():
    roles = ["해결사", *BASE]
    g0 = play(roles, {})  # the same seed deals the same client
    client = g0.by_name(g0.players[0].state["client"]).seat
    g = play(roles, {(1, "mafia", 1): {"target": client}, (2, "night", 0): {"target": 1}}, days=2)
    assert not g.players[client].alive and g.players[0].state.get("armed")
    assert not g.players[1].alive


def test_wiretapper_learns_the_role_when_night_falls():
    g = play(["도청꾼", *BASE], {(2, "vote", 0): {"tap": 2}}, days=2)
    assert f"도청 결과: {name(g, 2)}님의 직업은 경찰입니다" in private_to(g, 0)


def test_face_reader_compares_two_players():
    g = play(["관상가", *BASE], {(1, "night", 0): {"target": 1, "second": 4}, (2, "night", 0): {"target": 2, "second": 4}}, days=2)
    assert "다른 팀이다" in private_to(g, 0) and "같은 팀이다" in private_to(g, 0)


def test_archivist_finds_a_role_and_the_shadow_sees_no_player_named():
    g = play(["기록관", "미행꾼", "마피아", "경찰", "의사", "시민"],
             {(1, "night", 0): {"target": "경찰"}, (1, "night", 1): {"target": 0}})
    assert f"기록 결과: 경찰은 {name(g, 3)}님이다" in private_to(g, 0)
    assert "아무에게도 능력을 쓰지 않았다" in private_to(g, 1)


def test_enchanter_wakes_a_spellbound_mafia_and_learns_the_role():
    g = play(["주술사", *BASE], {(1, "night", 0): {"target": 1}, (2, "vote", 0): {"wake": 1}}, days=2)
    assert f"{name(g, 1)}님의 직업은 마피아다" in private_to(g, 0)


def test_astrologer_sees_two_roles_one_of_them_true():
    g = play(["점성가", *BASE], {(1, "night", 0): {"target": 1}})
    line = next(t for t in private_to(g, 0).splitlines() if t.startswith("점괘"))
    assert "마피아" in line and "가운데 하나다" in line


def test_gossip_hears_what_a_citizen_learned():
    g = play(["소문꾼", "마피아", "기록관", "의사", "시민", "시민"], {(1, "night", 2): {"target": "의사"}})
    assert f"소문: {name(g, 3)}님의 직업은 의사라고 한다" in private_to(g, 0)
