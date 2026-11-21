"""every pair of roles that can share a 복잡한 마피아 game is played through scripted nights and days, and
the invariants hold: the game ends with a team, the lineup is as dealt, dead players never act, no one dies twice,
targets are seats in the game, and a private line reaches only the prompts of the seats allowed to see it.
The pairs are generated from the role table, so a new role brings its pairs with it."""
from __future__ import annotations

import itertools

import pytest

from nmb.engine.roles import COMPLEX, GAME_ROLES, MAFIA, ROLES
from nmb.engine.setup import GameSetup, playable

from .helpers import run_game, seats
from .test_isolation import marking

ROLES_IN_PLAY = [r for r in GAME_ROLES[COMPLEX] if playable(r) and r not in ("시민", "마피아")]
PAIRS = list(itertools.combinations(ROLES_IN_PLAY, 2))
N = 8


def counts_for(a: str, b: str) -> dict[str, int]:
    counts = {r: 2 if r == "연인" else 1 for r in (a, b)}
    helpers = sum(1 for r in (a, b) if ROLES[r].team == MAFIA)
    counts["마피아"] = 1 if helpers else 2
    return counts


def test_the_pairs_cover_the_whole_pool() -> None:
    assert len(ROLES_IN_PLAY) >= 15 and len(PAIRS) == len(ROLES_IN_PLAY) * (len(ROLES_IN_PLAY) - 1) // 2


@pytest.mark.parametrize("a,b", PAIRS, ids=[f"{a}+{b}" for a, b in PAIRS])
def test_a_pair_of_roles_plays_cleanly(a: str, b: str) -> None:
    counts = counts_for(a, b)
    seed = PAIRS.index((a, b)) + 1
    s = GameSetup(kind=COMPLEX, seats=seats(N), role_mode="custom", counts=counts, seed=seed, max_nights=3)
    assert s.problem() is None
    g, log = run_game(s, marking)
    assert g.result is not None and g.result["team"] in ("시민", "마피아", "교주")
    dealt = sorted(p.start_role for p in g.players)
    for role, k in counts.items():
        assert dealt.count(role) == k, (role, dealt)
    names = {p.seat for p in g.players}
    dead: set[int] = set()
    for e in g.events:
        if e.kind == "death":
            assert e.target in names and e.target not in dead, (a, b, e.text)
            dead.add(e.target)
        elif e.kind == "revive":  # 부활술사, 불사신: back in the game
            assert e.target in dead, (a, b)
            dead.discard(e.target)
        elif e.kind == "action" and e.data.get("role") == "사냥꾼":  # the last shot comes after the execution
            continue
        elif e.kind in ("action", "say", "whisper", "vote") and e.actor is not None:
            assert e.actor not in dead, (a, b, e.kind, e.text)
            assert e.target is None or e.target in names
    seen = {seat: {e.text for e in g.events if e.log and (e.to is None or seat in e.to)} for seat in names}
    prompts = {seat: "\n".join(s + "\n" + u for st, _k, s, u in log if st == seat) for seat in names}
    checked = 0
    for e in g.events:
        if not e.log or e.to is None or len(e.text) < 6:
            continue
        for seat in names - set(e.to):
            if e.text not in seen[seat]:
                assert e.text not in prompts[seat], (a, b, e.kind, seat, e.text)
                checked += 1
    assert checked > 0  # the mafia chat and whispers at least were private
