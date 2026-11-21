"""The standings table from saved games, without GTK so it is tested headless.

Rows come from rating.board (balanced score, rank range, side scores, Wilson win rates, 예비 below 30 games or
8 per side). Each row also carries what the result lines count per seat: failed calls, cost and time per game.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from . import rating
from .store import Saved


@dataclass
class Usage:
    games: int = 0
    calls: int = 0
    failed: int = 0
    cost: float = 0.0
    ms: int = 0

    @property
    def fail_rate(self) -> float:
        return self.failed / self.calls if self.calls else 0.0

    @property
    def cost_per_game(self) -> float:
        return self.cost / self.games if self.games else 0.0

    @property
    def minutes_per_game(self) -> float:
        return self.ms / self.games / 60000 if self.games else 0.0


@dataclass
class Table:
    rows: list[rating.BoardRow]
    usage: dict[str, Usage] = field(default_factory=dict)
    games: int = 0  # games that count
    skipped: int = 0  # stopped, draws, provider failures
    fit: rating.Fit | None = None
    names: dict[str, str] = field(default_factory=dict)  # entrant key → model name for people

    def name(self, e: rating.Entrant) -> str:
        return self.names.get(e.key) or e.model.rsplit("/", 1)[-1]


def entrant_of(seat: dict) -> rating.Entrant | None:
    if seat.get("kind") == "human":
        return None
    model = (seat.get("model") or "").split("#")[0]
    return rating.Entrant(model, seat.get("variant") or "", bool(seat.get("expert")), seat.get("model_name") or model)


def build(games: Iterable[Saved], intervals: dict[str, tuple[float, float]] | None = None) -> Table:
    rows: list[rating.GameRow] = []
    usage: dict[str, Usage] = {}
    names: dict[str, str] = {}
    skipped = 0
    for g in games:
        row = counted(g)
        if row is None:
            skipped += 1
            continue
        rows.append(row)
        seats = {s["seat"]: s for s in g.header.get("seats", [])}
        for p in (g.result or {}).get("players", []):
            e = entrant_of(seats.get(p.get("seat"), {}))
            if e is None:
                continue
            if not names.get(e.key):
                names[e.key] = seats.get(p.get("seat"), {}).get("model_name") or p.get("model_name") or ""
            u = usage.setdefault(e.key, Usage())
            u.games += 1
            u.calls += int(p.get("calls") or 0)
            u.failed += int(p.get("failed") or 0)
            u.cost += float(p.get("cost") or 0.0)
            u.ms += int(p.get("ms") or 0)
    if not rows:
        return Table([], usage, 0, skipped, names=names)
    f = rating.fit(rows)
    return Table(rating.board(f, intervals, hide=("human",)), usage, len(rows), skipped, f, names)


def counted(g: Saved) -> rating.GameRow | None:
    """The game as a rating row when it counts: finished with a winner, decided by the players and not by a
    provider failure, and played by models (scripted offline players are not entrants)."""
    if any((x.get("model") or "").startswith("offline:") for x in g.header.get("seats", [])):
        return None
    row = rating.row_from_saved(g.header, g.events, g.result)
    return None if row is None or row.failed else row


def rows_for_bootstrap(games: Iterable[Saved]) -> list[rating.GameRow]:
    return [r for r in (counted(g) for g in games) if r is not None]
