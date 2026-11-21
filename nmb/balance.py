"""The mafia side's expected win chance of a lineup, learned from NMB's own games.

Per game type, a logistic model with Gaussian priors (ridge around a prior mean) over every finished, recorded
game: logit P(mafia team wins) = b0 + b1 (mafia team share minus 1/4) + the sum of b_role times count(role). The prior says what
holds before any game is recorded: a table where a quarter is on the mafia team is even, and the share moves the
chance strongly (b1 ≈ 8: half the table on the mafia team is about 88 %); each role starts at no effect. Recorded
games move all of it. The lobby shows the estimate dimmed while fewer than `ENOUGH` games stand behind it.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable

import numpy as np

from .engine.roles import MAFIA, ROLES

if TYPE_CHECKING:
    from .engine.setup import GameSetup

ENOUGH = 30  # games before the estimate is shown at full strength and the 랜덤 draw trusts it
BASE_SHARE = 0.25
PRIOR = {"b0": (0.0, 1.0), "share": (8.0, 4.0)}  # (mean, sd)
ROLE_SD = 0.5


@dataclass(frozen=True)
class GameLineup:
    kind: str
    roles: tuple[str, ...]  # the roles dealt at the start
    mafia_won: bool


@dataclass(frozen=True)
class Estimate:
    p: float  # the mafia team's chance
    lo: float
    hi: float
    games: int  # recorded games of this type behind it

    @property
    def sure(self) -> bool:
        return self.games >= ENOUGH


def mafia_share(roles: Iterable[str]) -> float:
    roles = list(roles)
    return sum(1 for r in roles if r in ROLES and ROLES[r].team == MAFIA) / max(1, len(roles))


def read_lineups(folder: Path) -> list[GameLineup]:
    """Finished games with a winner: only the header and the result line of each record are parsed."""
    out: list[GameLineup] = []
    for path in sorted(folder.glob("*.nmb.jsonl")):
        try:
            with path.open(encoding="utf-8") as f:
                header = json.loads(f.readline())
                result = None
                gods: list[dict] = []
                for line in f:
                    if line.startswith('{"record": "result"'):
                        result = json.loads(line)
                    elif '"god"' in line:  # only the god's lines are parsed, to see whether it meddled
                        gods.append(json.loads(line))
        except (OSError, ValueError):
            continue
        from .engine.god import intervened
        if not result or result.get("stopped") or not result.get("team") or intervened(gods):
            continue  # a game the god meddled in says nothing about how a lineup plays
        if any(str(s.get("model") or "").startswith("offline:") for s in header.get("seats", [])):
            continue  # scripted offline players say nothing about real play
        from .engine.roles import canon_role
        roles = tuple(canon_role(r) or "시민" for _k, r in sorted((result.get("roles") or {}).items(), key=lambda kv: int(kv[0])))
        if roles:
            out.append(GameLineup(header.get("game") or header.get("settings", {}).get("kind", "simple"), roles,
                                  result["team"] == MAFIA))
    return out


class Model:
    def __init__(self, kind: str, games: list[GameLineup]):
        self.kind = kind
        games = [g for g in games if g.kind == kind]
        self.games = len(games)
        self.names = sorted({r for g in games for r in g.roles if r not in ("시민", "마피아")})
        mean = [PRIOR["b0"][0], PRIOR["share"][0]] + [0.0] * len(self.names)
        sd = [PRIOR["b0"][1], PRIOR["share"][1]] + [ROLE_SD] * len(self.names)
        self.mu, prec = np.array(mean), np.diag(1.0 / np.square(sd))
        X = np.array([self.x(g.roles) for g in games]).reshape(len(games), len(mean))
        y = np.array([1.0 if g.mafia_won else 0.0 for g in games])
        b = self.mu.copy()
        H = prec
        for _ in range(50):  # Newton on the log posterior
            p = 1 / (1 + np.exp(-(X @ b))) if len(games) else np.zeros(0)
            grad = X.T @ (y - p) - prec @ (b - self.mu)
            H = (X.T * (p * (1 - p))) @ X + prec
            step = np.linalg.solve(H, grad)
            b = b + step
            if float(np.max(np.abs(step))) < 1e-8:
                break
        self.b, self.cov = b, np.linalg.inv(H)

    def x(self, roles: Iterable[str]) -> list[float]:
        roles = list(roles)
        return [1.0, mafia_share(roles) - BASE_SHARE] + [float(roles.count(r)) for r in self.names]

    def estimate(self, roles: Iterable[str]) -> Estimate:
        x = np.array(self.x(roles))
        z = float(x @ self.b)
        se = math.sqrt(max(0.0, float(x @ self.cov @ x)))
        f = lambda v: 1 / (1 + math.exp(-v))  # noqa: E731
        return Estimate(f(z), f(z - 1.96 * se), f(z + 1.96 * se), self.games)


_cache: dict[tuple[str, str, int], Model] = {}


def model(kind: str, folder: Path | None = None) -> Model:
    """The fitted model for a game type, refitted when the record folder changes."""
    from .store import games_dir
    folder = folder or games_dir()
    files = list(folder.glob("*.nmb.jsonl")) if folder.exists() else []
    key = (kind, str(folder), len(files) * 1_000_003 + int(sum(p.stat().st_size for p in files)) % 1_000_003)
    if key not in _cache:
        _cache.clear()
        _cache[key] = Model(kind, read_lineups(folder) if folder.exists() else [])
    return _cache[key]


def drawn_estimate(setup: "GameSetup", folder: Path | None = None, draws: int = 40) -> Estimate:
    """What a 랜덤 lineup is expected to give the mafia: the mean over draws made exactly as a game start
    makes them (the judge keeps them inside 40~60 % once enough games stand behind it)."""
    import random

    from .engine.lineups import lineup
    from .engine.setup import playable
    m = model(setup.kind, folder)
    j = judge(setup.kind, folder)
    rng = random.Random(len(setup.seats) * 7919 + (setup.seed or 0))
    ests = [m.estimate(lineup(setup, rng, playable, j)) for _ in range(draws)]
    mean = lambda v: sum(v) / len(v)  # noqa: E731
    return Estimate(mean([e.p for e in ests]), mean([e.lo for e in ests]), mean([e.hi for e in ests]), m.games)


def judge(kind: str, folder: Path | None = None) -> Callable[[int, list[str]], float | None]:
    """For the 랜덤 draw: the predicted chance, or None while too few games stand behind it."""
    m = model(kind, folder)
    return lambda _n, roles: m.estimate(roles).p if m.games >= ENOUGH else None
