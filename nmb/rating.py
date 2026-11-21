"""Ratings: refit a team softmax model on the whole history after every game.

Team strength S_k = β[setting, side k] + mean over the team's players of (θ_e + δ[e, side k]),
P(team k wins) = softmax_k(S_k), θ_e = a[model] + b[model, effort] + expert × (γ + γ[model]).
Ridge priors on everything but β and γ let a variant with few games borrow from its model. Fit by Newton
MAP in numpy; Arena's scale: 1000 + 400/ln10 × score. Board score = θ_e + ½(δ[e, 마피아] + δ[e, 시민]).
Instant intervals by the sandwich estimate, a game-level bootstrap for the background. Games a provider
failure decided are left out (counted as failures only); a model's own bad answer counts.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

SCALE = 400 / math.log(10)
CITIZEN, MAFIA, CULT = "시민", "마피아", "교주"
REF_SIDE = CITIZEN  # β of the citizen side is 0 in every setting (softmax is shift-invariant)
PROVIDER_FAIL = {"rate_limit", "overloaded", "network", "provider", "off"}
# prior precisions (logit scale); δ at 16 (sd 0.25, about 43 points) recovered skills best in the simulation
LAM = {"a": 1.0, "b": 4.0, "g": 1e-3, "gm": 4.0, "d": 16.0, "beta": 1e-4}
MIN_GAMES, MIN_SIDE = 30, 8


@dataclass(frozen=True)
class Entrant:
    model: str  # route:provider/id without the effort
    effort: str  # "" when the route has none
    expert: bool
    name: str = field(default="", compare=False)

    @property
    def key(self) -> str:
        return f"{self.model}#{self.effort or '기본'}{'+전문가' if self.expert else ''}"


@dataclass
class GameRow:
    setting: str
    teams: list[tuple[str, list[Entrant]]]  # (side, players)
    winner: int  # index into teams
    failed: bool = False


@dataclass
class Fit:
    entrants: list[Entrant]
    index: dict[str, int]
    w: np.ndarray
    cov: np.ndarray
    games: int
    side_games: dict[str, dict[str, int]]  # entrant key → side → games
    wins: dict[str, dict[str, int]]
    settings: dict[str, float]  # setting → fitted mafia-side base win chance (two-team settings)

    def contrast(self, e: Entrant) -> np.ndarray:
        c = np.zeros(len(self.w))
        for j, v in theta_terms(self.index, e):
            c[j] += v
        for side in (MAFIA, CITIZEN):
            j = self.index.get(f"d|{e.key}|{side}")
            if j is not None:
                c[j] += 0.5
        return c

    def score(self, e: Entrant) -> tuple[float, float]:
        """Balanced score and its sandwich standard error, both on the Arena scale."""
        c = self.contrast(e)
        return 1000 + SCALE * float(c @ self.w), SCALE * math.sqrt(max(0.0, float(c @ self.cov @ c)))

    def side_score(self, e: Entrant, side: str) -> float:
        c = np.zeros(len(self.w))
        for j, v in theta_terms(self.index, e):
            c[j] += v
        j = self.index.get(f"d|{e.key}|{side}")
        if j is not None:
            c[j] += 1
        return 1000 + SCALE * float(c @ self.w)

    def effect(self, name: str) -> tuple[float, float] | None:
        """A coefficient (γ, γ[model], or a contrast built by the caller) with its standard error, Arena scale."""
        j = self.index.get(name)
        if j is None:
            return None
        return SCALE * float(self.w[j]), SCALE * math.sqrt(max(0.0, float(self.cov[j, j])))


def theta_terms(index: dict[str, int], e: Entrant) -> list[tuple[int, float]]:
    out = [(index[f"a|{e.model}"], 1.0), (index[f"b|{e.model}|{e.effort}"], 1.0)]
    if e.expert:
        out += [(index["g"], 1.0), (index[f"gm|{e.model}"], 1.0)]
    return out


def _params(rows: list[GameRow]) -> tuple[dict[str, int], np.ndarray]:
    index: dict[str, int] = {}
    lam: list[float] = []

    def add(name: str, kind: str) -> None:
        if name not in index:
            index[name] = len(lam)
            lam.append(LAM[kind])

    for g in rows:
        for side, players in g.teams:
            if side != REF_SIDE:
                add(f"beta|{g.setting}|{side}", "beta")
            for e in players:
                add(f"a|{e.model}", "a")
                add(f"b|{e.model}|{e.effort}", "b")
                add(f"d|{e.key}|{side}", "d")
                if e.expert:
                    add("g", "g")
                    add(f"gm|{e.model}", "gm")
    return index, np.array(lam)


def _design(rows: list[GameRow], index: dict[str, int]) -> list[np.ndarray]:
    """One (teams × parameters) matrix per game."""
    out = []
    p = len(index)
    for g in rows:
        X = np.zeros((len(g.teams), p))
        for k, (side, players) in enumerate(g.teams):
            j = index.get(f"beta|{g.setting}|{side}")
            if j is not None:
                X[k, j] = 1.0
            n = max(1, len(players))
            for e in players:
                for jj, v in theta_terms(index, e):
                    X[k, jj] += v / n
                X[k, index[f"d|{e.key}|{side}"]] += 1.0 / n
        out.append(X)
    return out


def _newton(Xs: list[np.ndarray], wins: list[int], lam: np.ndarray, iters: int = 60) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Penalised Newton on the stacked team rows; games are contiguous row blocks."""
    p = len(lam)
    X = np.vstack(Xs)
    sizes = np.array([len(x) for x in Xs])
    starts = np.concatenate([[0], np.cumsum(sizes)[:-1]])
    gid = np.repeat(np.arange(len(Xs)), sizes)
    Xwin = X[starts + np.array(wins)]
    R = np.diag(lam)
    w = np.zeros(p)

    def parts(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        s = X @ w
        e = np.exp(s - np.maximum.reduceat(s, starts)[gid])
        pr = e / np.add.reduceat(e, starts)[gid]
        return pr, np.add.reduceat(pr[:, None] * X, starts)

    H = R
    for _ in range(iters):
        pr, m = parts(w)
        g = Xwin.sum(0) - m.sum(0) - R @ w
        H = (X.T * pr) @ X - m.T @ m + R
        step = np.linalg.solve(H, g)
        w = w + step
        if np.abs(step).max() < 1e-9:
            break
    pr, m = parts(w)
    H = (X.T * pr) @ X - m.T @ m + R
    u = Xwin - m  # per-game scores; sandwich H⁻¹ (Σ u uᵀ) H⁻¹
    Hi = np.linalg.inv(H)
    return w, Hi @ (u.T @ u) @ Hi, Hi


def fit(rows: Iterable[GameRow]) -> Fit:
    rows = [g for g in rows if not g.failed and len(g.teams) >= 2]
    index, lam = _params(rows)
    entrants: dict[str, Entrant] = {}
    side_games: dict[str, dict[str, int]] = {}
    wins: dict[str, dict[str, int]] = {}
    for g in rows:
        for k, (side, players) in enumerate(g.teams):
            for e in players:
                entrants.setdefault(e.key, e)
                side_games.setdefault(e.key, {}).setdefault(side, 0)
                side_games[e.key][side] += 1
                wins.setdefault(e.key, {}).setdefault(side, 0)
                wins[e.key][side] += int(k == g.winner)
    if not rows:
        return Fit([], index, np.zeros(0), np.zeros((0, 0)), 0, {}, {}, {})
    w, cov, _ = _newton(_design(rows, index), [g.winner for g in rows], lam)
    settings = {}
    for name, j in index.items():
        if name.startswith("beta|") and name.endswith(f"|{MAFIA}"):
            settings[name[len("beta|"):-len(f"|{MAFIA}")]] = 1 / (1 + math.exp(-w[j]))
    return Fit(list(entrants.values()), index, w, cov, len(rows), side_games, wins, settings)


def bootstrap(rows: list[GameRow], entrants: list[Entrant], n: int = 200, seed: int = 0) -> dict[str, tuple[float, float]]:
    """Game-level bootstrap 95 % interval of each entrant's balanced score (run in the background)."""
    rows = [g for g in rows if not g.failed and len(g.teams) >= 2]
    rng = np.random.default_rng(seed)
    draws: dict[str, list[float]] = {e.key: [] for e in entrants}
    for _ in range(n):
        sample = [rows[i] for i in rng.integers(0, len(rows), len(rows))]
        f = fit(sample)
        for e in entrants:
            if e.key in {x.key for x in f.entrants}:
                draws[e.key].append(f.score(e)[0])
    return {k: (float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))) for k, v in draws.items() if len(v) >= n // 2}


@dataclass
class BoardRow:
    entrant: Entrant
    score: float
    low: float
    high: float
    rank: tuple[int, int]
    mafia: float
    citizen: float
    games: dict[str, int]
    winrate: dict[str, tuple[float, float, float]]  # side → (rate, Wilson low, Wilson high)
    preliminary: bool


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return 0.0, 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - h), min(1.0, c + h)


def board(f: Fit, intervals: dict[str, tuple[float, float]] | None = None, hide: Iterable[str] = ()) -> list[BoardRow]:
    """Rows sorted by score. Interval: bootstrap when given, else ±1.96 sandwich. Rank range as Arena shows it."""
    hidden = set(hide)
    rows = []
    for e in f.entrants:
        if e.model in hidden:
            continue
        s, se = f.score(e)
        lo, hi = (intervals or {}).get(e.key, (s - 1.96 * se, s + 1.96 * se))
        g = f.side_games.get(e.key, {})
        wr = {side: wilson(f.wins.get(e.key, {}).get(side, 0), n) for side, n in g.items()}
        prelim = sum(g.values()) < MIN_GAMES or min(g.get(MAFIA, 0), g.get(CITIZEN, 0)) < MIN_SIDE
        rows.append(BoardRow(e, s, lo, hi, (0, 0), f.side_score(e, MAFIA), f.side_score(e, CITIZEN), g, wr, prelim))
    for r in rows:
        best = 1 + sum(1 for o in rows if o is not r and o.low > r.high)
        worst = len(rows) - sum(1 for o in rows if o is not r and o.high < r.low)
        r.rank = (best, worst)
    return sorted(rows, key=lambda r: -r.score)


def head_to_head(delta: float) -> float:
    """Win chance against the same opponents when one entrant is `delta` points stronger (Arena's reading)."""
    return 1 / (1 + 10 ** (-delta / 400))


# ---- from saved games -------------------------------------------------------------------------------

def team_of_role(role: str) -> str:
    from .engine.roles import ROLES
    r = ROLES.get(role)
    return r.team if r else CITIZEN


def row_from_saved(header: dict[str, Any], events: list[dict[str, Any]], result: dict[str, Any] | None) -> GameRow | None:
    """A finished game as a rating row, or None (stopped, a draw, or a human seat whose side has no entrant)."""
    if not result or result.get("stopped") or not result.get("team"):
        return None
    settings = header.get("settings", {})
    roles = {int(k): v for k, v in (result.get("roles") or {}).items()}
    sides: dict[str, list[Entrant]] = {}
    for s in header.get("seats", []):
        role = roles.get(s["seat"], s.get("role"))
        side = team_of_role(role)
        if s.get("kind") == "human":
            e = Entrant("human", "", False, "사람")
        else:
            model = (s.get("model") or "").split("#")[0]
            e = Entrant(model, s.get("variant") or "", bool(s.get("expert")), s.get("model_name") or model)
        sides.setdefault(side, []).append(e)
    cult = CULT in sides
    setting = f"{settings.get('kind', 'simple')}|{len(header.get('seats', []))}|{settings.get('role_pool', 'classic')}|{'cult' if cult else ''}"
    teams = sorted(sides.items(), key=lambda kv: kv[0])
    winner = next((i for i, (side, _) in enumerate(teams) if side == result["team"]), None)
    if winner is None:
        return None
    return GameRow(setting, teams, winner, provider_decided(events))


def provider_decided(events: list[dict[str, Any]]) -> bool:
    """A call the provider failed for good: retries used up on 429/5xx/network, or a key or credit problem."""
    for ev in events:
        if ev.get("kind") != "error":
            continue
        d = ev.get("details") or {}
        if d.get("reason") in PROVIDER_FAIL and d.get("attempt") == 2 or d.get("reason") in ("auth", "credit", "nokey"):
            return True
    return False
