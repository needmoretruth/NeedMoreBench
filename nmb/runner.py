"""Starting a game from a setup: draw pooled seats, seat players, wire controllers and the recorder.

Shared by the app, the headless runner and the bench, so every game is played and saved the same way.
"""
from __future__ import annotations

import random
import secrets
from pathlib import Path
from typing import Any, Callable

from .engine.expert import EXPERT_VERSION, expert_on
from .engine.game import Game
from .engine.setup import GameSetup, SeatSpec, key_name, seat_players
from .engine.state import Event
from .harness import AIController, HumanController, RandomController
from .providers.base import ModelRef
from .providers.catalog import maker_of
from .providers.registry import Routes
from .stats import player_stats
from .store import Recorder
from .i18n import _


def fill_seats(setup: GameSetup, routes: Routes, pools: dict[str, list[str]], rng: random.Random,
               allow_repeat: bool = False, strict: bool = True) -> None:
    """Give every 랜덤 seat a model from its pool, and names and makers to every model seat. `strict` refuses a
    model that trains on prompts while that is not allowed; the seat check (strict=False) shows it instead."""
    taken = {s.model_key for s in setup.seats if s.model_key}
    for s in setup.seats:
        if s.kind != "ai":
            continue
        if not s.model_key and s.pool:
            keys = [k for k in pools.get(s.pool, []) if allow_repeat or k not in taken] or pools.get(s.pool, [])
            if not keys:
                raise ValueError(_("No usable model in the pool {pool}").format(pool=s.pool))
            s.model_key = rng.choice(keys)
            taken.add(s.model_key)
        if s.model_key:
            if strict:
                routes.check_allowed(s.model_key)
            info = routes.info(s.model_key)
            describe(s, routes)
            ref = ModelRef.parse(s.model_key)
            levels = info.variants if info is not None else []
            if s.variant_random and levels:
                s.variant = rng.choice(levels)  # 랜덤 effort
            s.variant = s.variant or ref.variant
            if s.variant and levels and s.variant not in levels:
                raise ValueError(_("{model} has no {level} level").format(model=s.model_name or s.model_key, level=s.variant))
            s.model_key = ModelRef(ref.route, ref.provider, ref.id, s.variant).key


def describe(s: SeatSpec, routes: Routes | None) -> None:
    """The seat's display name, maker and country: from the route's catalog when it knows the model, else from
    the key itself. A seat never shows a raw key."""
    if s.kind != "ai" or not s.model_key:
        return
    info = routes.info(s.model_key) if routes is not None else None
    ref = ModelRef.parse(s.model_key)
    s.model_name = s.model_name or (info.name if info is not None else key_name(s.model_key))
    if info is not None:
        s.maker, s.country = s.maker or info.maker, s.country or info.country
    if not s.maker:
        maker, country = maker_of(ref.id, s.model_name)
        s.maker, s.country = s.maker or maker, s.country or country


def describe_seats(setup: GameSetup, routes: Routes | None) -> None:
    for s in setup.seats:
        describe(s, routes)


def seat_record(game: Game) -> list[dict[str, Any]]:
    out = []
    for p, spec in zip(game.players, game.setup.seats):
        ref = ModelRef.parse(p.model_key) if p.model_key else None
        out.append({"seat": p.seat, "name": p.name, "kind": p.kind, "role": p.start_role,
                    "model": p.model_key, "model_name": p.model_name, "route": ref.route if ref else None,
                    "provider": ref.provider if ref else None, "variant": ref.variant if ref else None,
                    "maker": spec.maker, "country": spec.country, "shown": p.shown.line(),
                    "disguise": spec.disguise_key, "expert": expert_on(game, p)})
    return out


def draw_judge(setup: GameSetup, folder: Path | None, record: bool) -> Callable[[int, list[str]], float | None] | None:
    """The balance judge for a 랜덤 draw of 복잡한 마피아, fitted on the games in the record folder; none
    for other lineups, or when the game is not recorded and no folder was named."""
    from .engine.lineups import RANDOM, mode_of
    if setup.kind != "complex" or mode_of(setup) != RANDOM or (folder is None and not record):
        return None
    from . import balance
    return balance.judge(setup.kind, folder)


def build_game(setup: GameSetup, routes: Routes | None, sink: Callable[[Event], None] | None = None,
               offline: bool = False, folder: Path | None = None, record: bool = True,
               extra: dict[str, Any] | None = None) -> tuple[Game, Recorder | None, HumanController | None]:
    if setup.seed is None:
        setup.seed = secrets.randbelow(2**31)
    rng = random.Random(setup.seed)
    if offline or routes is None:  # scripted players: a 랜덤 seat still needs a name of its own
        for i, s in enumerate(setup.seats):
            if s.kind == "ai" and not s.model_key:
                s.model_key, s.model_name = f"offline:random/seat{i}", f"Scripted {i + 1}"
        describe_seats(setup, routes)
    problem = setup.problem()
    if problem:
        raise ValueError(problem)
    players = seat_players(setup, rng, draw_judge(setup, folder, record))
    human: HumanController | None = None
    controllers: dict[int, Any] = {}
    for p in players:
        if p.kind == "human":
            human = HumanController()
            controllers[p.seat] = human
        elif offline or routes is None:
            controllers[p.seat] = RandomController(setup.seed * 31 + p.seat)
        else:
            ref = ModelRef.parse(p.model_key or "")
            controllers[p.seat] = AIController(routes.route(ref), ref, routes=routes)
    sinks: list[Callable[[Event], None]] = []
    game = Game(setup, players, controllers, sink=lambda e: [f(e) for f in sinks], rng=rng)
    rec = Recorder(game, seat_record(game), folder, {"expert_version": EXPERT_VERSION, **(extra or {})}) if record else None
    if rec is not None:
        sinks.append(rec.event)
    if sink is not None:
        sinks.append(sink)
    return game, rec, human


async def play(game: Game, rec: Recorder | None) -> dict[str, Any] | None:
    try:
        return await game.run()
    finally:
        if rec is not None:
            rec.close(player_stats(game) if game.result else None)
