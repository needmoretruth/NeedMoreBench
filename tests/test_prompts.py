"""The default prompt is minimal and the expert section is opt-in and versioned."""
from __future__ import annotations

from nmb.engine.expert import EXPERT_VERSION
from nmb.engine.setup import GameSetup

from .helpers import run_game, seats

# phrases of strategy advice or behaviour correction that the default prompt must never carry
COACHING = ["숨긴다", "시민인 척", "콕 집어", "되풀이하지", "빈말", "신중", "설득", "추리에 써도", "꼭 고친다",
            "전략", "의심해야", "조심"]


def test_default_prompt_has_no_coaching():
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=31))
    assert log
    for _, _, system, user in log:
        for w in COACHING:
            assert w not in system and w not in user, w


def test_expert_section_only_for_seats_with_the_switch():
    sp = seats(7)
    sp[3].expert = True
    g, log = run_game(GameSetup(kind="simple", seats=sp, seed=32))
    head = f"전문가 전략 (v{EXPERT_VERSION})"
    for seat, _, system, _ in log:
        assert (head in system) == (seat == 3)


def test_game_switch_sets_every_seat_and_a_seat_can_differ():
    sp = seats(6)
    sp[0].expert = False
    g, log = run_game(GameSetup(kind="simple", seats=sp, seed=33, expert=True))
    for seat, _, system, _ in log:
        assert ("전문가 전략" in system) == (seat != 0)


def test_expert_text_follows_the_side():
    g, log = run_game(GameSetup(kind="simple", seats=seats(7), seed=34, expert=True))
    for seat, _, system, _ in log:
        mafia = g.players[seat].start_role == "마피아"
        assert ("마피아 팀\n" in system) == mafia
        assert ("시민 팀\n" in system) == (not mafia)
