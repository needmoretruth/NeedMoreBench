"""Per-player numbers for one finished game, written on the result line and summed for the standings."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .engine.roles import MAFIA, team_of

if TYPE_CHECKING:
    from .engine.game import Game


def player_stats(game: "Game") -> list[dict[str, Any]]:
    result = game.result or {}
    winners = set(result.get("winners", []))
    names = {p.name: p for p in game.players}
    out = []
    for p in game.players:
        team = team_of(p.start_role)
        calls = [c for c in game.calls if c["seat"] == p.seat]
        # votes: how often this player's vote went to the other team (town) or to town (mafia)
        votes = [e.data.get("votes", {}).get(p.seat, e.data.get("votes", {}).get(str(p.seat)))
                 for e in game.events if e.kind == "vote_result"]
        cast = [names[v] for v in votes if isinstance(v, str) and v in names]
        good = [q for q in cast if (team_of(q.start_role) == MAFIA) != (team == MAFIA)]
        # ledger accuracy: final guesses that name a role correctly (모름 excluded)
        guessed = [(names[n], r.guess) for n, r in p.ledger.items() if r.guess != "모름" and n in names]
        right = [1 for q, g in guessed if g == q.start_role]
        # how much the others suspected this player at the end (deception for the mafia)
        held = [q.ledger[p.name].suspicion for q in game.players if q is not p and p.name in q.ledger]
        out.append({
            "seat": p.seat, "name": p.name, "kind": p.kind, "model": p.model_key, "model_name": p.model_name,
            "role": p.start_role, "final_role": p.role, "team": team, "won": p.seat in winners, "alive": p.alive,
            "died_day": p.died_day or None,
            "votes": len(cast), "votes_right": len(good),
            "guesses": len(guessed), "guesses_right": len(right),
            "suspected": round(sum(held) / len(held), 1) if held else None,
            "calls": sum(1 for c in calls if c["kind"] != "error"),
            "failed": sum(1 for c in calls if c["kind"] == "error" or c.get("problem")),
            "tokens_in": sum(c["tokens_in"] for c in calls), "tokens_out": sum(c["tokens_out"] for c in calls),
            "cost": round(sum(c["cost"] for c in calls), 6), "ms": sum(c["ms"] for c in calls),
        })
    return out
