"""벤치: many games without a person, GTK-free.

Four kinds of run share one queue:
- 수동: the same entrants N times; seats and roles drawn each game.
- 리그: N games; each game takes the entrants with the fewest games, and the mafia seats go to the entrants
  furthest behind on mafia games, so every model plays as often and on each side about equally.
- 토너먼트: groups of one table each play a small league; the best of each group advance to a final table.
- 자동: keeps going until stopped. Entrants are drawn by the matchmaking (need over cost, 80 % by
  weight and 20 % uniform), sides by deficit, and only free models unless a daily spend limit is set.
The plan and what it has done live in the settings (Settings.bench), so a run resumes after a restart.
"""
from __future__ import annotations

import datetime as dt
import math
import random
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from . import rating
from .engine.roles import COMPLEX, COMPLEX_SLOTS, SIMPLE, simple_lineup
from .engine.setup import GameSetup, SeatSpec
from .providers.base import ModelInfo, ModelRef

KINDS = ("manual", "league", "tournament", "auto")
FREE_TIME_COST = 0.004  # $ a free entrant's game counts as in the weights, so the free pool is not drawn forever


@dataclass
class Entry:
    key: str  # model key with its effort (#variant)
    expert: bool = False

    @property
    def entrant(self) -> str:
        """The board's entrant key (rating.Entrant.key) this entry plays as."""
        ref = ModelRef.parse(self.key)
        model = ModelRef(ref.route, ref.provider, ref.id).key
        return rating.Entrant(model, ref.variant or "", self.expert).key


@dataclass
class Plan:
    kind: str = "league"
    game: str = SIMPLE
    players: int = 7
    entries: list[Entry] = field(default_factory=list)
    games: int = 10  # 수동, 리그: in all; 토너먼트: per group and again for the final
    at_once: int = 1  # 1~3 games at the same time
    blind: bool = True  # bench runs are blind by default
    daily_limit: float = 0.0  # 자동: dollars per day; 0 = free models only
    expert_coin: bool = False  # 자동: each seat's expert flag is a fair coin (experiment)
    language: str = "ko"

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Plan":
        d = dict(d)
        d["entries"] = [Entry(**e) for e in d.get("entries", [])]
        known = Plan.__dataclass_fields__
        return Plan(**{k: v for k, v in d.items() if k in known})


@dataclass
class Played:
    """One game of the run: what was seated, where the record is and how it ended."""
    n: int
    seats: list[dict[str, Any]]  # entry key, expert, role (마피아 or None)
    group: str = ""  # 토너먼트: "A", "B", ... or "final"
    file: str = ""
    status: str = "queued"  # queued | running | done | stopped | failed
    winners: list[str] = field(default_factory=list)  # entrant keys on the winning side
    cost: float = 0.0
    error: str = ""


@dataclass
class Run:
    plan: Plan
    id: str = field(default_factory=lambda: secrets.token_hex(4))
    running: bool = False
    played: list[Played] = field(default_factory=list)
    spent: dict[str, float] = field(default_factory=dict)  # UTC date → dollars spent by this run
    seed: int = field(default_factory=lambda: secrets.randbelow(2**31))

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["plan"] = self.plan.to_json()
        return d

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Run":
        r = Run(Plan.from_json(d.get("plan", {})), d.get("id") or secrets.token_hex(4), bool(d.get("running")),
                [Played(**p) for p in d.get("played", [])], dict(d.get("spent", {})), int(d.get("seed") or 1))
        for p in r.played:  # a game cut off by a restart is not resumed; the run plays another in its place
            if p.status in ("running", "queued"):
                p.status = "stopped"
        return r

    # ---- progress ---------------------------------------------------------------------------------------
    def finished(self) -> list[Played]:
        return [p for p in self.played if p.status == "done"]

    def total(self) -> int | None:
        """Games the run plays in all, None for 자동."""
        if self.plan.kind == "auto":
            return None
        if self.plan.kind == "tournament":
            return self.plan.games * (len(groups(self.plan)) + 1)
        return self.plan.games

    def today(self) -> float:
        return self.spent.get(dt.datetime.now(dt.timezone.utc).date().isoformat(), 0.0)

    def spend(self, dollars: float) -> None:
        day = dt.datetime.now(dt.timezone.utc).date().isoformat()
        self.spent[day] = self.spent.get(day, 0.0) + dollars


# ---- counting what the run has done -----------------------------------------------------------------------
def counts(played: Iterable[Played]) -> tuple[dict[str, int], dict[str, int]]:
    """Games and mafia-side games per entry key over the games that started."""
    games: dict[str, int] = {}
    mafia: dict[str, int] = {}
    for p in played:
        if p.status not in ("done", "running"):
            continue
        for s in p.seats:
            games[s["key"]] = games.get(s["key"], 0) + 1
            if s.get("role") == "마피아":
                mafia[s["key"]] = mafia.get(s["key"], 0) + 1
    return games, mafia


def mafia_seats(game: str, n: int) -> int:
    return simple_lineup(n)["마피아"] if game == SIMPLE else COMPLEX_SLOTS[n][0]


def balanced(entries: list[Entry], n: int, game: str, done: Iterable[Played], rng: random.Random,
             history: dict[str, tuple[int, int]] | None = None) -> list[dict[str, Any]]:
    """n seats: the entries with the fewest games (all of them, repeated, when there are fewer than n), then
    마피아 to those furthest behind on mafia games (step 5). `history` adds games from the board
    (entrant key → (games, mafia games)). Seat order random."""
    games, mafia = counts(done)
    hist = history or {}

    def g(e: Entry) -> int:
        return games.get(e.key, 0) + hist.get(e.entrant, (0, 0))[0]

    def m(e: Entry) -> int:
        return mafia.get(e.key, 0) + hist.get(e.entrant, (0, 0))[1]

    pool = list(entries)
    rng.shuffle(pool)
    if len(pool) >= n:
        chosen = sorted(pool, key=g)[:n]
    else:
        chosen = [pool[i % len(pool)] for i in range(n)]
    k = mafia_seats(game, n)
    share = k / n
    order = sorted(range(n), key=lambda i: (-(g(chosen[i]) * share - m(chosen[i])), rng.random()))
    bad = set(order[:k])
    seats = [{"key": e.key, "expert": e.expert, "role": "마피아" if i in bad else None} for i, e in enumerate(chosen)]
    rng.shuffle(seats)
    return seats


# ---- 토너먼트 --------------------------------------------------------------------------------------------------
def groups(plan: Plan) -> dict[str, list[Entry]]:
    """Entries dealt into tables of `players` (the last table may be short; it repeats its entries)."""
    n = max(1, plan.players)
    k = max(1, math.ceil(len(plan.entries) / n))
    out: dict[str, list[Entry]] = {chr(65 + i): [] for i in range(k)}
    for i, e in enumerate(plan.entries):
        out[chr(65 + i % k)].append(e)
    return out


def table(played: Iterable[Played], keys: Iterable[str]) -> list[tuple[str, int, int]]:
    """(entry key, wins, games) in a group, best first: win rate, then wins."""
    rows = {k: [0, 0] for k in keys}
    for p in played:
        if p.status != "done":
            continue
        for s in p.seats:
            if s["key"] in rows:
                rows[s["key"]][1] += 1
                rows[s["key"]][0] += s["key"] in p.winners
    return sorted(((k, w, n) for k, (w, n) in rows.items()), key=lambda r: (-(r[1] / r[2] if r[2] else 0), -r[1]))


def advancing(plan: Plan, played: list[Played]) -> list[Entry]:
    """The best of each group: as many as fill the final table, shared out evenly."""
    gs = groups(plan)
    per = max(1, plan.players // len(gs))
    by_key = {e.key: e for e in plan.entries}
    out: list[Entry] = []
    for name, members in gs.items():
        rows = table([p for p in played if p.group == name], [e.key for e in members])
        out += [by_key[k] for k, _w, _n in rows[:per]]
    return out


# ---- 자동: matchmaking ----------------------------------------------------------------------------------
def weights(entrants: list[Entry], fit: rating.Fit | None, cost: Callable[[Entry], float]) -> list[float]:
    """π_e ∝ u_e / c_e for 80 %, uniform for 20 %. u_e is how much one more game narrows the entrant's interval."""
    prior_sd = rating.SCALE * 1.0  # the prior on a model's skill (LAM a = 1)
    need = []
    for e in entrants:
        n, se = 0, prior_sd
        if fit is not None:
            for x in fit.entrants:
                if x.key == e.entrant:
                    n = sum(fit.side_games.get(x.key, {}).values())
                    se = fit.score(x)[1] or prior_sd
        per_game = se * se * n if n else (2.0 * prior_sd) ** 2  # the information one game adds
        need.append(se - math.sqrt(1.0 / (1.0 / (se * se) + 1.0 / per_game)))
    ratio = [u / max(cost(e), 1e-4) for u, e in zip(need, entrants)]
    total = sum(ratio) or 1.0
    k = len(entrants)
    return [0.8 * r / total + 0.2 / k for r in ratio]


def draw(entrants: list[Entry], n: int, w: list[float], rng: random.Random) -> list[Entry]:
    """n entrants without replacement by weight (all of them, repeated, when there are fewer)."""
    if len(entrants) <= n:
        return [entrants[i % len(entrants)] for i in range(n)] if entrants else []
    pool, ws, out = list(entrants), list(w), []
    for _ in range(n):
        i = rng.choices(range(len(pool)), weights=ws)[0]
        out.append(pool.pop(i))
        ws.pop(i)
    return out


def auto_lineup(run: Run, entrants: list[Entry], paid: Callable[[Entry], float], fit: rating.Fit | None,
                rng: random.Random, history: dict[str, tuple[int, int]] | None = None) -> list[dict[str, Any]] | None:
    """The next 자동 game's seats, or None when nothing fits the money left today."""
    plan = run.plan
    left = plan.daily_limit - run.today()
    free = [e for e in entrants if paid(e) == 0]
    pool = entrants if plan.daily_limit > 0 else free
    if not pool:
        return None
    n = min(plan.players, max(4, len(pool))) if len(pool) < plan.players else plan.players
    w = weights(pool, fit, lambda e: paid(e) or FREE_TIME_COST)
    chosen: list[Entry] = []
    for _ in range(20):
        chosen = draw(pool, n, w, rng)
        if sum(paid(e) for e in chosen) <= max(left, 0.0):
            break
    else:
        if not free:
            return None
        chosen = draw(free, n, weights(free, fit, lambda e: FREE_TIME_COST), rng)
    if plan.expert_coin:
        chosen = [Entry(e.key, rng.random() < 0.5) for e in chosen]
    return balanced(chosen, len(chosen), plan.game, run.played, rng, history)


# ---- one game from seats ----------------------------------------------------------------------------------------
def setup_for(plan: Plan, seats: list[dict[str, Any]], seed: int) -> GameSetup:
    specs = []
    for s in seats:
        ref = ModelRef.parse(s["key"])
        specs.append(SeatSpec(model_key=s["key"], variant=ref.variant, expert=bool(s.get("expert")), role=s.get("role")))
    return GameSetup(kind=plan.game, seats=specs, named=not plan.blind, blind_scope="ai", language=plan.language,
                     delay=0.0, god_powers=False, seed=seed)


def next_game(run: Run, rng: random.Random, entrants_now: Callable[[], list[Entry]] | None = None,
              paid: Callable[[Entry], float] | None = None, fit: rating.Fit | None = None,
              history: dict[str, tuple[int, int]] | None = None) -> Played | None:
    """The next game to start, or None when the run has nothing more to start now."""
    plan = run.plan
    started = [p for p in run.played if p.status in ("done", "running", "failed")]
    n = len(run.played) + 1
    if plan.kind == "auto":
        entrants = entrants_now() if entrants_now is not None else plan.entries
        seats = auto_lineup(run, entrants, paid or (lambda e: 0.0), fit, rng, history)
        return Played(n, seats) if seats else None
    if not plan.entries:
        return None
    if plan.kind == "tournament":
        gs = groups(plan)
        for name, members in gs.items():
            mine = [p for p in started if p.group == name]
            if len(mine) < plan.games:
                return Played(n, balanced(members, plan.players, plan.game, mine, rng), group=name)
        if any(p.status == "running" for p in run.played):
            return None  # the final waits for every group game
        final = [p for p in started if p.group == "final"]
        if len(final) < plan.games:
            finalists = advancing(plan, run.played)
            return Played(n, balanced(finalists, plan.players, plan.game, final, rng), group="final")
        return None
    if len(started) >= plan.games:
        return None
    if plan.kind == "manual":
        seats = [{"key": plan.entries[i % len(plan.entries)].key, "expert": plan.entries[i % len(plan.entries)].expert,
                  "role": None} for i in range(plan.players)]
        rng.shuffle(seats)
        return Played(n, seats)
    return Played(n, balanced(plan.entries, plan.players, plan.game, started, rng))


def champion(run: Run) -> str | None:
    if run.plan.kind != "tournament":
        return None
    final = [p for p in run.played if p.group == "final" and p.status == "done"]
    if len(final) < run.plan.games:
        return None
    rows = table(final, {s["key"] for p in final for s in p.seats})
    return rows[0][0] if rows else None


def entry_cost(info: ModelInfo | None) -> float:
    """Dollars one seat of this model costs per game (the lobby's estimate)."""
    from .pools import seat_cost
    return seat_cost(info)


__all__ = ["KINDS", "Entry", "Plan", "Played", "Run", "balanced", "groups", "table", "advancing", "weights", "draw",
           "auto_lineup", "setup_for", "next_game", "champion", "entry_cost", "counts", "mafia_seats", "COMPLEX"]
