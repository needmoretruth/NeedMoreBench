"""A bench run as it plays: progress, the games playing now, the league table or the
tournament bracket, and every finished game, each openable."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import bench  # noqa: E402
from ..bench import Played, Run  # noqa: E402
from ..i18n import _  # noqa: E402
from ..store import load  # noqa: E402
from .bench import GAME_EN, KIND_EN, entry_name  # noqa: E402
from .standings import cell  # noqa: E402
from .widgets import clear, label, vbox  # noqa: E402

STATUS_EN = {"done": "Finished", "stopped": "Stopped", "failed": "Failed", "running": "Playing", "queued": "Waiting"}
TABLE_HEAD = ["Model", "Games", "As mafia", "Wins", "Win rate"]


class RunView(Gtk.ScrolledWindow):
    def __init__(self, app: Any, on_new: Callable[[], None]):
        super().__init__(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.app, self.on_new = app, on_new
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, margin_top=18, margin_bottom=24,
                           margin_start=16, margin_end=16)
        self.set_child(Adw.Clamp(maximum_size=1000, child=self.box))

        self.title = label("", "title-2")
        self.sub = label("", "dim-label")
        self.bar = Gtk.ProgressBar(show_text=False)
        self.count = label("", "numeric")
        self.money = label("", "dim-label")
        self.stop = Gtk.Button(label=_("Stop"))
        self.stop.add_css_class("pill")
        self.stop.connect("clicked", lambda *_a: app.stop_bench())
        self.resume = Gtk.Button(label=_("Continue"))
        self.resume.add_css_class("pill")
        self.resume.add_css_class("suggested-action")
        self.resume.connect("clicked", lambda *_a: self._resume())
        self.new = Gtk.Button(label=_("New run"))
        self.new.add_css_class("pill")
        self.new.connect("clicked", lambda *_a: on_new())
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
        for b in (self.new, self.resume, self.stop):
            buttons.append(b)
        head = Gtk.Box(spacing=12)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        texts.append(self.title)
        texts.append(self.sub)
        head.append(texts)
        head.append(buttons)
        line = Gtk.Box(spacing=12)
        self.count.set_hexpand(True)
        line.append(self.count)
        line.append(self.money)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.add_css_class("bench-card")
        for w in (head, self.bar, line):
            card.append(w)
        self.box.append(card)

        self.now = Adw.PreferencesGroup(title=_("Playing now"))
        self.box.append(self.now)
        self.board_title = label(_("Table"), "heading")
        self.board = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.box.append(self.board_title)
        self.box.append(self.board)
        self.done = Adw.PreferencesGroup(title=_("Games"))
        self.box.append(self.done)
        self._now_rows: list[Gtk.Widget] = []
        self._done_rows: list[Gtk.Widget] = []

    # ---- filling ------------------------------------------------------------------------------------------
    def show(self, run: Run) -> None:
        p = run.plan
        live = self.app.bench is not None and self.app.bench.alive and self.app.bench.run is run
        self.title.set_label(f"{_(KIND_EN[p.kind])}, {_(GAME_EN.get(p.game, 'Mafia'))}")
        # the tables as they are seated: 자동 seats fewer than the plan when fewer models are free (6명 said, 4 played)
        sizes = sorted({len(x.seats) for x in run.played if x.seats}) or [p.players]
        size = str(sizes[0]) if len(sizes) == 1 else f"{sizes[0]}~{sizes[-1]}"
        bits = [_("{n} players").format(n=size), _("{n} at once").format(n=p.at_once)]
        bits.append(_("Blind") if p.blind else _("Named"))
        self.sub.set_label(", ".join(bits))
        done = run.finished()
        failed = [x for x in run.played if x.status == "failed"]
        total = run.total()
        if total:
            self.bar.set_fraction(min(1.0, len(done) / total))
            text = _("{done} of {total} games").format(done=len(done), total=total)
        else:
            text = _("{done} games").format(done=len(done))
        self.bar.set_visible(bool(total))
        if failed:
            text += ", " + _("{n} failed").format(n=len(failed))
        if not live:
            text += ", " + (_("Finished") if total and len(done) >= total else _("Stopped"))
        self.count.set_label(text)
        spent = sum(x.cost for x in run.played)
        if p.kind == "auto":
            limit = _("free models only") if p.daily_limit == 0 else f"${p.daily_limit:.2f}"
            self.money.set_label(_("Today ${today:.2f}, limit {limit}").format(today=run.today(), limit=limit))
        else:
            self.money.set_label(_("Spent ${n:.2f}").format(n=spent))
        finished = bool(total) and len(done) >= total
        self.stop.set_visible(live)
        self.resume.set_visible(not live and not finished)
        self.new.set_visible(not live)
        self._now(run, live)
        self._board(run)
        self._games(run)

    def _resume(self) -> None:
        run = self.app.bench_run()
        if run is not None:
            self.app.start_bench(Run.from_json(run.to_json()))

    def _now(self, run: Run, live: bool) -> None:
        for r in self._now_rows:
            self.now.remove(r)
        self._now_rows = []
        playing = [x for x in run.played if x.status == "running"] if live else []
        where = self.app.bench.where if live else {}
        for x in playing:
            row = Adw.ActionRow(title=self._game_title(x) + ", " + (where.get(x.n) or _("Starting")),
                                subtitle=self._seats(x), activatable=bool(x.file))
            row.set_subtitle_lines(2)
            row.add_prefix(Gtk.Spinner(spinning=True))
            row.connect("activated", lambda *_a, x=x: self._open(x))
            self.now.add(row)
            self._now_rows.append(row)
        self.now.set_visible(bool(playing))

    def _games(self, run: Run) -> None:
        for r in self._done_rows:
            self.done.remove(r)
        self._done_rows = []
        ended = [x for x in run.played if x.status in ("done", "stopped", "failed")][::-1][:60]
        for x in ended:
            won = ", ".join(entry_name(self.app, k) for k in x.winners) if x.winners else ""
            status = _(STATUS_EN[x.status]) + (f", {_('Won')}: {won}" if won else "")
            if x.error:
                status += f", {x.error}"
            row = Adw.ActionRow(title=self._game_title(x), subtitle=status + "\n" + self._seats(x),
                                activatable=bool(x.file))
            row.set_subtitle_lines(3)
            if x.file:
                row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", lambda *_a, x=x: self._open(x))
            self.done.add(row)
            self._done_rows.append(row)
        self.done.set_visible(bool(ended))

    def _game_title(self, x: Played) -> str:
        t = _("Game {n}").format(n=x.n)
        if x.group == "final":
            return _("Final") + ", " + t
        if x.group:
            return _("Group {g}").format(g=x.group) + ", " + t
        return t

    def _seats(self, x: Played) -> str:
        names = []
        for s in x.seats:
            n = entry_name(self.app, s["key"])
            names.append(n + (" (" + _("mafia") + ")" if s.get("role") == "마피아" else ""))
        return ", ".join(names)

    def _open(self, x: Played) -> None:
        if not x.file or not Path(x.file).exists():
            return
        from .replay import Replay
        r = Replay(load(Path(x.file)), on_sound=self.app.play_sound)
        r.page.add_sound_button(self.app.sound.button())
        self.app.window.push(r.page)

    # ---- league table and tournament bracket ---------------------------------------------------------------
    def _board(self, run: Run) -> None:
        clear(self.board)
        p = run.plan
        if p.kind == "tournament":
            self.board_title.set_label(_("Bracket"))
            self.board.append(self._bracket(run))
            return
        self.board_title.set_label(_("Table"))
        keys = [e.key for e in p.entries] or sorted({s["key"] for x in run.played for s in x.seats})
        self.board_title.set_visible(bool(keys))
        if keys:
            self.board.append(self._table(run.played, keys))

    def _table(self, played: list[Played], keys: list[str], top: int = 0) -> Gtk.Widget:
        games, mafia = bench.counts(x for x in played if x.status == "done")
        rows = bench.table(played, keys)
        seats = bench.repeats(played)  # an entry sat twice in a game: every number is per seat, the head says so
        grid = Gtk.Grid()
        grid.add_css_class("standings")
        for col, h in enumerate(TABLE_HEAD):
            words = {1: _("Seats played"), 2: _("Mafia seats")}.get(col, _(h)) if seats else _(h)
            head = cell(words, "table-head", xalign=0.0 if col == 0 else 1.0)
            head.add_css_class("edge-start" if col == 0 else ("edge-end" if col == len(TABLE_HEAD) - 1 else "mid"))
            grid.attach(head, col, 0, 1, 1)
        for y, (k, w, n) in enumerate(rows, start=1):
            name = cell(entry_name(self.app, k), "strong", xalign=0.0, tip=k)
            name.set_hexpand(True)
            name.set_ellipsize(3)
            cells = [name, cell(str(games.get(k, 0))), cell(str(mafia.get(k, 0))), cell(str(w)),
                     cell(f"{w / n:.0%}" if n else "")]
            for col, c in enumerate(cells):
                c.add_css_class("table-cell")
                if col in (0, len(cells) - 1):
                    c.add_css_class("edge-start" if col == 0 else "edge-end")
                if y == 1:
                    c.add_css_class("first")
                if top and y <= top:
                    c.add_css_class("advance")
                grid.attach(c, col, y, 1, 1)
        frame = Gtk.Frame(child=grid)
        frame.add_css_class("standings-frame")
        if not seats:
            return frame
        note = label(_("A model sat in more than one seat of a game, so each seat counts once."), "dim-label", wrap=True,
                     xalign=0.0)
        return vbox(6, frame, note)

    def _bracket(self, run: Run) -> Gtk.Widget:
        p = run.plan
        gs = bench.groups(p)
        per = max(1, p.players // len(gs))
        groups = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, hexpand=True)
        for name, members in gs.items():
            mine = [x for x in run.played if x.group == name]
            played = len([x for x in mine if x.status == "done"])
            col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            col.append(label(_("Group {g}").format(g=name) + f", {played}/{p.games}", "heading"))
            col.append(self._table(mine, [e.key for e in members], top=per))
            groups.append(col)
        final = [x for x in run.played if x.group == "final"]
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        done_final = len([x for x in final if x.status == "done"])
        right.append(label(_("Final") + f", {done_final}/{p.games}", "heading"))
        if final:
            right.append(self._table(final, sorted({s["key"] for x in final for s in x.seats})))
        else:
            right.append(label(_("The best {k} of each group play here").format(k=per), "dim-label", wrap=True))
        champ = bench.champion(run)
        if champ:
            win = Gtk.Box(spacing=8)
            win.add_css_class("card")
            win.add_css_class("bench-champion")
            win.append(Gtk.Image.new_from_icon_name("starred-symbolic"))
            win.append(label(_("Champion") + ", " + entry_name(self.app, champ), "heading"))
            right.append(win)
        arrow = Gtk.Image.new_from_icon_name("go-next-symbolic")
        arrow.set_valign(Gtk.Align.CENTER)
        arrow.add_css_class("dim-label")
        out = Gtk.Box(spacing=16)
        out.append(groups)
        out.append(arrow)
        out.append(right)
        return out
