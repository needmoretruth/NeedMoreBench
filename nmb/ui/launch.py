"""Starting a live game from the lobby (or 같은 설정으로 다시) and showing it on the game screen."""
from __future__ import annotations

import os
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib  # noqa: E402

from ..engine.setup import GameSetup  # noqa: E402
from ..engine.state import Event  # noqa: E402
from ..i18n import _  # noqa: E402
from ..live import LiveGame  # noqa: E402
from ..view import ViewState  # noqa: E402
from ..pools import pool_keys  # noqa: E402
from ..stats import player_stats  # noqa: E402
from .game_page import GamePage  # noqa: E402


class Session:
    """One live game on screen. Events arrive from the game thread and are applied on the main loop in order."""

    def __init__(self, app: Any, setup: GameSetup, pools: dict[str, list[str]], allow_repeat: bool):
        self.app = app
        self.page: GamePage | None = None
        self.backlog: list[Event] = []
        self.allow_repeat = allow_repeat
        self.again_setup = setup.again()  # taken before the game draws its 랜덤 seats
        setup.delay = app.settings.delay
        offline = bool(os.environ.get("NMB_OFFLINE"))
        self.live = LiveGame(setup, app.routes, self._deliver, self._done, offline=offline,  # names come from the catalog either way
                             pools=pools, allow_repeat=allow_repeat)

    def start(self) -> None:
        self.live.thread.start()  # the lobby stays responsive while the routes answer
        GLib.timeout_add(100, self._wait_ready)

    def _wait_ready(self) -> bool:
        if self.page is not None:  # already shown
            return False
        if not self.live.ready.is_set():
            return True
        if self.live.error:
            self.app.window.toast(self.live.error)
            return False
        self._show()
        return False

    def _show(self) -> None:
        header = self.live.header or {}
        setup = self.live.setup
        viewer = setup.human_seat if setup.human_seat is not None and not setup.cheats else None
        st = ViewState.from_header(header, viewer=viewer)
        self.page = GamePage(st, _("Complex mafia") if setup.kind == "complex" else _("Simple mafia"), on_sound=self.app.play_sound,
                             controls=self.live)
        self.page.human_seat = setup.human_seat
        self.page.cheat_chip.set_visible(setup.human_seat is not None and setup.cheats)
        if setup.human_seat is not None:  # the person keeps their own ledger and notes
            ins = self.page.inspector
            ins.own_seat, ins.send_edit, ins.guesses = setup.human_seat, self.live.edit, self.live.guesses()
            ins.show_seat(st, setup.human_seat)
        self.page.on_end = self._show_end
        if setup.powers and self.app.god_ready:
            self.page.enable_powers()
        self.app.window.push(self.page)
        self.app.window.nav.connect("popped", self._popped)
        self._flush()

    def _deliver(self, e: Event) -> None:  # game thread
        self.backlog.append(e)
        GLib.idle_add(self._flush)

    def _flush(self) -> bool:
        if self.page is None:
            return False
        events, self.backlog = self.backlog, []
        for e in events:
            self.page.feed(e)
        return False

    def _done(self, result: dict[str, Any] | None, err: str | None) -> None:  # game thread
        if err:
            GLib.idle_add(lambda: (self.app.window.toast(_("The game stopped: {why}").format(why=err)), False)[1])

    def _popped(self, _nav: Adw.NavigationView, page: Adw.NavigationPage) -> None:
        if page is self.page:
            self.live.stop()

    def _show_end(self) -> None:
        page, game = self.page, self.live.game
        if page is None or page.st.result is None or page.get_root() is None:
            return
        from .end import EndDialog
        stats = player_stats(game) if game is not None and game.result else None
        roles = {v.seat: v.role for v in page.st.seats}
        EndDialog(self.live.header or {}, page.st.result, stats, roles, on_again=self._again,
                  on_records=self._records if self.live.rec is not None else None,
                  human_seat=self.live.setup.human_seat).present(page)

    def _again(self) -> None:
        """같은 설정으로 다시: the next game replaces this one on the screen."""
        app = self.app
        app.window.nav.pop_to_tag("home")
        start_game(app, self.again_setup.again(), self.allow_repeat)

    def _records(self) -> None:
        from .records import RecordsPage
        self.app.window.push(RecordsPage(self.app))


def current_pools(app: Any) -> dict[str, list[str]]:
    """The models each 랜덤 pool may draw from, as the app knows them now."""
    return pool_keys(app.models, app.routes.usable, app.settings.pools)


def start_game(app: Any, setup: GameSetup, allow_repeat: bool = False) -> Session:
    s = Session(app, setup, current_pools(app), allow_repeat)
    app.sessions.append(s)
    s.start()
    return s
