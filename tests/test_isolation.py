"""Information isolation in the prompts.

Every answer carries markers unique to its writer; the test then reads every prompt the engine built and
checks that a marker only reaches the seats that have the right to see it.
"""
from __future__ import annotations

import random

from nmb.engine.abilities import in_mafia_team
from nmb.engine.setup import GameSetup, SeatSpec

from .helpers import MODELS, run_game, seats


def marking(game, p, req):
    others = [q.name for q in game.alive() if q is not p]
    r = random.Random(p.seat * 1000 + len(game.events))
    obj = {"thought": f"속마음표식{p.seat}", "ledger": [{"name": others[0], "suspicion": 70, "note": f"비고표식{p.seat}"}],
           "notes": {"add": [f"노트표식{p.seat}"]}}
    if req.say:
        obj["say"] = f"{req.kind}발언표식{p.seat}"
    if req.whispers and others:
        obj["whispers"] = [{"to": others[0], "text": f"귓속말표식{p.seat}_{len(game.events)}"}]
    if req.field:
        obj[req.field] = r.choice(req.options)
    if req.hand:
        obj["hand"] = 2
    return obj


def prompts_of(log, seat):
    return [s + "\n" + u for st, _, s, u in log if st == seat]


def test_markers_reach_only_their_audience():
    g, log = run_game(GameSetup(kind="simple", seats=seats(8), seed=21), marking)
    mafia = {p.seat for p in g.players if in_mafia_team(p)}
    for seat in range(8):
        text = "\n".join(prompts_of(log, seat))
        for other in range(8):
            if other != seat:
                assert f"속마음표식{other}" not in text
                assert f"비고표식{other}" not in text
                assert f"노트표식{other}" not in text
            if other not in mafia or seat not in mafia:
                if other != seat:
                    assert f"mafia발언표식{other}" not in text, (seat, other)
    # whispers: only sender and receiver
    for e in g.events:
        if e.kind != "whisper":
            continue
        for seat in range(8):
            text = "\n".join(u for st, _, _, u in log if st == seat)
            if seat not in (e.actor, e.target):
                assert e.text not in text
    assert any(e.kind == "whisper" for e in g.events)
    # the mafia chat reaches the mafia
    m = min(mafia)
    assert any(f"mafia발언표식{o}" in "\n".join(prompts_of(log, m)) for o in mafia if o != m) or len(mafia) == 1


def test_police_result_only_for_police():
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=22), marking)
    results = [e for e in g.events if e.kind == "private" and e.text.startswith("조사 결과")]
    assert results
    police = results[0].to
    for seat in range(7):
        text = "\n".join(prompts_of(log, seat))
        if seat not in police:
            assert results[0].text not in text


def test_blind_prompts_have_no_model_maker_or_country():
    g, log = run_game(GameSetup(kind="simple", seats=seats(10), seed=23, named=False), marking)
    banned = {w for m in MODELS for w in m} | {"Flash", "Haiku", "GPT", "DeepSeek"}
    for _, _, s, u in log:
        for w in banned:
            assert w not in s and w not in u, w


def test_named_prompts_show_model_maker_country():
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=24, named=True), marking)
    _, _, s, u = log[0]
    assert "서로 어느 회사" in s
    for name, maker, country in MODELS[:7]:
        assert name in u and maker in u and country in u


def test_disguised_human_looks_like_the_model():
    sp = seats(6)
    sp[2] = SeatSpec(kind="human", human_name="Mina", disguise_key="test:t/x", disguise_name="Claude Haiku 5.5",
                     disguise_maker="Anthropic", disguise_country="미국")
    setup = GameSetup(kind="simple", seats=sp, seed=25, named=True)

    def human_too(game, p, req):
        return marking(game, p, req)
    g, log = run_game(setup, human_too)
    other = next(u for st, _, _, u in log if st != 2)
    line = next(x for x in other.splitlines() if x.startswith("3. "))
    assert "Claude Haiku 5.5, Anthropic, 미국" in line and "사람" not in line and "Mina" not in line


def test_vote_reveal_follows_the_setting():
    for public in (False, True):
        g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=26, vote_public=public), marking)
        v = next(e for e in g.events if e.kind == "vote_result")
        voters = [n for names in v.data["voters"].values() for n in names]
        assert v.data["votes"]  # the saved game keeps every vote either way
        if public:
            assert all(n in v.text for n in voters)
        else:
            assert "(" not in v.text
