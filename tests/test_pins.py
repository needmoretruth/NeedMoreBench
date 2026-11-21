"""AL1,: 직접's counts and the roles set on seats are one model. The user's saved lobby (10 players,
직접, 마피아 1 and 경찰 9, seats set to 의사, 시민 x3, 경찰, 마피아 x2) opened refusing to start with 「직업 수가 인원보다
많습니다」; in 참가 their own 마피아 seat made it worse. Now the newest action wins and the rest gives way."""
from __future__ import annotations

from collections import Counter

from nmb.engine.lineups import counted_lineup, counts_problem
from nmb.engine.pins import cover_pins, set_count
from nmb.engine.setup import GameSetup, SeatSpec, playable, seat_players

import random

OWNER_PINS = ["의사", "시민", "시민", "경찰", "마피아", "마피아", "시민", None, None, None]


def owner_setup(pins: list[str | None], counts: dict[str, int], kind: str = "simple") -> GameSetup:
    return GameSetup(kind=kind, role_mode="custom", counts=counts,
                     seats=[SeatSpec(kind="ai", model_key="test:t/m", role=r) for r in pins])


def agrees(setup: GameSetup) -> None:
    """Startable, and every seat gets the role set on it."""
    assert counts_problem(setup, playable) is None and setup.problem() is None
    roles = counted_lineup(setup.counts, len(setup.seats), [s.role for s in setup.seats if s.role])
    assert len(roles) == len(setup.seats)
    have = Counter(roles)
    for r, c in Counter(s.role for s in setup.seats if s.role).items():
        assert have[r] >= c, r
    players = seat_players(setup, random.Random(3))
    assert all(p.role == s.role for p, s in zip(players, setup.seats) if s.role)


def test_the_saved_lobby_refused_before_and_opens_agreeing() -> None:
    before = owner_setup(OWNER_PINS, {"마피아": 1, "경찰": 9})
    assert counts_problem(before, playable) == "too_many"  # the refusal the user saw
    f = cover_pins(before.counts, 10, OWNER_PINS)
    assert f.counts == {"마피아": 2, "경찰": 4, "의사": 1} and not f.unpin
    assert ("경찰", 9, 4) in f.changed and ("마피아", 1, 2) in f.changed  # said on the lobby's note
    agrees(owner_setup(OWNER_PINS, f.counts))


def test_in_play_his_own_mafia_seat_is_part_of_the_count() -> None:
    pins = ["마피아"] + OWNER_PINS  # the person's seat comes first in 참가
    f = cover_pins({"마피아": 1, "경찰": 9}, 11, pins)
    assert f.counts["마피아"] == 3
    agrees(owner_setup(pins, f.counts))


def test_setting_the_stepper_to_his_lineup_unsets_the_seats_in_the_way() -> None:
    f = cover_pins({"마피아": 1, "경찰": 9}, 10, OWNER_PINS)
    g = set_count(f.counts, 10, OWNER_PINS, "경찰", 9)  # then 마피아 1, 경찰 9, 시민 0: the lineup he asked for
    pins = [None if i in g.unpin else p for i, p in enumerate(OWNER_PINS)]
    assert g.counts == {"마피아": 1, "경찰": 9}
    assert Counter(p for p in pins if p) == Counter({"경찰": 1, "마피아": 1})
    agrees(owner_setup(pins, g.counts))
    h = set_count(g.counts, 10, pins, "경찰", 0)  # lowering below a seat set to it unsets that seat
    assert 3 in h.unpin and h.counts == {"마피아": 1}


def test_a_seat_set_to_citizen_needs_a_citizen_place_and_lovers_stay_pairs() -> None:
    full = owner_setup(["시민", None, None, None], {"마피아": 1, "경찰": 3})
    assert counts_problem(full, playable) == "too_many"  # no 시민 left for the seat set to 시민
    f = cover_pins(full.counts, 4, ["시민", None, None, None])
    assert f.counts == {"마피아": 1, "경찰": 2}
    f = cover_pins({"마피아": 1}, 6, ["연인", None, None, None, None, None])
    assert f.counts["연인"] == 2
    g = set_count({"마피아": 1, "연인": 2, "의사": 2}, 6, [None] * 6, "경찰", 3)
    assert sum(g.counts.values()) <= 6 and g.counts.get("연인", 0) % 2 == 0 and g.counts["경찰"] == 3


def test_the_fixed_table_keeps_the_seat_just_set_and_unsets_the_rest() -> None:
    from nmb.engine.pins import fit_table
    from nmb.engine.roles import simple_lineup
    pins = ["마피아", None, "마피아", None, "마피아", None, None, None]  # 참가: their seat first, 기본 of 8 has 2 마피아
    assert fit_table(simple_lineup(8), 3, pins, keep=4) == [2]  # he just set seat 4: the older one gives way
    assert fit_table(simple_lineup(8), 3, pins, keep=None) == [4]  # a saved lobby: the last one gives way
    s = GameSetup(kind="simple", seats=[SeatSpec(kind="ai", model_key="test:t/m", role=r) for r in pins])
    assert s.problem()  # 「마피아 자리가 역할 수(2)보다 많습니다」 before
    s.seats[4].role = None
    assert s.problem() is None
    assert fit_table(None, 2, ["마피아", "스파이", "마피아", None, None, None], keep=0) == [2]


class Lobby:
    """The parts of the lobby page `lineup.fit` touches."""

    def __init__(self, setup: GameSetup, human: SeatSpec | None = None) -> None:
        self.setup, self.human, self.lineup_note = setup, human or SeatSpec(kind="human"), ""
        self.mode = "play" if human else "watch"

    def full_setup(self) -> GameSetup:
        s = GameSetup.from_json(self.setup.to_json())
        if self.mode == "play":
            s.seats.insert(0, SeatSpec(**self.human.__dict__))
        return s


def test_the_lobby_opens_his_saved_shape_startable_and_says_what_moved() -> None:
    import pytest
    pytest.importorskip("gi")
    from nmb.ui import lineup
    page = Lobby(owner_setup(OWNER_PINS, {"마피아": 1, "경찰": 9}), SeatSpec(kind="human", role="마피아"))
    assert page.full_setup().problem()  # what he met
    assert lineup.fit(page)
    assert page.full_setup().problem() is None and page.setup.counts == {"마피아": 3, "경찰": 4, "의사": 1}
    assert "4" in page.lineup_note and "9" in page.lineup_note  # 경찰 9 → 4 said
    lineup.fit(page, stepper=("경찰", 9))  # then he sets 경찰 9: their lineup, the seats in the way go back to 랜덤
    assert page.setup.counts == {"마피아": 1, "경찰": 9, "의사": 1} and page.full_setup().problem() is None  # 11 seats
    assert page.human.role == "마피아" and [x.role for x in page.setup.seats if x.role] == ["의사", "경찰"]


def test_every_single_action_on_random_lobbies_leaves_a_startable_agreeing_lineup() -> None:
    rng = random.Random(11)
    roles = ["마피아", "경찰", "의사", "시민"]
    for _ in range(400):
        n = rng.randint(4, 12)
        pins = [rng.choice(roles + [None, None]) for _i in range(n)]
        if sum(p == "마피아" for p in pins) * 2 >= n:
            continue
        counts = {r: rng.randint(0, n) for r in ("마피아", "경찰", "의사")}
        f = cover_pins(counts, n, pins)
        s = owner_setup(pins, f.counts)
        if counts_problem(s, playable) in ("no_mafia", "no_town"):
            continue  # a lineup with nobody on a side is said on the start button, not changed for him
        agrees(s)
        role = rng.choice(["마피아", "경찰", "의사"])
        g = set_count(f.counts, n, pins, role, rng.randint(0, n))
        pins2 = [None if i in g.unpin else p for i, p in enumerate(pins)]
        s2 = owner_setup(pins2, g.counts)
        if counts_problem(s2, playable) not in ("no_mafia", "no_town"):
            agrees(s2)
