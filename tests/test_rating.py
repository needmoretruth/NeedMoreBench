"""The rating fit recovers known skills from simulated games, built like tools/research-sim."""
from __future__ import annotations

import math

import numpy as np

from nmb.rating import (CITIZEN, CULT, MAFIA, SCALE, Entrant, GameRow, board, bootstrap, fit, head_to_head, row_from_saved,
                        wilson)

K, N, M = 12, 8, 2
EFFORTS = ("low", "high")


def simulate(games: int, seed: int, gamma: float = 0.3, beta: float = -0.3):
    """Each seat: a model (no repeats), a random effort, a fair-coin expert flag; sides filled by side deficit
    as step 5. Truth: θ = a[model] + b[model, effort] + expert·γ, δ = 0."""
    rng = np.random.default_rng(seed)
    a = rng.normal(0, 0.6, K)
    a -= a.mean()
    b = {(m, "low"): 0.0 for m in range(K)}
    b.update({(m, "high"): (0.3 if m < K // 2 else 0.0) for m in range(K)})
    count, maf = np.zeros(K), np.zeros(K)
    rows = []
    for _ in range(games):
        ms = rng.choice(K, N, replace=False)
        eff = rng.choice(EFFORTS, N)
        ex = rng.random(N) < 0.5
        need = count[ms] * M / N - maf[ms] + rng.random(N) * 1e-3
        order = np.argsort(-need)
        th = np.array([a[m] + b[(m, e)] + (gamma if x else 0.0) for m, e, x in zip(ms, eff, ex)])
        s_maf = beta + th[order[:M]].mean()
        s_cit = th[order[M:]].mean()
        p_maf = 1 / (1 + math.exp(-(s_maf - s_cit)))
        win_maf = rng.random() < p_maf
        ent = [Entrant(f"sim:m/{m}", str(e), bool(x)) for m, e, x in zip(ms, eff, ex)]
        teams = sorted([(MAFIA, [ent[i] for i in order[:M]]), (CITIZEN, [ent[i] for i in order[M:]])])
        winner = next(i for i, (side, _) in enumerate(teams) if side == (MAFIA if win_maf else CITIZEN))
        rows.append(GameRow("simple|8|classic|", teams, winner))
        count[ms] += 1
        maf[ms[order[:M]]] += 1
    return rows, a


def test_recovers_known_skills_and_effects() -> None:
    rows, a = simulate(2000, seed=1)
    f = fit(rows)
    ref = [Entrant(f"sim:m/{m}", "low", False) for m in range(K)]
    est = np.array([f.score(e)[0] for e in ref])
    se = np.array([f.score(e)[1] for e in ref])
    truth = 1000 + SCALE * a
    assert np.corrcoef(est, truth)[0, 1] > 0.8  # 5 seeds at 2000 games: mean 0.90, min 0.74 (.scratch curve)
    centred = (est - est.mean()) - (truth - truth.mean())
    assert np.mean(np.abs(centred) <= 1.96 * se + 1e-9) >= 0.7, "sandwich intervals cover the truth"
    g, g_se = f.effect("g")
    assert abs(g - 0.3 * SCALE) < 3 * g_se and g > 0, "expert effect γ recovered"
    assert abs(f.settings["simple|8|classic|"] - 1 / (1 + math.exp(0.3))) < 0.06, "side base rate β recovered"
    # effort: the high step is real for the first half of the models and absent for the rest
    steps = [f.w[f.index[f"b|sim:m/{m}|high"]] - f.w[f.index[f"b|sim:m/{m}|low"]] for m in range(K)]
    assert np.mean(steps[: K // 2]) > np.mean(steps[K // 2:]) + 0.1


def test_three_teams_softmax() -> None:
    rng = np.random.default_rng(3)
    strong, weak = Entrant("sim:m/strong", "", False), Entrant("sim:m/weak", "", False)
    rows = []
    for _ in range(600):
        who = [strong, weak]
        rng.shuffle(who)
        teams = [(CULT, [who[0]]), (MAFIA, [who[1]]), (CITIZEN, [Entrant("sim:m/x", "", False)])]
        s = np.array([1.0 if teams[0][1][0] is strong else 0.0, 1.0 if teams[1][1][0] is strong else 0.0, 0.0])
        p = np.exp(s) / np.exp(s).sum()
        rows.append(GameRow("complex|3|full|cult", teams, int(rng.choice(3, p=p))))
    f = fit(rows)
    assert f.score(strong)[0] > f.score(weak)[0] + 80


def test_board_rules_and_saved_games() -> None:
    rows, _ = simulate(40, seed=2)
    f = fit(rows)
    r = board(f)
    assert all(x.preliminary for x in r), "fewer than 30 games or 8 per side is a dimmed 예비 row"
    iv = bootstrap(rows, f.entrants[:3], n=20)
    assert iv and all(lo < hi for lo, hi in iv.values())
    assert all(1 <= x.rank[0] <= x.rank[1] <= len(r) for x in r)
    assert abs(head_to_head(0) - 0.5) < 1e-12 and wilson(0, 0)[1] == 0.0
    header = {"settings": {"kind": "simple", "role_pool": "classic"}, "seats": [
        {"seat": i, "kind": "ai", "model": f"opencode:go/m{i}#low", "variant": "low", "expert": i == 0, "role": role}
        for i, role in enumerate(["마피아", "시민", "경찰", "의사", "시민"])]}
    result = {"team": MAFIA, "roles": {str(i): s["role"] for i, s in enumerate(header["seats"])}}
    row = row_from_saved(header, [], result)
    assert row is not None and [s for s, _ in row.teams] == [MAFIA, CITIZEN] and row.teams[row.winner][0] == MAFIA
    assert row.teams[0][1][0].expert and not row.failed
    bad = [{"kind": "error", "details": {"reason": "overloaded", "attempt": 2}}]
    assert row_from_saved(header, bad, result).failed, "a game the provider decided is left out"
    assert not row_from_saved(header, [{"kind": "error", "details": {"reason": "timeout", "attempt": 0}}], result).failed
    assert row_from_saved(header, [], {"team": None}) is None
    assert fit([row_from_saved(header, bad, result)]).games == 0
