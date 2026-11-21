"""신의 권능 in an English game: what the players meet, the rule and the 계시 block in the system
prompt, and the god's own record lines read in English; the record keeps each line's message."""
from __future__ import annotations

from nmb.engine import god
from nmb.engine.text import Msg
from tests.test_god_powers import at, play, records


def test_revelation_block_and_rule_are_english() -> None:
    word = "Suspect the quietest player first."
    g, log, out = play([(at("intro", 0, 1), lambda g: g.god("계시", 2, word))], language="en")
    after = [sy for i, (s, k, sy, u) in enumerate(log) if i > out["at", 0] and s == 2]
    assert after and all("God's revelation" in sy and word in sy for sy in after)
    assert all("신" not in sy for sy in after)  # no Korean head, rule or block line in an English game
    assert all("a god may step into this game" in sy for s, k, sy, u in log)


def test_player_lines_are_english() -> None:
    acts = [(at("discuss", day=1), lambda g: g.god("공지", text="Be calm.")),
            (at("discuss", 1, 1), lambda g: g.god("침묵", 6)),
            (at("discuss", 2, 1), lambda g: g.god("역할 바꾸기", 4, role="의사")),
            (at("discuss", 3, 1), lambda g: g.god("천벌", 5)),
            (at("discuss", 4, 1), lambda g: g.god("심문", 1, "Who do you suspect?"))]
    g, log, _ = play(acts, roles={4: "시민", 5: "시민"}, language="en")
    seen = "\n".join(u for s, k, sy, u in log)
    assert "God's announcement: Be calm." in seen
    assert "The god silenced you. You cannot speak on day" in seen
    assert "The god changed your role. You are now the Doctor." in seen
    assert "Lightning struck from the sky." in seen
    assert "God's question (to you alone; only the god sees your answer): Who do you suspect?" in seen
    assert not any(ch in seen for ch in "벼락침묵공지질문")


def test_false_result_and_records_in_english() -> None:
    def fake(g) -> None:  # noqa: ANN001
        assert g.god("거짓 결과", 0, role="마피아가 아닙니다")

    g, log, _ = play([(at("discuss", 0, 1), fake), (at("night", 0, 1), lambda g: {"target": g.players[1].name})],
                     roles={0: "경찰", 1: "마피아"}, language="en")
    res = next(e for e in g.events if e.kind == "private" and e.data.get("false_result"))
    assert res.text == f"Result: {g.players[1].name} is not Mafia."  # exactly a real English police line
    assert any(res.text in u for s, k, sy, u in log if s == 0)
    rec = records(g, "거짓 결과")[0]
    assert rec.text.endswith('will read: "not Mafia"')
    assert Msg.load(rec.data["msg"]) is not None  # the screen can show it in the interface language


def test_every_god_line_is_a_message() -> None:
    acts = [(at("discuss", day=1), lambda g, p=p: g.god(p, 2, "words", role="의사", n=2))
            for p in ("공지", "빙의", "역할 공개", "투표권 박탈", "토론 시간 조절", "보호")]
    g, _log, _ = play(acts, roles={2: "시민"})
    lines = [e for e in g.events if e.kind == "god" and (e.data.get("record") or e.data.get("god_effect"))]
    typed = {"공지"}  # the god's own words go to the players as typed
    for e in lines:
        if e.data.get("god_effect") and e.data.get("power") in typed:
            continue
        assert "msg" in e.data, (e.data.get("power"), e.text)
    assert {e.data["power"] for e in lines if e.data.get("record")} >= {"공지", "역할 공개", "보호"}
    assert god.intervened(g.events)


def test_ro_particle_after_a_final_rieul() -> None:
    from nmb.engine.text import T, say
    line = T("{name}님의 직업을 {old}에서 {role:으로/로} 바꿨습니다.", name="가", old="시민", role="경찰")
    assert say("ko", line).endswith("경찰로 바꿨습니다.")
    assert say("ko", T("{name}님의 직업을 {old}에서 {role:으로/로} 바꿨습니다.", name="가", old="경찰", role="시민")).endswith("시민으로 바꿨습니다.")
