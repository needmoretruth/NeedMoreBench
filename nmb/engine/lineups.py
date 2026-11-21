"""Which roles a game gets: 랜덤, 정해진 구성 or 직접, and what the players are told can exist.

The slot table fixes how many of each kind a count gets; roles are drawn inside a kind. 정해진 구성 is one
기본 lineup per player count, written from the classic pool with 복수자 and 사냥꾼; the list is public to the
players and the bench uses it by default. 랜덤 draws again until a balance judge (fitted on recorded games,
`nmb.balance`) puts the mafia side's chance inside 40~60 %, when the judge has enough games to say.
"""
from __future__ import annotations

import random
from collections import Counter
from typing import TYPE_CHECKING, Callable

from .roles import (COMPLEX, COMPLEX_SLOTS, CULT_FROM, ROLES, SIMPLE, SLOT_CITIZEN, SLOT_DOCTOR, SLOT_HELPER, SLOT_MAFIA, SLOT_POLICE,
                    SLOT_SPECIAL, SLOTS, draw_lineup, pool_roles, simple_lineup)
from .text import Msg, T, lines

if TYPE_CHECKING:
    from .setup import GameSetup

RANDOM, NAMED, CUSTOM = "random", "named", "custom"
MODES = (RANDOM, NAMED, CUSTOM)
FAIR = (0.40, 0.60)  # the mafia side's predicted chance a 랜덤 draw must land in
DRAWS = 200  # tries before the draw closest to even is taken

M = "마피아"
# 기본 lineups, one per count: the table filled from the classic pool, 복수자 and 사냥꾼
NAMED_LINEUPS: dict[int, list[str]] = {
    4: [M, "경찰", "의사", "사냥꾼"],
    5: [M, "경찰", "의사", "사냥꾼", "복수자"],
    6: [M, "스파이", "경찰", "의사", "방패병", "사냥꾼"],
    7: [M, "스파이", "경찰", "의사", "방패병", "영매", "복수자"],
    8: [M, M, "야수", "경찰", "의사", "시장", "사냥꾼", "복수자"],
    9: [M, M, "스파이", "경찰", "의사", "방패병", "영매", "사냥꾼", "복수자"],
    10: [M, M, "스파이", "경찰", "의사", "방패병", "시장", "영매", "사냥꾼", "복수자"],
    11: [M, M, M, "유혹자", "경찰", "의사", "방패병", "영매", "연인", "연인", "복수자"],
    12: [M, M, M, "스파이", "경찰", "의사", "방패병", "시장", "영매", "폭로자", "사냥꾼", "시민"],
    13: [M, M, M, "스파이", "야수", "경찰", "의사", "방패병", "영매", "연인", "연인", "사냥꾼", "복수자"],
    14: [M, M, M, "스파이", "유혹자", "경찰", "의사", "방패병", "시장", "영매", "미행꾼", "사냥꾼", "복수자", "시민"],
    15: [M, M, M, M, "스파이", "모방자", "경찰", "의사", "방패병", "시장", "영매", "연인", "연인", "사냥꾼", "복수자"],
    16: [M, M, M, M, "스파이", "야수", "경찰", "의사", "방패병", "영매", "연인", "연인", "폭로자", "부활술사", "사냥꾼", "시민"],
}

Judge = Callable[[int, list[str]], "float | None"]  # (players, roles) → the mafia side's predicted chance, None: too few games


def mode_of(setup: "GameSetup") -> str:
    if setup.kind == SIMPLE:  # 기본 (the table) or 직접
        return CUSTOM if setup.role_mode == CUSTOM else NAMED
    return setup.role_mode if setup.role_mode in MODES else RANDOM


def slots_of(setup: "GameSetup", n: int) -> tuple[int, ...]:
    """Seats per kind: the table, or the 직접 counts when they fit the player count."""
    if mode_of(setup) == CUSTOM and setup.slots and len(setup.slots) == len(SLOTS) and sum(setup.slots) == n:
        return tuple(setup.slots)
    return COMPLEX_SLOTS[n]


def draw_pool(setup: "GameSetup", playable: Callable[[str], bool]) -> list[str]:
    """Roles a slot may draw: the classic pool in 랜덤, the switched-on roles in 직접."""
    if mode_of(setup) == CUSTOM:
        return [r for r in pool_roles("custom", setup.enabled_roles or None) if playable(r)]
    return [r for r in pool_roles(setup.role_pool if setup.role_pool != "custom" else "classic") if playable(r)]


def lineup(setup: "GameSetup", rng: random.Random, playable: Callable[[str], bool], judge: Judge | None = None) -> list[str]:
    """The roles of one game; the seats' own role choices are in it."""
    n = len(setup.seats)
    fixed = [s.role for s in setup.seats if s.role]
    mode = mode_of(setup)
    if by_counts(setup):
        return counted_lineup(setup.counts, n, fixed)
    if setup.kind == SIMPLE:
        return draw_lineup(SIMPLE, n, rng)
    if mode == NAMED:
        return list(NAMED_LINEUPS[n])
    pool, slots = draw_pool(setup, playable), slots_of(setup, n)
    cult = with_cult(setup, n)
    first = draw_lineup(COMPLEX, n, rng, "custom", pool, fixed, cult=cult, slots=slots)
    if mode != RANDOM or judge is None or judge(n, first) is None:
        return first
    best, gap = first, 2.0
    for i in range(DRAWS):
        roles = first if i == 0 else draw_lineup(COMPLEX, n, rng, "custom", pool, fixed, cult=cult, slots=slots)
        p = judge(n, roles)
        if p is None:
            return roles
        if FAIR[0] <= p <= FAIR[1]:
            return roles
        if abs(p - 0.5) < gap:
            best, gap = roles, abs(p - 0.5)
    return best


def with_cult(setup: "GameSetup", n: int) -> bool:
    """The 교주팀 setting applies: 랜덤 of 복잡한 마피아 with enough players."""
    return setup.cult and setup.kind == COMPLEX and mode_of(setup) == RANDOM and n >= CULT_FROM["교주"]


def by_counts(setup: "GameSetup") -> bool:
    """직접 set by a count per role; the older 직접 by kinds and switched-on roles stays for saved setups."""
    return mode_of(setup) == CUSTOM and (bool(setup.counts) or setup.kind == SIMPLE)


def counted_lineup(counts: dict[str, int], n: int, fixed: list[str] | None = None) -> list[str]:
    """Exactly these roles, any number of each; a seat's own role beyond its count takes a 시민 place (연인 by
    pairs); 시민 fill the rest."""
    roles = [r for r, c in counts.items() if r != "시민" for _ in range(max(0, int(c)))]
    for r, c in Counter(fixed or []).items():
        extra = c - roles.count(r)
        if r == "시민" or extra <= 0:
            continue
        roles += [r] * (extra + (extra % 2 if r == "연인" else 0))
    return roles + ["시민"] * max(0, n - len(roles))


COUNT_PROBLEMS = ("unknown", "too_many", "pairs", "no_mafia", "no_town")


def counts_problem(setup: "GameSetup", playable: Callable[[str], bool]) -> str | None:
    """Why a 직접 lineup cannot be played, as one of COUNT_PROBLEMS (the lobby words it), or None."""
    from .roles import GAME_ROLES, MAFIA
    n = len(setup.seats)
    if any(c < 0 or r not in GAME_ROLES[setup.kind] or not playable(r) for r, c in setup.counts.items()):
        return "unknown"
    roles = counted_lineup(setup.counts, n, [s.role for s in setup.seats if s.role])
    if len(roles) > n or roles.count("시민") < sum(1 for s in setup.seats if s.role == "시민"):
        return "too_many"  # a seat set to 시민 needs one of the 시민 that fill the rest
    if roles.count("연인") % 2:
        return "pairs"
    mafia = sum(1 for r in roles if ROLES[r].team == MAFIA)
    if mafia == 0:
        return "no_mafia"
    if mafia == len(roles):
        return "no_town"
    return None


def named_problem(setup: "GameSetup") -> str | None:
    """A seat's role choice that the 정해진 구성 of this count cannot give (the role and how many it has)."""
    if setup.kind != COMPLEX or mode_of(setup) != NAMED or len(setup.seats) not in NAMED_LINEUPS:
        return None
    have = Counter(NAMED_LINEUPS[len(setup.seats)])
    want = Counter(s.role for s in setup.seats if s.role)
    for r, c in want.items():
        if c > have.get(r, 0):
            return r
    return None


def kinds_text(setup: "GameSetup", n: int, playable: Callable[[str], bool]) -> tuple[Msg, list[str]]:
    """What the players are told can exist and the roles whose abilities the rules explain.
    정해진 구성: the exact list. 랜덤 and 직접: how many seats of each kind and the pool each draws from.
    The text is a message, rendered in the game's language."""
    if by_counts(setup):
        counts = Counter(counted_lineup(setup.counts, n, [s.role for s in setup.seats if s.role]))
        listed = [T("{role} {n}명", role=r, n=c) for r, c in counts.items()]
        if any(c > 1 for r, c in counts.items() if r not in (M, "시민")):
            return T("이번 판의 직업(직접 정한 구성, 모두 공개): {listed}. 같은 직업이 여럿이면 각자 자기 능력을 따로 쓴다.",
                     listed=listed), sorted(counts)
        return T("이번 판의 직업(직접 정한 구성, 모두 공개): {listed}.", listed=listed), sorted(counts)
    if mode_of(setup) == NAMED:
        roles = NAMED_LINEUPS[n]
        counts = Counter(roles)
        named = [T("{role} {n}명", role=r, n=c) if c > 1 else r for r, c in counts.items()]
        return T("이번 판의 직업(정해진 구성, 모두 공개): {listed}.", listed=named), sorted(counts)
    slots = dict(zip(SLOTS, slots_of(setup, n)))
    pool = draw_pool(setup, playable)
    fixed = [s.role for s in setup.seats if s.role]
    cultists = [r for r, at in CULT_FROM.items() if with_cult(setup, n) and n >= at and r not in fixed]
    slots[SLOT_SPECIAL] -= len(cultists)  # the 교주팀 setting takes 특수 seats
    parts: list[Msg] = [T("{role} {n}명", role=M, n=slots[SLOT_MAFIA])]
    parts += [T("{role} {n}명", role=r, n=1) for r in cultists]
    told = {M, "시민", *cultists}
    for slot in (SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL):
        if slots[slot] <= 0 and not any(ROLES[r].slot == slot for r in fixed):
            continue
        names = sorted({r for r in pool + fixed if ROLES[r].slot == slot})
        told.update(names)
        if len(names) == 1:
            parts.append(T("{role} {n}명", role=names[0], n=slots[slot]))
        else:
            parts.append(T("{slot} {n}자리({names} 가운데에서)", slot=slot, n=slots[slot], names=names or ["시민"]))
    if slots[SLOT_CITIZEN] > 0:
        parts.append(T("{role} {n}명", role="시민", n=slots[SLOT_CITIZEN]))
    return T("이번 판의 직업은 자리 종류마다 정해진 수만큼 아래 후보 가운데에서 뽑혔다. 어떤 후보가 뽑혔는지는 모른다. "
             "뽑을 후보가 모자란 자리는 시민이 된다. {parts}.", parts=lines(*parts, sep="; ")), sorted(told)


def possible_roles(setup: "GameSetup", n: int, playable: Callable[[str], bool]) -> list[str]:
    return kinds_text(setup, n, playable)[1] if setup.kind == COMPLEX or by_counts(setup) else list(simple_lineup(n))
