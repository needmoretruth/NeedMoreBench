"""A game running on its own asyncio loop in a worker thread. No GTK here: the window passes a
`deliver` function that hands each event to the main loop (GLib.idle_add), and posts god powers and the
human's answers back with `call`.
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any, Callable

from .engine.game import Game
from .engine.setup import GameSetup
from .engine.state import Event
from .harness import HumanController
from .providers.registry import Routes
from .runner import build_game, fill_seats, play
from .store import Recorder


class LiveGame:
    def __init__(self, setup: GameSetup, routes: Routes | None, deliver: Callable[[Event], None],
                 done: Callable[[dict[str, Any] | None, str | None], None], offline: bool = False,
                 pools: dict[str, list[str]] | None = None, allow_repeat: bool = False, folder: Path | None = None):
        self.setup, self.routes, self.deliver, self.done = setup, routes, deliver, done
        self.offline, self.pools, self.allow_repeat, self.folder = offline, pools or {}, allow_repeat, folder
        self.game: Game | None = None
        self.rec: Recorder | None = None
        self.human: HumanController | None = None
        self.header: dict[str, Any] | None = None
        self.ready = threading.Event()
        self.error: str | None = None
        self.thread = threading.Thread(target=self._run, name="nmb-game", daemon=True)

    def start(self) -> None:
        self.thread.start()
        self.ready.wait(timeout=60)
        if self.error:
            raise RuntimeError(self.error)

    def _run(self) -> None:
        asyncio.run(self._main())

    async def _main(self) -> None:
        result, err = None, None
        try:
            import random
            if self.routes is not None and not self.offline:
                await self.routes.models()
                fill_seats(self.setup, self.routes, self.pools, random.Random(self.setup.seed), self.allow_repeat)
            self.game, self.rec, self.human = build_game(self.setup, self.routes, sink=self.deliver,
                                                         offline=self.offline, folder=self.folder)
            self.header = self.rec.header if self.rec else None
        except Exception as e:  # shown on the lobby; nothing started
            self.error = str(e) or type(e).__name__
            self.ready.set()
            return
        self.ready.set()
        try:
            result = await play(self.game, self.rec)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
        self.done(result, err)

    # ---- from the window ----------------------------------------------------------------------------
    def call(self, fn: Callable[..., None], *args: Any, **kw: Any) -> None:
        if self.game is not None:
            self.game.post(fn, *args, **kw)

    def god(self, power: str, seat: int | None = None, text: str = "", role: str | None = None, by: str = "신",
            other: int | None = None, n: int = 0) -> None:
        """Runs at the game loop's next step whoever pressed it, so a cheating player's power has no timing tell
       its seat goes only into the god-only record."""
        if self.game is not None:
            self.call(self.game.god, power, seat, text, role, by, other, n, self.setup.human_seat)

    def pause(self, paused: bool) -> None:
        if self.game is not None:
            self.call(self.game.set_paused, paused)

    def answer(self, obj: dict[str, Any]) -> None:
        if self.human is not None:
            self.call(self.human.answer, obj)

    def say(self, text: str) -> None:
        """The person's line during 토론, said at the next turn boundary."""
        if self.game is not None:
            self.call(self.game.queue_line, self.setup.human_seat, text)

    def press_time(self, word: str) -> None:
        """The person's 연장 / 단축 during 토론."""
        if self.game is not None:
            self.call(self.game.press_time, self.setup.human_seat, word)

    def edit(self, obj: dict[str, Any]) -> None:
        """The person's own ledger rows and notes, any time during the game."""
        if self.game is not None:
            self.call(self.game.edit_own, self.setup.human_seat, obj)

    def guesses(self) -> list[str]:
        return self.game.guess_options() if self.game is not None else []

    def end_discussion(self) -> None:
        if self.game is not None:
            self.call(self.game.end_day)

    def stop(self) -> None:
        """Ends the game where it stands; the record keeps everything up to here (중단됨 if no result)."""
        g = self.game
        if g is None:
            return

        def halt() -> None:
            g.stop()
            if self.human is not None:
                self.human.answer({})
        self.call(halt)

    def set_delay(self, seconds: float) -> None:
        self.setup.delay = seconds
