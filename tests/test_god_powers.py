"""신의 권능: each power's legality, what it changes, who learns what, its record line and the
개입 mark; the god stays anonymous and a 계시 stands in the system prompt until lifted."""
from __future__ import annotations

from typing import Any, Callable

from nmb.engine import god
from nmb.engine.game import Game
from nmb.engine.setup import GameSetup
from tests.helpers import run_game, seats

Act = tuple[Callable[[Game, Any, Any], bool], Callable[[Game], Any]]


def play(acts: list[Act], n: int = 7, roles: dict[int, str] | None = None, seed: int = 3, **kw: Any):
    """A simple game where each act fires once, inside the game loop, the first time its condition holds on a
    call (before that call is answered)."""
    sp = seats(n)
    for s, r in (roles or {}).items():
        sp[s].role = r
    setup = GameSetup(kind="simple", seats=sp, seed=seed, max_nights=3, **kw)
    done: set[int] = set()
    out: dict[Any, Any] = {}
    calls = [0]

    def fn(game, p, req):  # called right after the Spy logged this call, so call numbers match the log
        answer, idx = None, calls[0]
        calls[0] += 1
        for i, (when, do) in enumerate(acts):
            if i not in done and when(game, p, req):
                done.add(i)
                out["at", i] = idx  # this call's prompt was built before the act
                out[i] = do(game)
                answer = out[i] if isinstance(out[i], dict) else answer  # an act may answer this call too
        return answer

    g, log = run_game(setup, fn)
    return g, log, out


def at(kind: str, seat: int | None = None, day: int | None = None) -> Callable[[Game, Any, Any], bool]:
    return lambda g, p, r: r.kind == kind and (seat is None or p.seat == seat) and (day is None or g.day == day)


def records(g: Game, power: str) -> list:
    return [e for e in g.events if e.kind == "god" and e.data.get("record") and e.data.get("power") == power]


def player_sees(g: Game, seat: int) -> list:
    return [e for e in g.events if e.visible_to(seat) and e.log]


def test_twenty_one_powers_in_four_groups() -> None:
    assert [k for k, _ps in god.GROUPS] == ["말", "정보", "생사와 역할", "진행"]
    assert len(god.POWERS) == 21 and len(set(god.POWERS)) == 21  # the nine of and twelve new
    assert set(god.APPLY) | {"일시정지"} == set(god.POWERS)
    assert set(god.EN) == set(god.POWERS)


def test_legality_and_reasons() -> None:
    seen: dict[str, Any] = {}

    def look(g: Game) -> None:
        seen["night"] = {p: god.why_not(g, p, 1, 2, inputs=False) for p in god.POWERS}
        seen["revive_living"] = god.why_not(g, "부활", 1)
        seen["no_target"] = god.why_not(g, "천벌")
        seen["same_two"] = god.why_not(g, "역할 맞바꾸기", 1, 1)
        seen["citizen_fake"] = god.why_not(g, "거짓 결과", 6, inputs=False)
        seen["empty_text"] = god.why_not(g, "공지", text=" ")

    g, _log, _ = play([(at("night", day=1), look)], roles={0: "경찰", 6: "시민"})
    night = seen["night"]
    assert night["사면"] == "trial" and night["재투표"] == "after_vote"
    assert night["발언 시키기"] == "day" and night["토론 시간 조절"] == "talk" and night["빙의"] == "day"
    assert night["정체 공개"] == "named"
    assert night["천벌"] is None and night["보호"] is None and night["다음 단계로"] is None
    assert seen["revive_living"] == "alive" and seen["no_target"] == "pick" and seen["same_two"] == "pick_two"
    assert seen["citizen_fake"] == "no_result" and seen["empty_text"] == "text"
    assert all(v == "over" for v in god.available(g, 1).values())
    assert set(god.REASONS) >= {r for r in night.values() if r}
    assert not g.god("천벌", 1)  # a finished game ignores late clicks


def test_announce_is_public_and_does_not_mark_the_game() -> None:
    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("공지", text="오늘은 비가 온다"))])
    assert {s for s, k, sy, u in log if "신의 공지: 오늘은 비가 온다" in u} >= {p.seat for p in g.players if p.alive}
    rec = records(g, "공지")[0]
    assert rec.to == frozenset() and not rec.log and rec.data["used_by"] == "관전자"
    assert not god.intervened(g.events)


def test_revelation_stands_in_the_system_prompt_until_lifted() -> None:
    def lift(g: Game) -> None:
        rid = g.players[2].revelations[0][0]
        assert g.god(god.LIFT, 2, n=rid)

    word = "너는 오늘 3번을 의심한다"
    g, log, out = play([(at("intro", 0, 1), lambda g: g.god("계시", 2, word)), (at("discuss", day=2), lift)])
    given, lifted = out["at", 0], out["at", 1]
    standing = [(i, s, sy) for i, (s, k, sy, u) in enumerate(log) if given < i <= lifted]
    assert [s for i, s, sy in standing if s == 2], "seat 2 had calls while the revelation stood"
    for i, s, sy in standing:
        assert (word in sy) == (s == 2), (i, s)  # on every call of seat 2, on nobody else's
    mine = next(sy for i, s, sy in standing if s == 2)
    assert "신의 계시" in mine and "게임 규칙과 같은 무게" in mine
    assert not any(word in sy for i, (s, k, sy, u) in enumerate(log) if i <= given or i > lifted)
    assert not any(word in u for i, (s, k, sy, u) in enumerate(log) if i <= lifted)  # a system block, not a log line
    ev = next(e for e in g.events if e.kind == "god" and e.data.get("power") == "계시" and e.data.get("god_effect"))
    assert ev.to == frozenset({2}) and not ev.log  # the player's own screen shows it
    later = [u for i, (s, k, sy, u) in enumerate(log) if i > lifted and s == 2]
    assert not later or any("계시를 거뒀다" in u for u in later)
    assert god.intervened(g.events) and records(g, god.LIFT)


def test_forged_whisper_looks_real_to_the_receiver_and_the_sender_never_knows() -> None:
    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("속삭임 위조", 1, "나 마피아 아니야, 믿어 줘", other=4))])
    a, b = g.players[1], g.players[4]
    assert any(f"(귓속말) {b.name} → 너: 나 마피아 아니야, 믿어 줘" in u for s, k, sy, u in log if s == 1)
    assert not any("나 마피아 아니야, 믿어 줘" in u for s, k, sy, u in log if s != 1)
    w = next(e for e in g.events if e.kind == "whisper" and e.data.get("forged"))
    assert w.actor == b.seat and w.target == a.seat and w.to == frozenset({a.seat})
    assert records(g, "속삭임 위조")[0].data["sender"] == b.seat


def test_possession_reads_as_the_players_own_line_to_everyone() -> None:
    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("빙의", 3, "제가 경찰입니다"))])
    line = f"{g.players[3].name}: 제가 경찰입니다"
    assert {s for s, k, sy, u in log if line in u} == set(range(7))
    say = next(e for e in g.events if e.kind == "say" and e.data.get("possessed"))
    assert say.actor == 3 and say.to is None and records(g, "빙의")


def test_question_goes_to_the_next_prompt_and_the_answer_only_to_the_god() -> None:
    def answer(g: Game, p: Any, r: Any) -> bool:
        return r.kind == "interrogate"

    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("심문", 5, "너 마피아야?")),
                      (answer, lambda g: {"say": "나는 그냥 시민이라 아는 게 없다"})])
    asked = next(x for x in log if x[1] == "interrogate")
    assert asked[0] == 5 and "신의 질문(너에게만, 답은 신만 본다): 너 마피아야?" in asked[3]
    ans = next(e for e in g.events if e.kind == "god" and e.data.get("answer"))
    assert ans.to == frozenset({5}) and ans.text == "나는 그냥 시민이라 아는 게 없다"
    assert any("(신에게 한 답) 나는 그냥 시민이라" in u for s, k, sy, u in log if s == 5)
    assert not any("너 마피아야?" in u or ans.text in u for s, k, sy, u in log if s != 5)
    assert not g.divine.asking


def test_false_result_arrives_like_a_real_one() -> None:
    def fake(g: Game) -> None:
        assert god.result_choices(g, g.players[0]) == god.VERDICTS
        assert g.god("거짓 결과", 0, role="마피아가 아닙니다")

    g, log, _ = play([(at("discuss", 0, 1), fake), (at("night", 0, 1), lambda g: {"target": g.players[1].name})],
                     roles={0: "경찰", 1: "마피아"})
    res = [e for e in g.events if e.kind == "private" and e.to == frozenset({0}) and "result" in e.data]
    first = res[0]
    assert first.data["false_result"] and first.data["real_result"] == "마피아입니다"
    assert first.text == f"조사 결과: {g.players[1].name}님은 마피아가 아닙니다."
    assert any(first.text in u for s, k, sy, u in log if s == 0)
    assert records(g, "거짓 결과")[0].to == frozenset()
    assert all(not e.data.get("false_result") for e in res[1:])  # only the next result


def test_reveal_role_and_reveal_model() -> None:
    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("역할 공개", 2))])
    assert g.players[2].revealed and any(f"직업은 {g.players[2].role}입니다" in u for s, k, sy, u in log if s == 4)
    g2, log2, _ = play([(at("discuss", day=1), lambda g: g.god("정체 공개", 2))], named=False)
    model = g2.players[2].model_name
    assert model and any(f"정체는 {model}입니다" in u for s, k, sy, u in log2 if s == 4)
    g3, _l, _ = play([(at("discuss", day=1), lambda g: g.god("정체 공개", 2))])
    assert not records(g3, "정체 공개")  # a named game has nothing to reveal


def test_life_and_role_powers_change_the_state() -> None:
    acts: list[Act] = [(at("discuss", day=1), lambda g: g.god("천벌", 6)),
                       (at("vote", day=2), lambda g: g.god("부활", 6)),
                       (at("discuss", 1, 1), lambda g: g.god("역할 바꾸기", 1, role="의사")),
                       (at("discuss", 2, 1), lambda g: g.god("역할 맞바꾸기", 2, other=3)),
                       (at("intro", 4, 1), lambda g: g.god("보호", 4))]
    g, log, _ = play(acts, roles={1: "시민", 2: "경찰", 3: "시민", 6: "시민"})
    assert any(e.kind == "death" and e.target == 6 and e.data["cause"] == "god" for e in g.events)
    assert records(g, "부활") or not g.players[6].alive
    assert records(g, "역할 바꾸기")[0].data["changed"]["role"] == {"from": "시민", "to": "의사"}
    assert "시민에서 의사로 바꿨습니다" in records(g, "역할 바꾸기")[0].text  # a real particle, never 「(으)로」
    assert not any("(으)로" in e.text for e in g.events)
    assert any("신이 네 직업을 바꿨다. 이제 너는 의사다." in u for s, k, sy, u in log if s == 1)
    assert any("이제 너는 경찰이다" in u for s, k, sy, u in log if s == 3)
    assert any("이제 너는 시민이다" in u for s, k, sy, u in log if s == 2)
    assert not any("맞바꿨다" in u for s, k, sy, u in log if s not in (2, 3))
    assert records(g, "보호") and not any("보호" in u for s, k, sy, u in log)


def test_silence_and_taking_a_vote() -> None:
    def take(g: Game) -> int:
        q = g.alive()[-1]
        assert g.god("투표권 박탈", q.seat)
        return q.seat

    g, log, out = play([(at("intro", 0, 1), lambda g: g.god("침묵", 3)), (at("discuss", day=2), take)],
                       roles={3: "경찰"})  # a night call of its own reads the notice
    assert not any(e.kind == "say" and e.actor == 3 and e.day == 1 for e in g.events)
    assert any("신이 너를 침묵시켰다" in u for s, k, sy, u in log if s == 3)
    q = out[1]
    assert not any(s == q and k == "vote" and day == 2 for s, k, day in _calls(g, log))
    assert any("신이 너의 투표권을 빼앗았다" in u for s, k, sy, u in log if s == q)


def _calls(g: Game, log: list) -> list[tuple[int, str, int]]:
    out = []
    for s, k, sy, u in log:
        day = int(u.split("지금: ")[1].split("번째")[0]) if "지금: " in u else 0
        out.append((s, k, day))
    return out


def test_pardon_and_revote() -> None:
    g, log, _ = play([(at("defense"), lambda g: g.god("사면"))], seed=5)
    pardon = records(g, "사면")
    assert pardon and any(e.kind == "system" and "신의 사면으로" in e.text for e in g.events)
    cand = pardon[0].target
    assert not any(e.kind == "death" and e.target == cand and e.data["cause"] == "execution" and e.day == pardon[0].day
                   for e in g.events)
    g2, log2, _ = play([(at("vote", day=2), lambda g: g.god("재투표"))], seed=5)
    steps = [e for e in g2.events if e.kind == "step" and e.day == 2 and e.data.get("step") == "투표"]
    assert len(steps) == 2 and records(g2, "재투표")
    first_vote = [e for e in g2.events if e.kind == "vote_result" and e.day == 2]
    assert len(first_vote) == 1  # the thrown-away vote is never counted


def test_give_the_floor_and_talk_time() -> None:
    g, log, _ = play([(at("discuss", 0, 1), lambda g: g.god("발언 시키기", 4)),
                      (at("discuss", 0, 1), lambda g: g.god("토론 시간 조절", n=3))])
    day1 = [s for s, k, sy, u in log if k == "discuss" and "지금: 1번째 낮" in u]
    assert day1[day1.index(0) + 1] == 4
    rec = records(g, "토론 시간 조절")[0]
    assert rec.data["changed"]["turns_left"]["to"] == rec.data["changed"]["turns_left"]["from"] + 3
    assert any("신이 남은 발언 차례를 3번 늘렸습니다" in u for s, k, sy, u in log)


def test_next_step_and_pause() -> None:
    g, _log, _ = play([(at("intro", 2, 1), lambda g: g.god("다음 단계로"))])
    assert records(g, "다음 단계로")
    assert not any(e.kind == "say" and e.data.get("intro") and e.actor and e.actor > 2 for e in g.events)


def test_the_god_stays_anonymous() -> None:
    g, log, _ = play([(at("discuss", day=1), lambda g: g.god("천벌", 3, user=0)),
                      (at("discuss", day=1), lambda g: g.god("빙의", 2, "안녕", user=0))])
    for e in g.events:
        if "used_by" in e.data:
            assert e.to == frozenset() and not e.log  # who used it: god-only details
    assert records(g, "천벌")[0].data["used_by"] == 0
    assert all(str(god.RULE) in sy for s, k, sy, u in log)
    _g, log_off, _ = play([], god_powers=False)
    assert not any(str(god.RULE) in sy for s, k, sy, u in log_off)


def test_intervened_reads_events_and_saved_records() -> None:
    assert not god.intervened([{"kind": "god", "details": {"power": "공지"}}, {"kind": "pause", "details": {}}])
    assert god.intervened([{"kind": "god", "details": {"power": "침묵"}}])
    g, _log, _ = play([(at("discuss", day=1), lambda g: g.god("침묵", 1))])
    from nmb.store import event_record
    assert god.intervened(g.events) and god.intervened([event_record(e) for e in g.events])


def test_an_intervened_game_is_left_out_of_ratings() -> None:
    from nmb.rating import row_from_saved
    header = {"settings": {"kind": "simple"}, "seats": [{"seat": 0, "kind": "ai", "model": "a", "role": "시민"},
                                                        {"seat": 1, "kind": "ai", "model": "b", "role": "마피아"}]}
    result = {"team": "시민", "roles": {}}
    assert row_from_saved(header, [{"kind": "god", "details": {"power": "공지"}}], result) is not None
    assert row_from_saved(header, [{"kind": "god", "details": {"power": "천벌"}}], result) is None


def test_balance_leaves_out_games_the_god_meddled_in(tmp_path) -> None:  # noqa: ANN001
    import json
    from nmb.balance import read_lineups
    for name, god_line in (("plain", {"kind": "god", "details": {"power": "공지"}}),
                           ("meddled", {"kind": "god", "details": {"power": "천벌"}})):
        lines = [{"record": "header", "game": "simple", "seats": []}, god_line,
                 {"record": "result", "team": "시민", "roles": {"0": "시민", "1": "마피아"}}]
        (tmp_path / f"{name}.nmb.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    assert len(read_lineups(tmp_path)) == 1
