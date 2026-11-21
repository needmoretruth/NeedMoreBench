"""직접 lineups and the roles set on seats (AL1): one model, the seats' roles are part of the counts.

A seat set to 경찰 uses one of the 경찰 in the count; a seat set to 시민 uses one of the 시민 that fill the rest.
So the counts always cover the seats' roles and add up to at most the players. When an action breaks that, the
newest action wins and the other side gives way, and the lobby says what changed:

- a seat's role (or a saved lobby, or a changed player count): the counts rise to cover the seats; if that makes
  more roles than players, the counts with the most unset copies come down (the mafia last, never below one);
- a stepper: the count is what the person set; seats set to that role beyond it lose their setting, and when the
  count needs room, seats set to 시민 give it first, then other counts' unset copies, then other seats' settings.

GTK-free: the lobby calls these, the tests call them directly.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .roles import MAFIA, ROLES

CITIZEN = "시민"


@dataclass
class Fit:
    counts: dict[str, int]
    unpin: list[int] = field(default_factory=list)  # seat indices whose role setting goes back to 랜덤
    changed: list[tuple[str, int, int]] = field(default_factory=list)  # (role, old count, new count)

    @property
    def nothing(self) -> bool:
        return not self.unpin and not self.changed


def _step(role: str) -> int:
    return 2 if role == "연인" else 1


def _shrink_order(counts: dict[str, int], pins: Counter[str], keep: str | None, mafia_floor: int = 1) -> list[str]:
    """Roles whose unset copies may go, the most unset first; the mafia last and never below one."""
    def spare(r: str) -> int:
        floor = max(pins[r], mafia_floor if r == "마피아" else 0)
        return counts[r] - floor
    cands = [r for r in counts if r != keep and spare(r) >= _step(r)]
    return sorted(cands, key=lambda r: (ROLES[r].team == MAFIA, -spare(r), r))


def _room(counts: dict[str, int], n: int, citizens: int) -> int:
    return sum(counts.values()) + citizens - n  # > 0: that many too many


def cover_pins(counts: dict[str, int], n: int, pins: list[str | None]) -> Fit:
    """The seats' roles win: counts rise to cover them, other counts' unset copies give way."""
    have = Counter(p for p in pins if p)
    new = {r: c for r, c in counts.items() if r != CITIZEN and c > 0}
    for r, c in have.items():
        if r != CITIZEN and new.get(r, 0) < c:
            new[r] = c + (c % 2 if r == "연인" else 0)
    while _room(new, n, have[CITIZEN]) > 0:
        order = _shrink_order(new, have, None)
        order = order or _shrink_order(new, have, None, mafia_floor=0)  # every seat set to the town: no mafia left,
        if not order:  # which the start button says
            break  # the seats alone fill more than the table; the start button says so
        r = order[0]
        new[r] -= _step(r)
    return _result(counts, new, [])


def set_count(counts: dict[str, int], n: int, pins: list[str | None], role: str, value: int) -> Fit:
    """The stepper wins: role's count is value; seats beyond it, then seats set to 시민, then other counts give way."""
    have = Counter(p for p in pins if p)
    new = {r: c for r, c in counts.items() if r != CITIZEN and c > 0}
    new[role] = max(0, min(value, n - 1 - ((n - 1) % 2 if role == "연인" else 0)))  # the other side keeps a seat
    unpin: list[int] = []
    extra = have[role] - new[role]
    for i in reversed(range(len(pins))):  # the last seats set to it lose their setting first
        if extra <= 0:
            break
        if pins[i] == role:
            unpin.append(i)
            extra -= 1
    left = [None if i in unpin else p for i, p in enumerate(pins)]
    have = Counter(p for p in left if p)
    for i in reversed(range(len(left))):  # room for the count: seats set to 시민 first
        if _room(new, n, have[CITIZEN]) <= 0:
            break
        if left[i] == CITIZEN:
            unpin.append(i)
            left[i] = None
            have[CITIZEN] -= 1
    while _room(new, n, have[CITIZEN]) > 0:  # then other counts' unset copies
        order = _shrink_order(new, have, role)
        if not order:
            break
        new[order[0]] -= _step(order[0])
    for i in reversed(range(len(left))):  # then other seats' settings, with their count
        if _room(new, n, have[CITIZEN]) <= 0:
            break
        r = left[i]
        if r and r != role and new.get(r, 0) > (1 if r == "마피아" else 0):
            unpin.append(i)
            left[i] = None
            have[r] -= 1
            new[r] -= 1
    return _result(counts, {k: v for k, v in new.items() if v > 0 or k == role}, sorted(unpin))


def fit_table(table: dict[str, int] | None, mafia_cap: int, pins: list[str | None], keep: int | None) -> list[int]:
    """기본 and 정해진 구성 have a fixed table: seats set to a role beyond its count go back to 랜덤, the seat just set
    (`keep`) stays; so do mafia-team seats beyond `mafia_cap`. Returns the seat indices that give way."""
    order = [i for i in reversed(range(len(pins))) if i != keep] + ([keep] if keep is not None else [])
    left = list(pins)
    unpin: list[int] = []

    def drop(over: Callable[[str], bool]) -> None:
        for i in order:
            r = left[i]
            if r and over(r):
                unpin.append(i)
                left[i] = None
    if table is not None:
        drop(lambda r: sum(1 for p in left if p == r) > table.get(r, 0))
    drop(lambda r: ROLES[r].team == MAFIA and sum(1 for p in left if p and ROLES[p].team == MAFIA) > mafia_cap)
    return sorted(unpin)


def _result(old: dict[str, int], new: dict[str, int], unpin: list[int]) -> Fit:
    roles = sorted((set(old) | set(new)) - {CITIZEN}, key=lambda r: list(ROLES).index(r) if r in ROLES else 999)
    changed = [(r, old.get(r, 0), new.get(r, 0)) for r in roles if old.get(r, 0) != new.get(r, 0)]
    return Fit({r: c for r, c in new.items() if c > 0}, unpin, changed)
