"""Plays a bench run (nmb.bench) on its own asyncio loop in a worker thread, up to `at_once` games at a time,
at full speed and without sound. GTK-free: the window passes `changed`, called (from the worker) after every
start, end and phase change, and `save`, which keeps the run in the settings so it resumes after a restart."""
from __future__ import annotations

import asyncio
import random
import threading
from pathlib import Path
from typing import Callable

from . import bench
from .bench import Entry, Played, Run
from .engine.game import Game
from .engine.state import Event
from .pools import pool_models
from .providers.registry import Routes
from .runner import build_game, fill_seats, play

IDLE_WAIT = 60.0  # 자동 with nothing it may start now (the day's money is spent): look again after this


class BenchRunner:
    def __init__(self, run: Run, routes: Routes, save: Callable[[Run], None], changed: Callable[[], None],
                 folder: Path | None = None, offline: bool = False):
        self.run, self.routes, self.save, self.changed = run, routes, save, changed
        self.folder, self.offline = folder, offline
        self.games: dict[int, Game] = {}  # Played.n → the game being played
        self.where: dict[int, str] = {}  # Played.n → '2번째 낮, 투표'
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self.thread = threading.Thread(target=lambda: asyncio.run(self._main()), name="nmb-bench", daemon=True)

    def start(self) -> None:
        self.run.running = True
        self.save(self.run)
        self.thread.start()

    def stop(self) -> None:
        """Stops the run: running games end where they stand (중단됨) and the run keeps what it finished."""
        self.run.running = False
        self.save(self.run)
        loop = self.loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._halt)

    def _halt(self) -> None:
        if self._stop is not None:
            self._stop.set()
        for g in list(self.games.values()):
            g.stop()

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    # ---- the loop ------------------------------------------------------------------------------------------
    async def _main(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        rng = random.Random(self.run.seed + len(self.run.played))
        if not self.offline:
            await self.routes.models()
        active: set[asyncio.Task[None]] = set()
        while self.run.running and not self._stop.is_set():
            while len(active) < max(1, min(3, self.run.plan.at_once)):
                played = self._next(rng)
                if played is None:
                    break
                played.status = "running"
                self.run.played.append(played)
                self.save(self.run)
                active.add(asyncio.create_task(self._one(played, rng.randrange(2**31))))
            self.changed()
            if not active:
                if self.run.plan.kind != "auto" or not self._entrants():
                    break
                try:  # 자동 waits for tomorrow's money or a model to come back
                    await asyncio.wait_for(self._stop.wait(), IDLE_WAIT)
                except asyncio.TimeoutError:
                    pass
                continue
            stopper = asyncio.create_task(self._stop.wait())
            done, _ = await asyncio.wait(active | {stopper}, return_when=asyncio.FIRST_COMPLETED)
            stopper.cancel()
            active -= done
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        if self.run.running:  # finished by itself (자동 runs until stopped)
            self.run.running = False
        self.save(self.run)
        self.changed()

    def _entrants(self) -> list[Entry]:
        """자동's field: the chosen entries, or every free model a route offers now (LM Studio never)."""
        if self.run.plan.entries:
            return [e for e in self.run.plan.entries if self._usable(e.key)]
        if self.offline:
            return []
        free = pool_models(self.routes.entries(), "free", self.routes.usable)
        return [Entry(m.key) for m in free]

    def _usable(self, key: str) -> bool:
        if self.offline:
            return True
        e = self.routes.entry(key)
        return e is not None and self.routes.usable(e)

    def _paid(self, e: Entry) -> float:
        return 0.0 if self.offline else bench.entry_cost(self.routes.info(e.key))

    def _next(self, rng: random.Random) -> Played | None:
        fit = None
        if self.run.plan.kind == "auto":
            from .standings import build
            from .store import list_games
            fit = build(list_games(self.folder)).fit
        return bench.next_game(self.run, rng, self._entrants, self._paid, fit)

    async def _one(self, played: Played, seed: int) -> None:
        plan = self.run.plan
        setup = bench.setup_for(plan, played.seats, seed)
        try:
            if not self.offline:
                fill_seats(setup, self.routes, {}, random.Random(seed), allow_repeat=True)
            game, rec, _human = build_game(setup, None if self.offline else self.routes, sink=self._sink(played.n),
                                           offline=self.offline, folder=self.folder,
                                           extra={"bench": {"run": self.run.id, "kind": plan.kind, "game": played.n,
                                                            "group": played.group}})
            self.games[played.n] = game
            played.file = str(rec.path) if rec is not None else ""
            self.save(self.run)
            result = await play(game, rec)
            if result is None or result.get("stopped"):
                played.status = "stopped"
            else:
                played.status = "done"
                won = set(result.get("winners", []))
                played.winners = sorted({s["key"] for i, s in enumerate(played.seats) if i in won})
                played.won_seats = sorted(won)
            played.cost = round(sum(c["cost"] for c in game.calls), 6)
            self.run.spend(played.cost)
        except Exception as e:  # a seat that cannot start, a provider gone: the run goes on with the next game
            played.status = "failed"
            played.error = (str(e) or type(e).__name__)[:300]
        finally:
            self.games.pop(played.n, None)
            self.where.pop(played.n, None)
            self.save(self.run)
            self.changed()

    def _sink(self, n: int) -> Callable[[Event], None]:
        def sink(e: Event) -> None:
            if e.kind in ("phase", "step"):
                g = self.games.get(n)
                if g is not None:
                    self.where[n] = g.phase_label()
                    self.changed()
        return sink


__all__ = ["BenchRunner", "IDLE_WAIT"]
