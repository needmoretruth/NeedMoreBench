"""자리 확인: the check before a game starts. Every model in the lineup answers one tiny request;
each seat shows ready, or its problem in plain words with one-click fixes. When all are ready the game starts by
itself; otherwise the person fixes seats or starts anyway."""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import check  # noqa: E402
from ..engine.names import line_of  # noqa: E402
from ..engine.setup import GameSetup  # noqa: E402
from ..i18n import _  # noqa: E402
from ..providers.merge import route_name  # noqa: E402
from .picker import route_label, seat_price  # noqa: E402
from . import bg  # noqa: E402
from .widgets import avatar, chip, hbox, label, vbox  # noqa: E402


class CheckDialog(Adw.Dialog):
    """on_go(setup) starts the game with the checked (and fixed) lineup; on_fix(index, key) tells the lobby a
    seat changed model or route."""

    def __init__(self, app: Any, setup: GameSetup, on_go: Callable[[GameSetup], None],
                 on_fix: Callable[[int, str], None] | None = None):
        super().__init__(title=_("Seat check"), content_width=620)
        self.app, self.setup, self.on_go, self.on_fix = app, setup, on_go, on_fix
        self.checks = check.seats_to_check(setup, app.routes, app.settings.pools)
        self.fixed = False  # once the person fixed something, the game waits for their click
        self.started = False
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.note = label(_("Each model answers one short request first"), "meta", wrap=True)
        body = vbox(12, self.note, self.list)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(16 if m != "top" else 4)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                max_content_height=640, child=body)
        view.set_content(sc)
        self.anyway = Gtk.Button(label=_("Start anyway"))
        self.anyway.add_css_class("flat")
        self.anyway.connect("clicked", lambda *_a: self._go())
        self.go_btn = Gtk.Button(label=_("Start game"), sensitive=False)
        self.go_btn.add_css_class("pill")
        self.go_btn.add_css_class("suggested-action")
        self.go_btn.connect("clicked", lambda *_a: self._go())
        bar = hbox(12, self.anyway, self.go_btn)
        bar.set_halign(Gtk.Align.END)
        bar.add_css_class("start-bar")
        view.add_bottom_bar(bar)
        self.set_child(view)
        self._fill()
        self._run(self.checks)

    # ---- rows --------------------------------------------------------------------------------------------
    def _fill(self) -> None:
        child = self.list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        for c in self.checks:
            self.list.append(self._row(c))
        ready = all(c.state == "ready" for c in self.checks)
        waiting = any(c.state == "checking" for c in self.checks)
        self.go_btn.set_sensitive(ready)
        self.anyway.set_visible(not ready)
        bad = sum(1 for c in self.checks if c.state == "problem")
        self.note.set_label(_("Each model answers one short request first") if waiting or not bad
                            else _("{n} seats cannot answer now").format(n=bad) if bad > 1 else _("1 seat cannot answer now"))

    def _row(self, c: check.SeatCheck) -> Gtk.Widget:
        row = Adw.ActionRow(title=c.name)
        row.set_title_lines(1)
        row.set_subtitle_lines(2)
        row.add_prefix(avatar(line_of(c.name), 32))
        if c.state == "checking":
            row.set_subtitle(_("Checking"))
            row.add_suffix(Adw.Spinner())
        elif c.state == "ready":
            info = self.app.routes.info(c.key)
            row.set_subtitle(route_label(info) if info else _("Ready"))
            if info is not None:  # 무료, Go 구독 or the price: what the seat costs now
                row.add_suffix(label(seat_price(info), "price"))
            icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
            icon.add_css_class("success")
            icon.set_tooltip_text(_("Ready"))
            row.add_suffix(icon)
        else:
            return self._problem_row(c)
        return row

    def _switch(self, c: check.SeatCheck, key: str) -> Gtk.Button:
        """A route switch that says what it does: the free one or the paid one, the price apart."""
        info = self.app.routes.info(key)
        was = self.app.routes.info(c.key)
        rname = route_label(info) if info else ""
        if info is not None and info.free:
            text, price, tip = _("Use the free one on {route}").format(route=rname), _("Free"), _("The same free model, no cost")
        elif info is not None and (was is None or was.free):
            text, price = _("Use the paid one on {route}").format(route=rname), seat_price(info)  # Go 구독 on Go
            tip = (_("Uses the usage included in your Go subscription; it costs extra only when Extra Usage is on")
                   if route_name(info) == "OpenCode Go" else _("The same model without the free limit. Price per million tokens in and out"))
        else:
            text, price = _("Use {route}").format(route=rname), seat_price(info)
            tip = _("The same model through {route}").format(route=rname)
        b = Gtk.Button(child=hbox(8, label(text), label(price, "price")))
        b.set_tooltip_text(tip)
        b.connect("clicked", lambda *_a: self._use(c, key))
        return b

    def _problem_row(self, c: check.SeatCheck) -> Gtk.Widget:
        """The model and its problem in full, the fixes on a line of their own below, so a long fix label never
        squeezes the name into an ellipsis. 다른 모델 opens the models that answered just now, for the user to pick."""
        title = label(c.name, "heading")
        title.set_ellipsize(3)
        # the title already names the model
        text = label(c.text.split(": ", 1)[1] if c.text.startswith(c.name + ": ") else c.text, "dim-label", wrap=True)
        head = hbox(12, avatar(line_of(c.name), 32), vbox(2, title, text))
        fixes = hbox(8)
        fixes.set_halign(Gtk.Align.END)
        for key in (c.other_route, c.paid):
            if key:
                fixes.append(self._switch(c, key))
        other = Gtk.Button(label=_("Other model"))
        other.set_tooltip_text(_("Models from the same pool that answer now"))
        other.set_sensitive(c.looking != "finding")
        other.connect("clicked", lambda *_a: self._look(c))
        fixes.append(other)
        box = vbox(10, head, fixes)
        if c.looking == "finding":
            spin = hbox(8, Adw.Spinner(), label(_("Asking models from the same pool"), "dim-label"))
            box.append(spin)
        elif c.looking == "shown":
            box.append(self._pick_list(c))
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        row = Gtk.ListBoxRow(child=box, activatable=False)
        row.add_css_class("check-problem")
        return row

    def _pick_list(self, c: check.SeatCheck) -> Gtk.Widget:
        if not c.picks:
            return label(_("No other model in this pool answers now"), "dim-label")
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        for p in c.picks:
            info = self.app.routes.info(p.key)
            row = Adw.ActionRow(title=p.name, subtitle=route_label(info) if info else "", activatable=True)
            row.set_title_lines(1)
            row.add_prefix(avatar(line_of(p.name), 28))
            if p.seated:  # two seats share a model only when the user picks it
                row.add_suffix(chip(_("Already seated"), "plain"))
            row.add_suffix(label(seat_price(info), "price"))
            row.connect("activated", lambda _r, k=p.key: self._use(c, k))
            lb.append(row)
        return lb

    # ---- actions -----------------------------------------------------------------------------------------
    def _run(self, checks: list[check.SeatCheck]) -> None:
        routes = self.app.routes

        def done(_res: Any, err: BaseException | None) -> None:
            if err is not None:
                for c in checks:
                    if c.state == "checking":
                        c.state, c.text = "problem", str(err)[:200]
            self.app.models_changed()
            if self.get_root() is None or self.started:
                return
            self._fill()
            if not self.fixed and all(c.state == "ready" for c in self.checks):
                self._go()
        bg.run(lambda: check.run(routes, checks), done)

    def _use(self, c: check.SeatCheck, key: str | None) -> None:
        if not key:
            return
        self.fixed = True
        check.apply(self.setup, self.app.routes, c, key)
        if self.on_fix is not None:
            self.on_fix(c.index, key)
        same = [x for x in self.checks if x.key == key]
        self._fill()
        self._run(same)

    def _look(self, c: check.SeatCheck) -> None:
        """Ask a few models from the seat's pool and list the ones that answered; nothing changes until the user
        picks one (it once put LongCat on two seats by itself)."""
        c.looking = "finding"
        self._fill()
        routes, setup = self.app.routes, self.setup

        def done(picks: list[check.Candidate] | None, err: BaseException | None) -> None:
            self.app.models_changed()
            if self.get_root() is None or self.started:
                return
            c.picks, c.looking = list(picks or []), "shown"
            self._fill()
        bg.run(lambda: check.candidates(routes, setup, c), done)

    def _go(self) -> None:
        if self.started:
            return
        self.started = True
        self.close()
        self.on_go(self.setup)
