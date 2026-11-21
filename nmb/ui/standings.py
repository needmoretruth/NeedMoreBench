"""순위: the board from saved games. The fit takes milliseconds and is shown at once with the
sandwich interval; the bootstrap interval replaces it when the background run finishes."""
from __future__ import annotations

import asyncio
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import rating, standings  # noqa: E402
from ..i18n import _  # noqa: E402
from ..store import list_games  # noqa: E402
from ..view import effort_label  # noqa: E402
from . import bg  # noqa: E402

SIDES = [(rating.MAFIA, "Mafia"), (rating.CITIZEN, "Citizens")]
HEAD = ["Rank", "Model and reasoning", "Score", "Mafia side", "Citizen side", "Games (mafia / citizen)",
        "Win rate (mafia / citizen)", "Failed", "Cost", "Time"]


def cell(text: str, *classes: str, xalign: float = 1.0, tip: str = "") -> Gtk.Label:
    lab = Gtk.Label(label=text, xalign=xalign, valign=Gtk.Align.CENTER)
    for c in classes:
        lab.add_css_class(c)
    if tip:
        lab.set_tooltip_text(tip)
    return lab


def variant_text(e: rating.Entrant) -> str:
    bits = [effort_label(e.effort)] if e.effort else []
    if e.expert:
        bits.append(_("Expert"))
    return ", ".join(bits)


class Standings(Gtk.Stack):
    def __init__(self, app: Any):
        super().__init__()
        self.app = app
        self.intervals: dict[str, tuple[float, float]] | None = None
        self.grid = Gtk.Grid()
        self.grid.add_css_class("standings")
        self.note = Gtk.Label(xalign=0, wrap=True)
        self.note.add_css_class("dim-label")
        self.note.add_css_class("caption")
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=24,
                       margin_start=16, margin_end=16)
        frame = Gtk.Frame(child=self.grid)
        frame.add_css_class("standings-frame")
        body.append(frame)
        body.append(self.note)
        scroll = Gtk.ScrolledWindow(vexpand=True, child=Adw.Clamp(maximum_size=1100, child=body))
        self.add_named(scroll, "table")
        self.add_named(Adw.StatusPage(icon_name="view-sort-descending-symbolic", title=_("No rated games yet"),
                                      description=_("Finished games between models count here.")), "empty")
        self.connect("map", lambda *_a: self.reload())

    def reload(self) -> None:
        games = list_games()
        table = standings.build(games, self.intervals)
        self._fill(table)
        if table.fit is not None and self.intervals is None:
            rows = standings.rows_for_bootstrap(games)
            entrants = table.fit.entrants

            async def boot() -> dict[str, tuple[float, float]]:
                return await asyncio.to_thread(rating.bootstrap, rows, entrants)

            def done(res: dict[str, tuple[float, float]] | None, _err: BaseException | None) -> None:
                if res:
                    self.intervals = res
                    self._fill(standings.build(games, res))
            bg.run(boot, done)

    def _fill(self, table: standings.Table) -> None:
        child = self.grid.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        if not table.rows:
            self.set_visible_child_name("empty")
            return
        self.set_visible_child_name("table")
        for col, h in enumerate(HEAD):
            head = cell(_(h), "table-head", xalign=0.0 if col == 1 else 1.0)
            if col in (0, len(HEAD) - 1):
                head.add_css_class("edge-start" if col == 0 else "edge-end")
            self.grid.attach(head, col, 0, 1, 1)
        for i, r in enumerate(table.rows, start=1):
            self._row(i, r, table.usage.get(r.entrant.key, standings.Usage()), table.name(r.entrant))
        self.note.set_label(_("{n} games count. {skipped} left out: stopped, draws, provider failures or scripted "
                              "players. Dimmed rows are preliminary: fewer than {min} games or {side} on a side.")
                            .format(n=table.games, skipped=table.skipped, min=rating.MIN_GAMES, side=rating.MIN_SIDE))

    def _row(self, y: int, r: rating.BoardRow, u: standings.Usage, shown: str) -> None:
        dim = ("prelim",) if r.preliminary else ()  # a colour, not opacity, so the row lines stay one colour
        lo, hi = r.rank
        rank = str(lo) if lo == hi else f"{lo}~{hi}"
        name = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.FILL, hexpand=True)
        title = cell(shown, "strong", *dim, xalign=0.0, tip=r.entrant.model)
        title.set_ellipsize(3)
        title.set_max_width_chars(28)
        name.append(title)
        sub = variant_text(r.entrant)
        if r.preliminary:
            sub = ", ".join(x for x in (sub, _("Preliminary")) if x)
        if sub:
            name.append(cell(sub, "caption", "dim-label", xalign=0.0))
        games = " / ".join(str(r.games.get(s, 0)) for s, _n in SIDES)
        rates = []
        for s, _n in SIDES:
            if r.games.get(s):
                rates.append(f"{r.winrate[s][0]:.0%}")
            else:
                rates.append("")
        score = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.FILL)
        main = cell(f"{r.score:.0f}", "strong", *dim)
        score.append(main)
        score.set_vexpand(False)  # stops the label's vexpand from stretching the whole grid row
        if r.high - r.low < 1:
            main.set_vexpand(True)
        else:
            score.append(cell(f"{r.low:.0f}~{r.high:.0f}", "caption", "dim-label"))
        wr_tip = "\n".join(_("{side}: {k} of {n}, 95% {lo:.0%}~{hi:.0%}").format(
            side=_(n), k=round(r.winrate[s][0] * r.games[s]), n=r.games[s], lo=r.winrate[s][1], hi=r.winrate[s][2])
            for s, n in SIDES if r.games.get(s))
        cells: list[Gtk.Widget] = [
            cell(rank, *dim), name, score,
            cell(f"{r.mafia:.0f}", *dim), cell(f"{r.citizen:.0f}", *dim),
            cell(games, *dim, tip=_("Mafia side / citizen side")),
            cell(" / ".join(rates), *dim, tip=wr_tip),
            cell(f"{u.fail_rate:.0%}" if u.calls else "", *dim),
            cell(f"${u.cost_per_game:.3f}", *dim, tip=_("Per game")),
            cell(_("{m:.0f} min").format(m=u.minutes_per_game), *dim, tip=_("Per game")),
        ]
        for col, w in enumerate(cells):
            w.add_css_class("table-cell")
            if col in (0, len(cells) - 1):
                w.add_css_class("edge-start" if col == 0 else "edge-end")
            w.set_valign(Gtk.Align.FILL)
            if y == 1:
                w.add_css_class("first")
            self.grid.attach(w, col, y, 1, 1)
