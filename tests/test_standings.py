"""Which saved games count on the board, and the per-entrant usage beside the scores."""
from __future__ import annotations

from pathlib import Path

from nmb import standings
from nmb.store import Saved


def game(models: list[str], mafia: set[int], winner: str, *, stopped: bool = False, names: bool = True,
         errors: list[dict] | None = None) -> Saved:
    seats, players, roles = [], [], {}
    for i, m in enumerate(models):
        role = "마피아" if i in mafia else "시민"
        roles[str(i)] = role
        seat = {"seat": i, "name": f"p{i}", "kind": "ai", "role": role, "model": f"{m}#low", "variant": "low"}
        if names:
            seat["model_name"] = m.rsplit("/", 1)[-1].upper()
        seats.append(seat)
        players.append({"seat": i, "model_name": f"{m.upper()} from result", "calls": 10, "failed": 1, "cost": 0.02,
                        "ms": 120000})
    result = None if stopped else {"team": winner, "roles": roles, "players": players}
    events = [{"kind": "error", "details": e} for e in errors or []]
    return Saved(Path("x"), {"settings": {"kind": "simple"}, "seats": seats}, events, result)


A, B, C, D = "opencode:go/a", "opencode:go/b", "opencode:go/c", "opencode:go/d"


def test_only_finished_model_games_count() -> None:
    games = [
        game([A, B, C, D], {0}, "시민"),
        game([A, B, C, D], {1}, "마피아"),
        game([A, B, C, D], {2}, "시민", stopped=True),
        game(["offline:random/seat0", B, C, D], {0}, "시민"),
        game([A, B, C, D], {3}, "시민", errors=[{"reason": "credit"}]),
    ]
    t = standings.build(games)
    assert t.games == 2 and t.skipped == 3
    assert {r.entrant.model for r in t.rows} == {A, B, C, D}
    assert all(r.preliminary for r in t.rows)


def test_usage_and_names() -> None:
    t = standings.build([game([A, B, C, D], {0}, "시민"), game([A, B, C, D], {1}, "시민", names=False)])
    row = next(r for r in t.rows if r.entrant.model == A)
    u = t.usage[row.entrant.key]
    assert (u.games, u.calls, u.failed) == (2, 20, 2)
    assert abs(u.cost_per_game - 0.02) < 1e-9 and abs(u.minutes_per_game - 2) < 1e-9
    assert abs(u.fail_rate - 0.1) < 1e-9
    assert t.name(row.entrant) == "A"
    # an old record without model_name in the header falls back to the result line
    t2 = standings.build([game([A, B, C, D], {0}, "시민", names=False)])
    assert t2.name(t2.rows[0].entrant).endswith("from result")


def test_empty() -> None:
    t = standings.build([game([A, B], {0}, "시민", stopped=True)])
    assert t.rows == [] and t.games == 0 and t.skipped == 1
