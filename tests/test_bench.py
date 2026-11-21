"""벤치: league balance, tournament flow, 자동 money rule and matchmaking, resuming
after a restart, and an offline run that plays and records real games."""
from __future__ import annotations

import json
import random
import time
from collections import Counter

from nmb import bench
from nmb.bench import Entry, Plan, Played, Run
from nmb.bench_run import BenchRunner
from nmb.store import list_games

KEYS = [f"opencode:opencode-go/m{i}#low" for i in range(10)]


def finish(run: Run, p: Played, rng: random.Random) -> None:
    p.status = "done"
    mafia_won = rng.random() < 0.4
    p.winners = [s["key"] for s in p.seats if (s.get("role") == "마피아") == mafia_won]
    run.played.append(p)


def test_league_gives_everyone_the_same_games_and_both_sides():
    run = Run(Plan(kind="league", players=7, games=60, entries=[Entry(k) for k in KEYS[:10]]))
    rng = random.Random(1)
    while (p := bench.next_game(run, rng)) is not None:
        finish(run, p, rng)
    games, mafia = bench.counts(run.played)
    assert len(run.played) == 60
    assert max(games.values()) - min(games.values()) <= 1  # 420 seats over 10 models
    share = 2 / 7
    for k in games:
        assert abs(mafia.get(k, 0) - games[k] * share) <= 2, (k, games[k], mafia.get(k, 0))


def test_manual_repeats_the_same_entrants_with_drawn_roles():
    run = Run(Plan(kind="manual", players=5, games=3, entries=[Entry(k) for k in KEYS[:2]]))
    rng = random.Random(2)
    while (p := bench.next_game(run, rng)) is not None:
        finish(run, p, rng)
    assert len(run.played) == 3
    assert all(Counter(s["key"] for s in p.seats) == Counter({KEYS[0]: 3, KEYS[1]: 2}) for p in run.played)
    assert all(s["role"] is None for p in run.played for s in p.seats)


def test_tournament_groups_then_the_best_play_the_final():
    plan = Plan(kind="tournament", players=5, games=4, entries=[Entry(k) for k in KEYS[:10]])
    run = Run(plan)
    assert list(bench.groups(plan)) == ["A", "B"] and run.total() == 12
    rng = random.Random(3)
    while (p := bench.next_game(run, rng)) is not None:
        if p.group == "final":
            assert all(s["key"] in {e.key for e in bench.advancing(plan, run.played)} for s in p.seats)
        finish(run, p, rng)
    assert [p.group for p in run.played] == ["A"] * 4 + ["B"] * 4 + ["final"] * 4
    finalists = bench.advancing(plan, run.played)
    assert len(finalists) == 4  # two from each group of five for a five-seat final
    for g in ("A", "B"):
        rows = bench.table([p for p in run.played if p.group == g], [e.key for e in bench.groups(plan)[g]])
        assert {e.key for e in finalists} >= {k for k, _w, _n in rows[:2]}
    assert bench.champion(run) in {e.key for e in finalists}


def test_the_final_waits_for_running_group_games():
    plan = Plan(kind="tournament", players=5, games=1, entries=[Entry(k) for k in KEYS[:10]])
    run = Run(plan)
    rng = random.Random(4)
    a = bench.next_game(run, rng)
    a.status = "running"
    run.played.append(a)
    b = bench.next_game(run, rng)
    b.status = "running"
    run.played.append(b)
    assert (a.group, b.group) == ("A", "B")
    assert bench.next_game(run, rng) is None


def test_auto_without_a_limit_draws_free_models_only_and_stays_in_the_money():
    entries = [Entry(k) for k in KEYS[:8]]
    paid = {KEYS[i]: (0.0 if i < 5 else 0.05) for i in range(8)}
    run = Run(Plan(kind="auto", players=5, entries=entries))
    rng = random.Random(5)
    for _ in range(30):
        p = bench.next_game(run, rng, lambda: entries, lambda e: paid[e.key])
        assert all(paid[s["key"]] == 0 for s in p.seats)
        finish(run, p, rng)
    run = Run(Plan(kind="auto", players=5, entries=entries, daily_limit=0.12))
    paid_seen = 0
    for _ in range(30):
        p = bench.next_game(run, rng, lambda: entries, lambda e: paid[e.key])
        cost = sum(paid[s["key"]] for s in p.seats)
        assert run.today() + cost <= 0.12 + 1e-9
        run.spend(cost)
        paid_seen += cost > 0
        finish(run, p, rng)
    assert paid_seen >= 1


def test_matchmaking_favours_need_over_cost_and_keeps_everyone_possible():
    entries = [Entry(KEYS[0]), Entry(KEYS[1])]
    w = bench.weights(entries, None, lambda e: 0.01 if e.key == KEYS[0] else 1.0)
    assert w[0] > w[1] > 0.09  # cheaper wins, the 20 % uniform share keeps the other in
    assert abs(sum(w) - 1) < 1e-9


def test_a_run_resumes_from_the_settings_without_its_cut_games():
    run = Run(Plan(kind="league", games=5, entries=[Entry(k) for k in KEYS[:7]]))
    rng = random.Random(6)
    p = bench.next_game(run, rng)
    finish(run, p, rng)
    q = bench.next_game(run, rng)
    q.status = "running"
    run.played.append(q)
    run.running = True
    back = Run.from_json(json.loads(json.dumps(run.to_json())))
    assert back.running and back.plan.entries[0].key == KEYS[0]
    assert [x.status for x in back.played] == ["done", "stopped"]
    assert bench.next_game(back, rng) is not None and len(back.finished()) == 1


def test_an_offline_run_plays_and_records_every_game(tmp_path):
    run = Run(Plan(kind="league", players=5, games=4, at_once=2, entries=[Entry(k) for k in KEYS[:6]]))
    saved: list[dict] = []
    r = BenchRunner(run, None, lambda x: saved.append(x.to_json()), lambda: None, folder=tmp_path, offline=True)  # type: ignore[arg-type]
    r.start()
    r.thread.join(timeout=60)
    assert not r.alive and not run.running
    assert [p.status for p in run.played] == ["done"] * 4, [p.error for p in run.played]
    games = list_games(tmp_path)
    assert len(games) == 4 and all(g.finished and g.header["bench"]["run"] == run.id for g in games)
    assert all(g.settings["named"] is False for g in games)  # blind by default
    assert all(p.winners for p in run.played)


def test_stopping_a_run_ends_its_games_where_they_stand(tmp_path):
    run = Run(Plan(kind="league", players=6, games=50, entries=[Entry(k) for k in KEYS[:6]]))
    r = BenchRunner(run, None, lambda x: None, lambda: None, folder=tmp_path, offline=True)  # type: ignore[arg-type]
    r.start()
    t0 = time.time()
    while not run.played and time.time() - t0 < 10:
        time.sleep(0.01)
    r.stop()
    r.thread.join(timeout=30)
    assert not r.alive and not run.running
    assert len(run.played) < 50
