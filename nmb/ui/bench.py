"""벤치: set up a run of many games without a person, then follow it (bench_view)."""
from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import bench  # noqa: E402
from ..bench import Entry, Plan, Run  # noqa: E402
from ..engine.roles import COMPLEX, DEFAULT_PLAYERS, PLAYER_RANGE, SIMPLE  # noqa: E402
from ..i18n import _  # noqa: E402
from ..pools import pool_models  # noqa: E402
from ..providers.base import ModelRef  # noqa: E402
from ..view import effort_label  # noqa: E402
from .widgets import label  # noqa: E402

KIND_EN = {"manual": "Manual", "league": "League", "tournament": "Tournament", "auto": "Automatic"}
KIND_SUB = {"manual": "The same models every game, seats and roles drawn",
            "league": "Every model plays as often, on each side about equally",
            "tournament": "Groups first, the best of each play the final",
            "auto": "Keeps playing until you stop it, picking models by need and cost"}
GAMES = [SIMPLE, COMPLEX]
GAME_EN = {SIMPLE: "Simple mafia", COMPLEX: "Complex mafia"}


def entry_name(app: Any, key: str) -> str:
    info = app.routes.info(key)
    ref = ModelRef.parse(key)
    return info.name if info is not None else ref.id


def entry_sub(app: Any, e: Entry) -> str:
    info = app.routes.info(e.key)
    ref = ModelRef.parse(e.key)
    bits = [effort_label(ref.variant)] if ref.variant else []
    if e.expert:
        bits.append(_("Expert"))
    if info is not None:
        bits.append(_("Free") if info.free else f"${bench.entry_cost(info):.3f} " + _("per game"))
    return ", ".join(bits)


def plan_cost(app: Any, plan: Plan, total: int | None) -> tuple[float, float]:
    """(per game, whole run) estimate in dollars; the run is None-safe for 자동 (per game only)."""
    if not plan.entries:
        return 0.0, 0.0
    costs = [bench.entry_cost(app.routes.info(e.key)) for e in plan.entries]
    if plan.kind == "manual":
        per = sum(costs[i % len(costs)] for i in range(plan.players))
    else:
        per = plan.players * sum(costs) / len(costs)
    return per, per * (total or 0)


class BenchPage(Adw.NavigationPage):
    def __init__(self, app: Any):
        super().__init__(title=_("Bench"), tag="bench")
        self.app = app
        last = app.bench_run()
        self.plan = Plan.from_json(last.plan.to_json()) if last is not None else Plan()
        view = Adw.ToolbarView()
        self.header = Adw.HeaderBar()
        view.add_top_bar(self.header)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        self.stack.add_named(self._setup(), "setup")
        from .bench_view import RunView
        self.run_view = RunView(app, self._new)
        self.stack.add_named(self.run_view, "run")
        view.set_content(self.stack)
        view.add_bottom_bar(self.bar)
        self.stack.connect("notify::visible-child-name", lambda *_a: self.bar.set_visible(self.stack.get_visible_child_name() == "setup"))
        self.set_child(view)
        app.on_bench(self._changed)
        self.connect("showing", lambda *_a: self._changed())
        self.stack.set_visible_child_name("run" if last is not None and (last.running or last.played) else "setup")
        self.bar.set_visible(self.stack.get_visible_child_name() == "setup")

    def _changed(self) -> None:
        run = self.app.bench_run()
        if run is not None and self.stack.get_visible_child_name() == "run":
            self.run_view.show(run)

    def _new(self) -> None:
        """새 벤치: back to the form, filled with the last plan."""
        if self.app.bench is not None and self.app.bench.alive:
            return
        self._refresh_form()
        self.stack.set_visible_child_name("setup")

    # ---- the form ----------------------------------------------------------------------------------------
    def _setup(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title=_("Run"))
        self.kind = Adw.ComboRow(title=_("Kind"), model=Gtk.StringList.new([_(KIND_EN[k]) for k in bench.KINDS]))
        self.kind.connect("notify::selected", lambda *_a: self._set("kind", bench.KINDS[self.kind.get_selected()]))
        self.game = Adw.ComboRow(title=_("Game"), model=Gtk.StringList.new([_(GAME_EN[k]) for k in GAMES]))
        self.game.connect("notify::selected", lambda *_a: self._set_game(GAMES[self.game.get_selected()]))
        self.players = Adw.SpinRow.new_with_range(4, 16, 1)
        self.players.set_title(_("Players"))
        self.players.connect("notify::value", lambda *_a: self._set("players", int(self.players.get_value())))
        self.games = Adw.SpinRow.new_with_range(1, 1000, 1)
        self.games.connect("notify::value", lambda *_a: self._set("games", int(self.games.get_value())))
        self.at_once = Adw.SpinRow.new_with_range(1, 3, 1)
        self.at_once.set_title(_("Games at once"))
        self.at_once.connect("notify::value", lambda *_a: self._set("at_once", int(self.at_once.get_value())))
        self.blind = Adw.SwitchRow(title=_("Blind"), subtitle=_("Models do not see who is who"))
        self.blind.connect("notify::active", lambda *_a: self._set("blind", self.blind.get_active()))
        for w in (self.kind, self.game, self.players, self.games, self.at_once, self.blind):
            g.add(w)
        page.add(g)

        self.auto = Adw.PreferencesGroup(title=_("Automatic"))
        self.limit = Adw.SpinRow.new_with_range(0, 100, 0.5)
        self.limit.set_digits(2)
        self.limit.set_title(_("Daily spend limit ($)"))
        self.limit.set_subtitle(_("0 uses free models only"))
        self.limit.connect("notify::value", lambda *_a: self._set("daily_limit", float(self.limit.get_value())))
        self.coin = Adw.SwitchRow(title=_("Expert mode experiment"), subtitle=_("Expert mode on for half the seats, drawn per seat"))
        self.coin.connect("notify::active", lambda *_a: self._set("expert_coin", self.coin.get_active()))
        self.auto.add(self.limit)
        self.auto.add(self.coin)
        page.add(self.auto)

        self.models = Adw.PreferencesGroup(title=_("Models"))
        add = Gtk.Button(child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("Add")), valign=Gtk.Align.CENTER)
        add.connect("clicked", lambda *_a: self._pick())
        free = Gtk.Button(label=_("All free models"), valign=Gtk.Align.CENTER)
        free.connect("clicked", lambda *_a: self._all_free())
        box = Gtk.Box(spacing=8)
        box.append(free)
        box.append(add)
        self.models.set_header_suffix(box)
        self.model_rows: list[Gtk.Widget] = []
        page.add(self.models)

        # the estimate and the start live in a bar under the form, as in the lobby, so they need no scrolling
        self.problem = label("", "error")
        self.estimate = label("", "meta")
        self.start = Gtk.Button(label=_("Start bench"))
        self.start.add_css_class("pill")
        self.start.add_css_class("suggested-action")
        self.start.connect("clicked", lambda *_a: self._start())
        self.bar = Gtk.Box(spacing=16, halign=Gtk.Align.END)
        for w in (self.problem, self.estimate, self.start):
            self.bar.append(w)
        self.bar.add_css_class("start-bar")
        self._refresh_form()
        return page

    def _refresh_form(self) -> None:
        p = self.plan
        self._quiet = True
        self.kind.set_selected(bench.KINDS.index(p.kind))
        self.game.set_selected(GAMES.index(p.game) if p.game in GAMES else 0)
        lo, hi = PLAYER_RANGE[p.game]
        self.players.set_range(lo, hi)
        self.players.set_value(p.players)
        self.games.set_value(p.games)
        self.at_once.set_value(p.at_once)
        self.blind.set_active(p.blind)
        self.limit.set_value(p.daily_limit)
        self.coin.set_active(p.expert_coin)
        self._quiet = False
        self._update()

    def _set(self, name: str, value: Any) -> None:
        if getattr(self, "_quiet", False):
            return
        setattr(self.plan, name, value)
        self._update()

    def _set_game(self, game: str) -> None:
        if getattr(self, "_quiet", False) or game == self.plan.game:
            return
        self.plan.game = game
        self.plan.players = DEFAULT_PLAYERS[game]
        self._refresh_form()

    def _update(self) -> None:
        p = self.plan
        self.kind.set_subtitle(_(KIND_SUB[p.kind]))
        auto = p.kind == "auto"
        self.games.set_visible(not auto)
        self.games.set_title(_("Games per group and final") if p.kind == "tournament" else _("Games"))
        self.auto.set_visible(auto)
        for r in self.model_rows:
            self.models.remove(r)
        self.model_rows = []
        for i, e in enumerate(p.entries):
            row = Adw.ActionRow(title=entry_name(self.app, e.key), subtitle=entry_sub(self.app, e))
            rm = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Remove"))
            rm.add_css_class("flat")
            rm.connect("clicked", lambda *_a, i=i: self._remove(i))
            row.add_suffix(rm)
            self.models.add(row)
            self.model_rows.append(row)
        if not p.entries:
            hint = _("Empty: every free model a route offers now") if auto else _("Add the models to compare")
            row = Adw.ActionRow(title=hint)
            row.add_css_class("dim-label")
            self.models.add(row)
            self.model_rows.append(row)
        self.models.set_description(self._models_note())
        run = Run(p)
        per, whole = plan_cost(self.app, p, run.total())
        if auto:
            self.estimate.set_label(_("Free models only") if p.daily_limit == 0 else
                                    _("Up to ${limit:.2f} a day, about ${per:.3f} a game").format(limit=p.daily_limit, per=per))
        else:
            self.estimate.set_label(_("{n} games, estimate ${cost:.2f}").format(n=run.total(), cost=whole))
        msg = self._problem()
        self.problem.set_label(msg)
        self.problem.set_visible(bool(msg))
        self.start.set_sensitive(not msg)

    def _models_note(self) -> str:
        p = self.plan
        if p.kind == "tournament" and p.entries:
            gs = bench.groups(p)
            return _("{groups} groups of up to {n}; the best {k} of each play the final").format(
                groups=len(gs), n=p.players, k=max(1, p.players // len(gs)))
        if p.kind == "manual" and p.entries:
            return _("Seats go round the list: {n} players").format(n=p.players)
        return ""

    def _problem(self) -> str:
        p = self.plan
        if p.kind == "auto":
            return ""
        if not p.entries:
            return _("Add at least one model")
        if p.kind == "tournament" and len(p.entries) <= p.players:
            return _("A tournament needs more models than seats at one table")
        return ""

    def _remove(self, i: int) -> None:
        del self.plan.entries[i]
        self._update()

    def _pick(self) -> None:
        from .picker import Picker

        def got(_kind: str, key: str) -> None:
            if all(e.key != key for e in self.plan.entries):
                self.plan.entries.append(Entry(key))
            self._update()
        Picker(self.app.routes, self.app.models, got, pools=False, title=_("Add a model")).present(self)

    def _all_free(self) -> None:
        have = {e.key for e in self.plan.entries}
        for m in pool_models(self.app.models, "free", self.app.routes.usable):
            if m.key not in have:
                self.plan.entries.append(Entry(m.key))
        self._update()

    def _start(self) -> None:
        from .. import i18n
        run = Run(Plan.from_json(self.plan.to_json()))
        run.plan.language = i18n.current or "en"  # dialogue in the interface language
        self.app.start_bench(run)
        self.stack.set_visible_child_name("run")
        self.run_view.show(run)
