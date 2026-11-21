"""새 게임: the lobby (start page, seats like a Civilization VI lobby).

Seats are 지정 (one model) or 랜덤 (a pool drawn at game start); each seat picks its role, effort and expert
mode. The person watches or takes a seat. The last lobby comes back on the next open. A first open starts from
random free-model seats, which play on whatever the person connects; the Go lineup (pools.READY) needs an
OpenCode Go plan a new user does not have. With nothing connected the lobby says so and Start opens Settings.
"""
from __future__ import annotations

import os
import random
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..engine.roles import COMPLEX, DEFAULT_PLAYERS, GAME_ROLES, PLAYER_RANGE, SIMPLE, simple_lineup  # noqa: E402
from ..engine.names import line_of  # noqa: E402
from ..engine.setup import GameSetup, SeatSpec, playable  # noqa: E402
from ..i18n import _  # noqa: E402
from ..pools import pool_models, seat_cost  # noqa: E402
from ..presets import put_model  # noqa: E402
from ..providers.base import ModelRef  # noqa: E402
from ..view import effort_label, role_label  # noqa: E402
from .picker import POOLS, Picker, place_text, route_menu, seat_price, seat_routes, why_not  # noqa: E402
from .widgets import avatar, chip, hbox, label, vbox  # noqa: E402

LANGS = [("ko", "한국어"), ("en", "English")]


def cheat_words(on: bool) -> str:
    return (_("On: you see every thought, night chat and role, and use god powers") if on
            else _("Off: you see only what your seat sees"))


def _row_list() -> Gtk.ListBox:
    lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
    lb.add_css_class("boxed-list")
    return lb


def _group(title: str, *rows: Gtk.Widget, suffix: Gtk.Widget | None = None) -> tuple[Gtk.Box, Gtk.ListBox]:
    lb = _row_list()
    for r in rows:
        lb.append(r)
    head = hbox(8, label(title, "heading"))
    head.get_first_child().set_hexpand(True)
    if suffix is not None:
        head.append(suffix)
    box = vbox(8, head, lb)
    return box, lb


def _toggles(items: list[tuple[str, str]], active: str, changed) -> Adw.ToggleGroup:
    g = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
    for name, text in items:
        g.add(Adw.Toggle(name=name, label=text))
    g.set_active_name(active)
    g.connect("notify::active-name", lambda w, _p: changed(w.get_active_name()))
    return g


def _dropdown(items: list[str], selected: int, changed) -> Gtk.DropDown:
    d = Gtk.DropDown.new_from_strings(items)
    d.set_selected(max(0, selected))
    d.set_valign(Gtk.Align.CENTER)
    d.connect("notify::selected", lambda w, _p: changed(w.get_selected()))
    return d


class HomePage(Adw.NavigationPage):
    def __init__(self, app: Any):
        super().__init__(title=_("New game"), tag="home")
        self.app = app
        saved = app.settings.lobby or {}
        self.setup = GameSetup.from_json(saved["setup"]) if saved.get("setup") else self._ready_setup()
        self.setup.seed = None
        self.mode = saved.get("mode", "watch")
        self.human = SeatSpec(**saved["human"]) if saved.get("human") else SeatSpec(kind="human")
        self.allow_repeat = bool(saved.get("allow_repeat", False))
        self._look_name = "name" if self.human.human_name.strip() else "human"
        if self.setup.human_seat is not None:  # the human seat lives apart while the lobby is open
            self.human = self.setup.seats.pop(self.setup.human_seat)
            self.mode = "play"
        if not app.complex_ready and self.setup.kind == COMPLEX:
            self.setup = self._ready_setup()
        if not app.play_ready and self.mode == "play":
            self.mode = "watch"
            self.setup.seats.append(SeatSpec(pool="free"))

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        records = Gtk.Button(icon_name="document-open-recent-symbolic", tooltip_text=_("Records"))
        records.connect("clicked", lambda *_a: self._open("records"))
        header.pack_start(records)
        bench = Gtk.Button(label=_("Bench"), tooltip_text=_("Many games without you, for the standings"))
        bench.connect("clicked", lambda *_a: self._open("bench"))
        header.pack_start(bench)
        menu = Gtk.MenuButton(icon_name="open-menu-symbolic", tooltip_text=_("Menu"))
        pop = vbox(2)
        for name, text in self._menu_items():
            b = Gtk.Button(label=text)
            b.add_css_class("flat")
            b.connect("clicked", lambda btn, n=name: (btn.get_ancestor(Gtk.Popover).popdown(), self._open(n)))
            pop.append(b)
        menu.set_popover(Gtk.Popover(child=pop))
        header.pack_end(menu)
        view.add_top_bar(header)

        self.body = vbox(22)
        self.body.set_margin_top(18)
        self.body.set_margin_bottom(24)
        self.body.set_margin_start(16)
        self.body.set_margin_end(16)
        clamp = Adw.Clamp(maximum_size=860, tightening_threshold=700, child=self.body)
        self.scroller = sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=clamp)
        view.set_content(sc)

        self.cost = label("", "meta")
        self.start_btn = Gtk.Button(label=_("Start game"))
        self.start_btn.add_css_class("pill")
        self.start_btn.add_css_class("suggested-action")
        self.start_btn.connect("clicked", lambda *_a: self._start())
        bar = hbox(16, self.cost, self.start_btn)
        bar.set_halign(Gtk.Align.END)
        bar.add_css_class("start-bar")
        view.add_bottom_bar(bar)
        self.set_child(view)
        app.on_models(self.rebuild)
        self.rebuild()

    def _menu_items(self) -> list[tuple[str, str]]:
        items = [("settings", _("Settings"))] if self.app.settings_ready else []
        items += [("standings", _("Standings"))] if self.app.standings_ready else []
        return items + [("about", _("About NeedMoreBench"))]

    # ---- state ------------------------------------------------------------------------------------------
    def _ready_setup(self) -> GameSetup:
        return GameSetup(kind=SIMPLE, seats=[SeatSpec(pool="free") for _i in range(DEFAULT_PLAYERS[SIMPLE])],
                         language=_default_language())

    @property
    def connected(self) -> bool:
        """Some route answers, or the check is still running (then the lobby does not flash the empty state)."""
        st = self.app.statuses
        return bool(self.app.loading or self.app.models or any(r == "ok" for r, _t in st.values()))

    def full_setup(self) -> GameSetup:
        s = GameSetup.from_json(self.setup.to_json())
        if self.mode == "play":
            s.seats.insert(0, SeatSpec(**self.human.__dict__))
        return s

    def save(self) -> None:
        self.app.settings.lobby = {"setup": self.setup.to_json(), "mode": self.mode, "human": self.human.__dict__,
                                   "allow_repeat": self.allow_repeat}
        self.app.settings.save()

    def changed(self) -> None:
        self.save()
        self.rebuild()

    @property
    def count(self) -> int:
        return len(self.setup.seats) + (1 if self.mode == "play" else 0)

    def _set_count(self, n: int) -> None:
        lo, hi = PLAYER_RANGE[self.setup.kind]
        n = max(lo, min(hi, n))
        ai = n - (1 if self.mode == "play" else 0)
        while len(self.setup.seats) < ai:
            self.setup.seats.append(SeatSpec(pool="free"))
        del self.setup.seats[ai:]
        self.changed()

    # ---- building -----------------------------------------------------------------------------------------
    def rebuild(self) -> None:
        child = self.body.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.body.remove(child)
            child = nxt
        if not self.connected:
            self.body.append(self._connect_first())
        self.start_btn.set_label(_("Start game") if self.connected else _("Connect a model"))
        self.body.append(self._numbers())
        self.body.append(self._game_group())
        self.body.append(self._seats_group())
        self.body.append(self._me_group())
        self.body.append(self._names_group())
        self.body.append(self._harness_group())
        self._update_cost()

    def _connect_first(self) -> Gtk.Widget:
        row = Adw.ActionRow(title=_("No model is connected yet"),
                            subtitle=_("Download OpenCode for free models, or paste a key in Settings"))
        row.set_subtitle_lines(2)
        row.add_prefix(Gtk.Image.new_from_icon_name("network-offline-symbolic"))
        go = Gtk.Button(label=_("Open settings"), valign=Gtk.Align.CENTER)
        go.add_css_class("suggested-action")
        go.connect("clicked", lambda *_a: self._open("settings"))
        row.add_suffix(go)
        lb = _row_list()
        lb.append(row)
        return lb

    def _numbers(self) -> Gtk.Widget:
        n = self.count
        if self.setup.kind == SIMPLE:
            lineup = simple_lineup(n)
            items = [(n, _("Players")), (lineup["마피아"], role_label("마피아")), (lineup["경찰"], role_label("경찰")),
                     (lineup["의사"], role_label("의사")), (lineup["시민"], role_label("시민"))]
        else:
            from ..engine.roles import COMPLEX_SLOTS
            sl = COMPLEX_SLOTS[n]
            items = [(n, _("Players")), (sl[0], role_label("마피아")), (sl[1], _("Helpers")), (sl[2] + sl[3], _("Police, doctor")),
                     (sl[4] + sl[5], _("Others"))]
        box = hbox(10)
        box.add_css_class("lobby-numbers")
        box.set_homogeneous(True)
        for value, text in items:
            cell = vbox(0, label(str(value), "value", xalign=0.5), label(text, "label", xalign=0.5))
            cell.add_css_class("lobby-number")
            box.append(cell)
        return box

    def _game_group(self) -> Gtk.Widget:
        kind = Adw.ActionRow(title=_("Game"))
        if self.app.complex_ready:
            kind.add_suffix(_toggles([(SIMPLE, _("Simple mafia")), (COMPLEX, _("Complex mafia"))], self.setup.kind, self._kind))
        else:
            kind.set_subtitle(_("Simple mafia"))
        lo, hi = PLAYER_RANGE[self.setup.kind]
        count = Adw.SpinRow.new_with_range(lo, hi, 1)
        count.set_title(_("Players"))
        count.set_value(self.count)
        count.connect("notify::value", lambda r, _p: self._set_count(int(r.get_value())))
        turns = Adw.SpinRow.new_with_range(1, 5, 1)
        turns.set_title(_("Turns to speak"))
        turns.set_subtitle(_("Per living player each day"))
        turns.set_value(self.setup.turns_per_player)
        turns.connect("notify::value", lambda r, _p: self._set("turns_per_player", int(r.get_value())))
        votes = Adw.SwitchRow(title=_("Open votes"), subtitle=_("Show who voted for whom"), active=self.setup.vote_public)
        votes.connect("notify::active", lambda r, _p: self._set("vote_public", r.get_active()))
        reveal = Adw.SwitchRow(title=_("Reveal the dead's roles"), active=self.setup.reveal)
        reveal.connect("notify::active", lambda r, _p: self._set("reveal_roles", r.get_active()))
        mod = Adw.ActionRow(title=_("Moderator"), subtitle=_("A person decides when the talk ends") if self.setup.moderator == "human" else "")
        mod.add_suffix(_toggles([("auto", _("Auto")), ("human", _("Me"))], self.setup.moderator, lambda v: self._set("moderator", v, True)))
        box, _lb = _group(_("Game"), kind, count, turns, votes, reveal, mod)
        return box

    def _seats_group(self) -> Gtk.Widget:
        fill = Gtk.Button(label=_("Fill with free models"))
        fill.add_css_class("flat")
        fill.connect("clicked", lambda *_a: self._fill_free())
        shuffle = Gtk.Button(icon_name="media-playlist-shuffle-symbolic", tooltip_text=_("Shuffle seats"))
        shuffle.add_css_class("flat")
        shuffle.connect("clicked", lambda *_a: self._shuffle())
        rows: list[Gtk.Widget] = []
        if self.mode == "play":
            rows.append(self._human_row())
        self.seat_rows = [self._seat_row(i, s) for i, s in enumerate(self.setup.seats)]
        rows += self.seat_rows
        repeat = Adw.SwitchRow(title=_("Same model twice"), subtitle=_("Random seats may draw a model already seated"),
                               active=self.allow_repeat)
        repeat.connect("notify::active", lambda r, _p: (setattr(self, "allow_repeat", r.get_active()), self.save()))
        rows.append(repeat)
        from .presets import PresetMenu
        self.preset_btn = PresetMenu(self)
        box, _lb = _group(_("Seats"), *rows, suffix=hbox(4, self.preset_btn, fill, shuffle))
        return box

    def _human_row(self) -> Gtk.Widget:
        row = Adw.ActionRow(title=self._human_title(), subtitle=_("You"))
        row.add_prefix(avatar(self._human_title(), 32))
        row.add_suffix(self._role_dropdown(self.human))
        return row

    def _human_title(self) -> str:
        if not self.setup.named:
            return _("Random name")
        if self.human.disguise_key:
            return _("As {model}").format(model=self.human.disguise_name or self.human.disguise_key)
        return self.human.human_name.strip() or "Human"

    def _seat_row(self, i: int, s: SeatSpec) -> Gtk.Widget:
        info = self.app.routes.info(s.model_key) if s.model_key else None
        if s.model_key:
            title = info.name if info else (s.model_name or ModelRef.parse(s.model_key).id)
            sub = place_text(info) if info else (_("Loading models") if self.app.loading else _("Not available now"))
            why = why_not(self.app.routes, info) if info else ""
            sub = why or sub
            price = seat_price(info)
        else:
            pool = s.pool or "all"
            title = pool[len("user:"):] if pool.startswith("user:") else _(dict(POOLS).get(pool, "All models"))
            sub, price = _("Drawn when the game starts"), ""  # the 랜덤 chip sits before the pool's name
        ways = len(seat_routes(self.app.routes, s.model_key)) if s.model_key and info else 0
        if ways > 1 and not why:
            sub += ", " + _("{n} routes").format(n=ways)
        row = Adw.ActionRow(title=title, subtitle=sub, activatable=ways > 1)
        if ways > 1:  # seat detail: the user may take another route than the order picks
            row.set_tooltip_text(_("Choose the route"))
            row.connect("activated", lambda r, s=s: route_menu(r, self.app.routes, s.model_key or "", lambda k, s=s: self._route(s, k)))
        row.set_title_lines(1)
        row.set_subtitle_lines(1)
        row.add_prefix(avatar(line_of(title) if s.model_key else "?", 32))
        if not s.model_key:
            row.add_prefix(chip(_("Random"), "plain"))
        if price:
            row.add_suffix(label(price, "price"))
        levels = info.variants if info else []
        if s.model_key and levels:
            items = [effort_label(v) for v in levels] + [_("Random effort")]
            cur = len(levels) if s.variant_random else (levels.index(s.variant) if s.variant in levels else 0)
            row.add_suffix(_dropdown(items, cur, lambda k, s=s, lv=levels: self._effort(s, lv, k)))
        row.add_suffix(self._role_dropdown(s))
        expert = Gtk.ToggleButton(label=_("Expert"), valign=Gtk.Align.CENTER,
                                  active=s.expert if s.expert is not None else self.setup.expert)
        expert.add_css_class("flat")
        expert.set_tooltip_text(_("Expert mode: a fixed guide on how strong players reason"))
        expert.connect("toggled", lambda b, s=s: (setattr(s, "expert", b.get_active()), self.save()))
        row.add_suffix(expert)
        change = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=_("Change"), valign=Gtk.Align.CENTER)
        change.add_css_class("flat")
        change.connect("clicked", lambda *_a, s=s: self._pick(s))
        row.add_suffix(change)
        return row

    def _role_dropdown(self, s: SeatSpec) -> Gtk.DropDown:
        roles = [r for r in GAME_ROLES[self.setup.kind] if playable(r)]
        items = [_("Random role")] + [role_label(r) for r in roles]
        cur = roles.index(s.role) + 1 if s.role in roles else 0

        def set_role(k: int) -> None:
            s.role = roles[k - 1] if k > 0 else None
            self.save()
        return _dropdown(items, cur, set_role)

    def _me_group(self) -> Gtk.Widget:
        mode = Adw.ActionRow(title=_("You"))
        if self.app.play_ready:
            mode.add_suffix(_toggles([("watch", _("Watch")), ("play", _("Play"))], self.mode, self._mode))
        else:
            mode.set_subtitle(_("Watching"))
        rows: list[Gtk.Widget] = [mode]
        if self.mode == "watch" and not self.app.god_ready:
            pass
        elif self.mode == "watch":
            sw = Adw.SwitchRow(title=_("God powers"), subtitle=_("Announce, reveal, smite, revive and more"),
                               active=self.setup.god_powers)
            sw.connect("notify::active", lambda r, _p: self._set("god_powers", r.get_active()))
            rows.append(sw)
        else:
            sw = Adw.SwitchRow(title=_("Cheats"), subtitle=cheat_words(self.setup.cheats), active=self.setup.cheats)

            def cheat(r: Adw.SwitchRow, _p: Any) -> None:  # the subtitle says what the switch does now
                r.set_subtitle(cheat_words(r.get_active()))
                self._set("cheats", r.get_active())
            sw.connect("notify::active", cheat)
            rows.append(sw)
            if self.setup.named:  # J10: Human, a typed name, or pretending to be a model
                look = Adw.ActionRow(title=_("Shown as"))
                look.add_suffix(_toggles([("human", "Human"), ("name", _("My name")), ("ai", _("An AI"))], self.look, self._look))
                rows.append(look)
                if self.look == "name":
                    entry = Adw.EntryRow(title=_("Name"), text=self.human.human_name)
                    entry.connect("changed", lambda e: (setattr(self.human, "human_name", e.get_text()), self.save()))
                    rows.append(entry)
                elif self.look == "ai":
                    pick = Adw.ActionRow(title=_("Pretend to be"), subtitle=self.human.disguise_name or "", activatable=True)
                    pick.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
                    pick.connect("activated", lambda *_a: self._pick_disguise())
                    rows.append(pick)
        box, _lb = _group(_("You"), *rows)
        return box

    def _names_group(self) -> Gtk.Widget:
        named = Adw.ActionRow(title=_("Names"), subtitle=_("Models see each other's model, maker and country")
                              if self.setup.named else _("Everyone gets a random name"))
        named.add_suffix(_toggles([("named", _("Real")), ("blind", _("Blind"))], "named" if self.setup.named else "blind",
                                  lambda v: self._set("named", v == "named", True)))
        rows: list[Gtk.Widget] = [named]
        if not self.setup.named:
            scope = Adw.ActionRow(title=_("Blind for"))
            scope.add_suffix(_toggles([("ai", _("AIs only")), ("me", _("Me too"))], self.setup.blind_scope,
                                      lambda v: self._set("blind_scope", v, True)))
            rows.append(scope)
        lang = Adw.ActionRow(title=_("Dialogue language"), subtitle=_("What the models write"))
        lang.add_suffix(_toggles(LANGS, self.setup.language, lambda v: self._set("language", v, True)))
        rows.append(lang)
        box, _lb = _group(_("Names and language"), *rows)
        return box

    def _harness_group(self) -> Gtk.Widget:
        expert = Adw.SwitchRow(title=_("Expert mode for every seat"), subtitle=_("A seat's own switch can differ"),
                               active=self.setup.expert)
        expert.connect("notify::active", lambda r, _p: self._expert_all(r.get_active()))
        compact = Adw.SpinRow.new_with_range(8, 1000, 8)
        compact.set_title(_("Compaction point"))
        compact.set_subtitle(_("Thousand tokens of history before a player sums it up"))
        compact.set_value(self.setup.compact_at // 1000)
        compact.connect("notify::value", lambda r, _p: self._set("compact_at", int(r.get_value()) * 1000))
        timeout = Adw.SpinRow.new_with_range(15, 600, 15)
        timeout.set_title(_("Time per call"))
        timeout.set_subtitle(_("Seconds; after that the safe default is used"))
        timeout.set_value(self.setup.call_timeout)
        timeout.connect("notify::value", lambda r, _p: self._set("call_timeout", float(r.get_value())))
        exp = Adw.ExpanderRow(title=_("Advanced"))
        for r in (expert, compact, timeout):
            exp.add_row(r)
        box, _lb = _group(_("Harness"), exp)
        return box

    # ---- actions -------------------------------------------------------------------------------------------
    def _set(self, name: str, value: Any, rebuild: bool = False) -> None:
        setattr(self.setup, name, value)
        self.changed() if rebuild else (self.save(), self._update_cost())

    def _kind(self, kind: str | None) -> None:
        if not kind or kind == self.setup.kind:
            return
        self.setup.kind = kind
        self.setup.reveal_roles = None  # each game's own default: shown in 단순, hidden in 복잡
        for s in self.setup.seats:
            if s.role and s.role not in GAME_ROLES[kind]:
                s.role = None
        self._set_count(max(self.count, DEFAULT_PLAYERS[kind]) if kind == COMPLEX else self.count)

    def _mode(self, mode: str | None) -> None:
        if not mode or mode == self.mode:
            return
        n = self.count
        self.mode = mode
        self._set_count(n)

    @property
    def look(self) -> str:
        return "ai" if self.human.disguise_key else self._look_name

    def _look(self, how: str | None) -> None:
        if how == "ai":
            self._pick_disguise()
            return
        self.human.disguise_key = self.human.disguise_name = self.human.disguise_maker = self.human.disguise_country = None
        self._look_name = how or "human"
        if how == "human":
            self.human.human_name = ""
        self.changed()

    def _pick_disguise(self) -> None:
        def got(kind: str, key: str) -> None:
            info = self.app.routes.info(key)
            self.human.disguise_key = key
            self.human.disguise_name = info.name if info else key
            self.human.disguise_maker = info.maker if info else None
            self.human.disguise_country = info.country if info else None
            self.changed()
        Picker(self.app.routes, self.app.models, got, pools=False, title=_("Pretend to be")).present(self)

    def _expert_all(self, on: bool) -> None:
        self.setup.expert = on
        for s in self.setup.seats:
            s.expert = None
        self.changed()

    def _effort(self, s: SeatSpec, levels: list[str], k: int) -> None:
        s.variant_random = k >= len(levels)
        s.variant = None if s.variant_random else levels[k]
        if s.model_key:
            ref = ModelRef.parse(s.model_key)
            s.model_key = ModelRef(ref.route, ref.provider, ref.id, s.variant).key
        self.save()
        self._update_cost()

    def _pick(self, s: SeatSpec) -> None:
        def got(kind: str, value: str) -> None:
            if kind == "pool":
                s.model_key, s.pool, s.model_name, s.maker, s.country = None, value, None, None, None
            else:
                put_model(s, self.app.routes, value)
            self.changed()
        Picker(self.app.routes, self.app.models, got, user_pools=self.app.settings.pools,
               on_pools=self._pools_changed).present(self)

    def _pools_changed(self, old: str | None, new: str | None) -> None:
        """A saved pool made, renamed or deleted: kept in the settings, and seats on it follow (deleted: 전체)."""
        from ..pools import USER
        if old is not None and old != new:
            for s in self.setup.seats:
                if s.pool == USER + old:
                    s.pool = USER + new if new is not None else "all"
        self.app.settings.save()
        self.changed()

    def _route(self, s: SeatSpec, key: str) -> None:
        put_model(s, self.app.routes, self.app.routes.with_effort(key, s.variant))
        self.changed()

    def _fill_free(self) -> None:
        free = [m for m in pool_models(self.app.models, "free", self.app.routes.usable)]
        if not free:
            self.app.window.toast(_("No free model answers right now"))
            return
        rng = random.Random()
        rng.shuffle(free)
        for i, s in enumerate(self.setup.seats):
            put_model(s, self.app.routes, free[i % len(free)].key)
        self.changed()

    def _shuffle(self) -> None:
        random.shuffle(self.setup.seats)
        self.changed()

    def _update_cost(self) -> None:
        total = sum(seat_cost(self.app.routes.info(s.model_key)) for s in self.setup.seats if s.model_key)
        text = _("About ${cost} a game").format(cost=f"{total:.2f}") if total >= 0.005 else _("Under a cent a game")
        if any(not s.model_key for s in self.setup.seats):
            text += ", " + _("random seats not counted")
        self.cost.set_label(text)

    def _start(self) -> None:
        if not self.connected and not os.environ.get("NMB_OFFLINE"):
            self._open("settings")
            return
        if any(x.page is None and not x.live.error for x in self.app.sessions):  # one start at a time
            self.app.window.toast(_("A game is starting"))
            return
        setup = self.full_setup()
        problem = setup.problem()
        if problem:
            self.app.window.toast(problem)
            return
        from .launch import start_game
        if os.environ.get("NMB_OFFLINE"):
            start_game(self.app, setup, self.allow_repeat)
            return
        if self.app.loading and not self.app.models:
            self.app.window.toast(_("Loading models"))
            return
        from ..check import draw
        from .check import CheckDialog
        try:
            drawn = draw(setup, self.app.routes, self.allow_repeat, user_pools=self.app.settings.pools)
        except Exception as e:  # noqa: BLE001  an empty pool or a refused model: said on the lobby
            self.app.window.toast(str(e))
            return
        CheckDialog(self.app, drawn, lambda s: start_game(self.app, s, self.allow_repeat), self._fixed).present(self)

    def _fixed(self, index: int, key: str) -> None:
        """A fix made in the seat check sticks to a 지정 seat of the lobby too."""
        i = index - (1 if self.mode == "play" else 0)
        if 0 <= i < len(self.setup.seats) and not self.setup.seats[i].pool:
            put_model(self.setup.seats[i], self.app.routes, key)
            self.changed()

    def _open(self, what: str) -> None:
        if what == "bench":
            from .bench import BenchPage
            self.app.window.push(BenchPage(self.app))
        elif what == "records":
            from .records import RecordsPage
            self.app.window.push(RecordsPage(self.app))
        elif what == "standings":
            from .records import RecordsPage
            page = RecordsPage(self.app)
            page.stack.set_visible_child_name("standings")
            self.app.window.push(page)
        elif what == "settings":
            from .settings import SettingsDialog
            SettingsDialog(self.app).present(self.app.window)
        else:
            about = Adw.AboutDialog(application_name="NeedMoreBench", application_icon=self.app.get_application_id(),
                                    developer_name="needmoretruth", version=_version(),
                                    comments=_("Language models play mafia while you watch, meddle or play."))
            about.present(self.app.window)


def _default_language() -> str:
    from .. import i18n
    return i18n.current


def _version() -> str:
    from .. import __version__
    return __version__
