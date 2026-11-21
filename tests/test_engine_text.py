"""engine text is a message key with parameters, rendered in the game's dialogue language."""
from __future__ import annotations

import json
import re
import string

import pytest

from nmb.engine.en import EN_TEXT
from nmb.engine.setup import COMPLEX, EN_NAMES, SIMPLE, GameSetup
from nmb.engine.text import Msg, T, from_word, lines, say
from nmb.engine.textkeys import all_keys
from nmb.engine.turn import TurnRequest
from nmb.harness import problem_with

from .helpers import run_game, seats

HANGUL = re.compile(r"[가-힣]")


def fields(template: str) -> set[str]:
    return {f for _lit, f, _spec, _conv in string.Formatter().parse(template) if f is not None}


def test_every_engine_message_has_english_with_the_same_parameters():
    keys = all_keys()
    missing = [k for k in keys if k not in EN_TEXT]
    assert not missing, missing[:5]
    for k in keys:
        assert fields(EN_TEXT[k]) == fields(k), k
        assert not HANGUL.search(EN_TEXT[k]), k


def test_english_particle_free_and_korean_picks_the_particle():
    m = T("{name}님은 {role:이었습니다/였습니다}.", name="Ava", role="경찰")
    assert m.render("ko") == "Ava님은 경찰이었습니다."
    assert T("{name}님은 {role:이었습니다/였습니다}.", name="Ava", role="의사").render("ko") == "Ava님은 의사였습니다."
    assert T("{text} {name}님은 {role:이었습니다/였습니다}.", text=T("밤사이 {name}님이 죽었습니다.", name="Ava"),
             name="Ava", role="경찰").render("en") == "Ava died in the night. Ava was the Police."


@pytest.mark.parametrize("kind,pool,seed,named", [(SIMPLE, "classic", 3, True), (COMPLEX, "full", 5, False),
                                                  (COMPLEX, "full", 8, False), (COMPLEX, "full", 11, True)])
def test_an_english_game_prompts_carry_no_korean(kind, pool, seed, named):
    n = 8 if kind == SIMPLE else 12
    g, log = run_game(GameSetup(kind=kind, seats=seats(n), language="en", seed=seed, expert=True, vote_public=True,
                                role_pool=pool, named=named))
    if not named:
        assert {p.name for p in g.players} <= set(EN_NAMES)
    assert log
    for seat, kind_, system, user in log:
        hit = HANGUL.search(system + user)
        assert hit is None, (kind_, (system + user)[max(0, hit.start() - 80):hit.start() + 80])
    shown = [e.text for e in g.events if e.text]  # every line the screen shows, private too
    assert all(not HANGUL.search(t) for t in shown), [t for t in shown if HANGUL.search(t)][:3]


def test_a_korean_game_still_reads_korean():
    g, log = run_game(GameSetup(kind=SIMPLE, seats=seats(8), language="ko", seed=3))
    assert all("Yes" not in s and "Rules" not in s for _seat, _k, s, _u in log)
    assert any("규칙" in s for _seat, _k, s, _u in log)


def test_english_answers_read_back_to_the_engine_words():
    assert from_word("en", "Yes") == "찬성" and from_word("en", " no ") == "반대"
    assert from_word("en", "Abstain") == "기권" and from_word("en", "None") == "없음"
    assert from_word("en", "Police") == "경찰" and from_word("en", "Unknown") == "모름"
    assert from_word("en", "Ava") == "Ava" and from_word("ko", "Yes") == "Yes"
    req = TurnRequest(kind="verdict", task="", field="verdict", options=["찬성", "반대"], skip_word="기권")
    assert problem_with({"verdict": "Yes"}, req, "en") is None
    assert problem_with({"verdict": "Abstain"}, req, "en") is None
    assert problem_with({"verdict": "Maybe"}, req, "en") is not None


def test_the_screen_shows_engine_lines_in_the_interface_language(monkeypatch):
    from nmb import i18n
    from nmb.view import line_text, result_text

    g, _log = run_game(GameSetup(kind=SIMPLE, seats=seats(6), language="ko", seed=3))
    death = next(e for e in g.events if e.kind == "death")
    action = next(e for e in g.events if e.kind == "action")
    monkeypatch.setattr(i18n, "current", "en")
    assert not HANGUL.search(line_text(death)) and HANGUL.search(death.text)
    assert not HANGUL.search(line_text(action, "what"))
    assert not HANGUL.search(result_text(g.result or {}, "label"))
    monkeypatch.setattr(i18n, "current", "ko")
    assert line_text(death) == death.text
    say_line = next(e for e in g.events if e.kind == "say")
    assert line_text(say_line) == say_line.text  # the players' own words stay as written


def test_a_message_record_loads_back_to_the_same_text():
    inner = T("{name}님이 처형되었습니다.", name="Ava")
    joined = lines(T("투표 시간입니다."), inner, "plain", sep="\n")
    outer = T("{text} {name}님은 {role:이었습니다/였습니다}.", text=inner, name="Ava", role="마피아")
    tally = T("투표 결과: {tally}", tally=[T("{name}님 {n}표", name="Ava", n=2), T("기권 {n}", n=1)])
    for m in (inner, joined, outer, tally):
        back = Msg.load(json.loads(json.dumps(m.record())))  # strict JSON: what the saved game holds
        assert back is not None
        assert back.render("ko") == m.render("ko") and back.render("en") == m.render("en")
    assert say("en", T("{n}번째 밤", n=2)) == "Night 2"


def test_every_saved_line_renders_again_in_both_languages():
    """What a replay on another interface language does: each event's message, through JSON, gives the line the
    game wrote and an English line with no Korean left."""
    g, _log = run_game(GameSetup(kind=COMPLEX, seats=seats(12), language="ko", seed=5, role_pool="full", vote_public=True))
    def sets_only(o: object) -> object:
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        raise TypeError(f"{o!r} would be saved as its Korean text")

    n = 0
    for e in g.events:
        json.dumps(e.data, default=sets_only)
        if "msg" not in e.data:
            continue
        m = Msg.load(json.loads(json.dumps(e.data["msg"])))
        assert m is not None and m.render("ko") == e.text, e.kind
        assert not HANGUL.search(m.render("en").replace(e.text if e.kind == "say" else "\0", "")), (e.kind, m.render("en"))
        n += 1
    assert n > 100
