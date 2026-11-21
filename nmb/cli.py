"""Headless runner: play and save games without the window, list models and saved games, export a record.

    .venv/bin/python -m nmb.cli models --route opencode --free
    .venv/bin/python -m nmb.cli run --game simple --models opencode:opencode-go/deepseek-v4.1-flash#low,... --players 7
    .venv/bin/python -m nmb.cli run --offline --players 7        # random legal answers, no model calls
    .venv/bin/python -m nmb.cli keys | status | list
    .venv/bin/python -m nmb.cli export <file.nmb.jsonl> --out <folder> [--raw] [--md]
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from pathlib import Path
from typing import Callable

from .engine.roles import DEFAULT_PLAYERS, GAME_ROLES
from .engine.setup import GameSetup, SeatSpec
from .engine.state import Event
from .providers.registry import Routes
from .runner import build_game, fill_seats, play
from .store import export_game, list_games, load


def _printer(game_ref: list) -> Callable[[Event], None]:
    def show(e: Event) -> None:
        g = game_ref[0] if game_ref else None
        if g is None:
            return
        if e.kind in ("thinking", "turns", "poll", "ledger", "note", "thought", "call", "human_turn", "would_end"):
            return
        who = g.name_of(e.actor) if e.actor is not None else ""
        scope = "" if e.to is None else (" (신)" if not e.to else f" (→{','.join(g.name_of(s) for s in sorted(e.to))})")
        line = f"[{g.phase_label()}] {e.kind}{scope} {who}: {e.text}" if who else f"[{g.phase_label()}] {e.kind}{scope} {e.text}"
        print(line, flush=True)
    return show


async def cmd_run(a: argparse.Namespace) -> int:
    keys = [k.strip() for k in (a.models or "").split(",") if k.strip()]
    n = a.players or DEFAULT_PLAYERS[a.game]
    if not a.offline and not keys:
        print("--models 또는 --offline 이 필요합니다", file=sys.stderr)
        return 2
    seats = [SeatSpec(model_key=keys[i % len(keys)] if keys else f"offline:random/seat{i}",
                      model_name=None if keys else f"Random {i + 1}") for i in range(n)]
    for s, role in zip(seats, [r.strip() for r in (a.roles or "").split(",") if r.strip()]):
        if role not in GAME_ROLES[a.game]:
            print(f"{role}: 이 게임에 없는 직업입니다", file=sys.stderr)
            return 2
        s.role = role
    setup = GameSetup(kind=a.game, seats=seats, named=not a.blind, seed=a.seed, language=a.lang,
                      turns_per_player=a.turns, vote_public=a.public_votes, role_pool=a.pool, cult=a.cult, expert=a.expert)
    routes = None if a.offline else Routes.standard(allow_training=a.allow_training)
    if routes is not None:
        await routes.models()
        fill_seats(setup, routes, {}, random.Random(a.seed))
    ref: list = []
    game, rec, _ = build_game(setup, routes, sink=None if a.quiet else _printer(ref), offline=a.offline,
                              folder=Path(a.out) if a.out else None)
    ref.append(game)
    print(f"기록: {rec.path if rec else '-'}", flush=True)
    for p in game.players:
        print(f"  {p.seat + 1}. {p.name} = {p.model_key} [{p.role}]", flush=True)
    result = await play(game, rec)
    cost = sum(c["cost"] for c in game.calls)
    calls = sum(1 for c in game.calls if c["kind"] != "error")
    print(f"결과: {result['label'] if result else '중단됨'}, {game.day}번째 밤까지, 호출 {calls}번, 약 ${cost:.4f}")
    return 0


async def cmd_models(a: argparse.Namespace) -> int:
    routes = Routes.standard(allow_training=True)
    models = await routes.models()
    for name, err in routes.errors.items():
        print(f"{name}: {err.reason} {err}", file=sys.stderr)
    for m in sorted(models, key=lambda m: m.key):
        if a.route and m.ref.route != a.route:
            continue
        if a.free and not m.free:
            continue
        price = "무료" if m.free else (m.status if m.status == "가격 모름" else f"${m.price_in:g}/${m.price_out:g}")
        print(f"{m.key}\t{m.name}\t{m.maker or '알 수 없음'}, {m.country or '알 수 없음'}\t{price}{'  학습' if m.trains else ''}{'  ' + m.status if m.status and m.status != '가격 모름' else ''}")
    return 0


async def cmd_keys(a: argparse.Namespace) -> int:
    from .firstrun import import_keys
    for f in await import_keys(replace=a.replace):
        print(f"{f.route}	{f.where}	{f.text}{'  (키링에 저장)' if f.stored else ''}")
    return 0


async def cmd_status(a: argparse.Namespace) -> int:
    for name, (reason, text) in (await Routes.standard().statuses()).items():
        print(f"{name}	{reason}	{text}")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    for s in list_games(Path(a.dir) if a.dir else None):
        r = s.result or {}
        names = ", ".join(x.get("model_name") or x.get("name") for x in s.header.get("seats", []))
        print(f"{s.header.get('created')}\t{s.header.get('title')}\t{s.status}\t{r.get('label', '')}\t{names}\t{s.path.name}")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    saved = load(Path(a.file))
    for path in export_game(saved, Path(a.out or "."), include_raw=a.raw, markdown=a.md):
        print(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nmb.cli", description="NeedMoreBench headless runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="play one game")
    r.add_argument("--game", choices=["simple", "complex"], default="simple")
    r.add_argument("--players", type=int)
    r.add_argument("--models", help="comma separated model keys, cycled over the seats")
    r.add_argument("--blind", action="store_true")
    r.add_argument("--seed", type=int)
    r.add_argument("--lang", default="ko")
    r.add_argument("--turns", type=int, default=2)
    r.add_argument("--pool", choices=["classic", "full"], default="classic")
    r.add_argument("--cult", action="store_true", help="교주팀: 9 players or more, 랜덤 of complex")
    r.add_argument("--roles", help="comma separated roles for the first seats, as the lobby's per-seat choice")
    r.add_argument("--public-votes", action="store_true")
    r.add_argument("--allow-training", action="store_true")
    r.add_argument("--expert", action="store_true", help="전문가 모드 for every seat")
    r.add_argument("--offline", action="store_true")
    r.add_argument("--quiet", action="store_true")
    r.add_argument("--out")
    m = sub.add_parser("models", help="list models")
    m.add_argument("--route")
    m.add_argument("--free", action="store_true")
    k = sub.add_parser("keys", help="take keys found on this machine into the keyring (tested first, never printed)")
    k.add_argument("--replace", action="store_true")
    sub.add_parser("status", help="status line of every route")
    li = sub.add_parser("list", help="list saved games")
    li.add_argument("--dir")
    ex = sub.add_parser("export", help="write the readable .md record")
    ex.add_argument("file")
    ex.add_argument("--out", help="folder to write into (default: here)")
    ex.add_argument("--raw", action="store_true", help="also copy the raw answers and prompts sidecar")
    ex.add_argument("--md", action="store_true", help="also write the readable .md record")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return asyncio.run(cmd_run(a))
    if a.cmd == "models":
        return asyncio.run(cmd_models(a))
    if a.cmd == "keys":
        return asyncio.run(cmd_keys(a))
    if a.cmd == "status":
        return asyncio.run(cmd_status(a))
    if a.cmd == "list":
        return cmd_list(a)
    return cmd_export(a)


if __name__ == "__main__":
    from .config import use_real_folders
    use_real_folders()  # the user's own runs keep their records with the app's
    sys.exit(main())
