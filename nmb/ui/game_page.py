"""The game screen (layout, night, turns bar, votes on cards).

Players on the left, the timeline in the middle, the selected player's 장부 / 노트 / 속마음 on the right.
The same page plays a live game (events from the worker thread) or a replay (events from a saved record).
"""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..engine.state import Event  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import ViewState, step_label  # noqa: E402
from .inspector import Inspector  # noqa: E402
from .widgets import PlayerCard, chip, hbox, label, timeline_row, vbox  # noqa: E402

FILTERS = [("all", "All"), ("say", "Public"), ("whisper", "Whispers"), ("mafia", "Night chats"), ("thought", "Thoughts"), ("reasoning", "Reasoning")]
SPEEDS = [("Slow", 2.4), ("Normal", 1.2), ("Fast", 0.4), ("Fastest", 0.0)]


class GamePage(Adw.NavigationPage):
    def __init__(self, st: ViewState, title: str, on_sound: Callable[[str], None] | None = None,
                 controls: Any = None):
        super().__init__(title=title)  # no tag: a page still sliding out must not block the next game
        self.st = st
        self.on_sound = on_sound or (lambda s: None)
        self.controls = controls  # LiveGame or Replay; None for a still picture
        self.cards: dict[int, PlayerCard] = {}
        self.filter = "all"
        self.selected: int | None = None
        self.on_end: Callable[[], None] | None = None
        self.human_seat: int | None = None  # set by a live game with a person in it
        self.card: Gtk.Widget | None = None
        self.held: list[tuple[int | None, Gtk.Widget]] = []  # thoughts waiting for their speaker's line

        self.root = Adw.ToolbarView()
        self.root.add_css_class("game")
        header = Adw.HeaderBar()
        self.title_label = label(title, "phase-title", xalign=0.5)
        self.sub_label = label("", "phase-sub", xalign=0.5)
        self.phase_icon = Gtk.Image.new_from_icon_name("weather-clear-night-symbolic")
        self.phase_icon.add_css_class("phase-icon")
        top = hbox(6, self.phase_icon, self.title_label)
        top.set_halign(Gtk.Align.CENTER)
        header.set_title_widget(vbox(0, top, self.sub_label))
        self.pause_btn = Gtk.Button(icon_name="media-playback-pause-symbolic", tooltip_text=_("Pause"))
        self.pause_btn.connect("clicked", self._toggle_pause)
        header.pack_start(self.pause_btn)
        self.speed_btn = Gtk.MenuButton(label=_("Normal"), tooltip_text=_("Speed"))
        self.speed_btn.set_popover(self._speed_popover())
        header.pack_start(self.speed_btn)
        self.panel_btn = Gtk.ToggleButton(icon_name="sidebar-show-right-symbolic", tooltip_text=_("Ledger and notes"), active=True)
        header.pack_end(self.panel_btn)
        self.god_btn = Gtk.MenuButton(icon_name="weather-clear-symbolic", tooltip_text=_("God powers"))
        self.god_btn.add_css_class("god-button")
        self.god_btn.set_visible(False)
        header.pack_start(self.god_btn)  # on the left its popover opens inside the window
        self.result_btn = Gtk.Button(label=_("Result"))
        self.result_btn.add_css_class("pill")
        self.result_btn.add_css_class("suggested-action")
        self.result_btn.set_visible(False)
        self.result_btn.connect("clicked", lambda *_a: self.on_end and self.on_end())
        header.pack_end(self.result_btn)
        self.cost_label = label("", "meta")
        header.pack_end(self.cost_label)
        self.cheat_chip = chip(_("Cheats"), "god")  # a playing person sees the god view
        self.cheat_chip.set_tooltip_text(_("You see every thought, night chat and role"))
        self.cheat_chip.set_visible(False)
        header.pack_end(self.cheat_chip)
        self.root.add_top_bar(header)

        # 남은 발언 차례 bar
        self.turns_bar = Gtk.LevelBar(min_value=0, max_value=1, value=1)
        self.turns_bar.set_hexpand(True)
        self.turns_bar.set_valign(Gtk.Align.CENTER)
        self.turns_label = label("", "turns-label")
        self.end_btn = Gtk.Button(label=_("To the vote"))
        self.end_btn.add_css_class("pill")
        self.end_btn.add_css_class("suggested-action")
        self.end_btn.set_visible(False)
        self.end_btn.connect("clicked", lambda *_: self.controls and self.controls.end_discussion())
        self.turns_box = hbox(12, label(_("Turns left"), "meta"), self.turns_bar, self.turns_label, self.end_btn)
        self.turns_box.add_css_class("turns-bar")
        self.turns_revealer = Gtk.Revealer(child=self.turns_box, transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.root.add_top_bar(self.turns_revealer)

        # players
        self.players = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.players.add_css_class("navigation-sidebar")
        self.players.connect("row-selected", self._picked)
        for v in st.seats:
            card = PlayerCard(v)
            self.cards[v.seat] = card
            self.players.append(card)
        ps = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        ps.set_child(self.players)
        self.players_pane = vbox(0, ps)
        self.players_pane.add_css_class("players-pane")
        self.players_pane.set_size_request(250, -1)

        # timeline
        self.timeline = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.timeline.add_css_class("timeline")
        self.timeline.set_filter_func(self._keep)
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        self.scroll.set_child(self.timeline)
        self.scroll.add_css_class("timeline-view")
        self.thinking = label("", "thinking-row")
        self.thinking.set_halign(Gtk.Align.START)
        self.filters = Adw.ToggleGroup()
        for name, text in FILTERS:
            if name != "reasoning" or st.viewer is None:  # a seat without cheats never sees reasoning
                self.filters.add(Adw.Toggle(name=name, label=_(text)))
        self.filters.set_active_name("all")
        self.filters.connect("notify::active-name", self._filter_changed)
        self.filters.set_halign(Gtk.Align.CENTER)
        bar = hbox(0, self.filters)
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_margin_top(8)
        bar.set_margin_bottom(6)
        self.banner = label("", "banner-text", xalign=0.5)
        self.banner_box = vbox(0, self.banner)
        self.banner_box.add_css_class("banner-overlay")
        self.banner_box.set_halign(Gtk.Align.CENTER)
        self.banner_box.set_valign(Gtk.Align.CENTER)
        self.banner_box.set_opacity(0)
        self.banner_box.set_can_target(False)
        overlay = Gtk.Overlay(child=self.scroll)
        overlay.add_overlay(self.banner_box)
        self.center = vbox(0, bar, overlay, self.thinking)
        self.center.add_css_class("timeline-view")
        self.center.set_hexpand(True)
        self.bottom = vbox(0)  # human composer and action cards
        self.center.append(self.bottom)

        # inspector as an overlay split view: a side panel when wide, a sheet when narrow
        self.inspector = Inspector()
        self.split = Adw.OverlaySplitView(sidebar_position=Gtk.PackType.END, min_sidebar_width=370,
                                          max_sidebar_width=400, sidebar_width_fraction=0.28)
        self.split.set_sidebar(self.inspector)
        self.split.set_content(hbox(0, self.players_pane, self.center))
        self.panel_btn.bind_property("active", self.split, "show-sidebar",
                                     gi.repository.GObject.BindingFlags.BIDIRECTIONAL | gi.repository.GObject.BindingFlags.SYNC_CREATE)
        self.root.set_content(self.split)
        self.bottom_bar = vbox(0)  # replay scrubber
        self.root.add_bottom_bar(self.bottom_bar)
        self.set_child(self.root)
        self._banner_anim: Adw.TimedAnimation | None = None
        self.refresh()
        if st.seats:
            self.players.select_row(self.cards[st.viewer if st.viewer is not None else 0])

    # ---- breakpoints (the window adds them) -------------------------------------------------------------
    def narrow(self, on: bool) -> None:
        self.split.set_collapsed(on)
        self.players_pane.set_size_request(210 if on else 250, -1)

    # ---- events ----------------------------------------------------------------------------------------
    def feed(self, e: Event, animate: bool = True) -> None:
        was_night = self.st.phase == "night"
        line = self.st.apply(e)
        if line:
            row = timeline_row(self.st, e)
            if row is not None and e.kind in ("thought", "reasoning"):
                self.held.append((e.actor, row))  # shown under the line it led to
            elif row is not None:
                self._place(row, e.actor)
                if animate:
                    self._scroll_soon()
        elif e.kind in ("step", "human_turn"):
            self._place(None, None)
        if animate:
            if e.kind == "phase" and e.data.get("banner"):
                self.show_banner(e.data["banner"])
            if e.data.get("sound") and self.st.sees(e):
                self.on_sound(e.data["sound"])
        if e.kind == "human_turn" and animate and self.human_seat is not None and e.to and self.human_seat in e.to:
            self.ask_human(e.data.get("request") or {})
        elif e.kind == "end":
            self.clear_card()
        if e.kind in ("phase", "end") or was_night != (self.st.phase == "night"):
            self._night(self.st.phase == "night")
        self.refresh(changed=e)
        if e.kind == "end" and self.on_end is not None and animate:
            GLib.timeout_add(1400, lambda: (self.on_end and self.on_end(), False)[1])

    def _place(self, row: Gtk.Widget | None, actor: int | None) -> None:
        """A 속마음 is emitted before the action it led to; it is placed right under that player's next line.
        Thoughts of others (a silent turn, a secret vote) come first, so nothing waits past the next line."""
        mine = [r for a, r in self.held if actor is not None and a == actor]
        for r in [r for a, r in self.held if actor is None or a != actor] + ([row] if row is not None else []) + mine:
            self.timeline.append(r)
        self.held = []

    def rebuild(self, events: list[Event], st: ViewState) -> None:
        """Replay jump: rebuild the whole screen from the first event up to a point, without motion."""
        self.st = st
        self.held = []
        child = self.timeline.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.timeline.remove(child)
            child = nxt
        for e in events:
            self.feed(e, animate=False)
        self._place(None, None)
        self._night(self.st.phase == "night")
        self.refresh()
        self._scroll_soon()

    def refresh(self, changed: Event | None = None) -> None:
        st = self.st
        self.title_label.set_label(st.phase_title())
        self.phase_icon.set_visible(st.phase in ("day", "night") and st.day > 0)
        self.phase_icon.set_from_icon_name("weather-clear-night-symbolic" if st.phase == "night" else "weather-clear-symbolic")
        sub = step_label(st.step) if st.phase == "day" else ""
        if st.paused:
            sub = (sub + ", " if sub else "") + _("Paused")
        self.sub_label.set_label(sub)
        for v in st.seats:
            self.cards[v.seat].update(st, v)
        names = st.thinking_names()
        if self.human_seat is not None:  # the person's own turn shows as the card, not as thinking
            names = [n for n in names if n != st.name_of(self.human_seat)]
        who = ", ".join(names[:3]) + (" …" if len(names) > 3 else "")
        self.thinking.set_label(_("{names} thinking").format(names=who) if names else "")
        self.thinking.set_visible(bool(names))
        talking = st.phase == "day" and st.step == "토론" and st.turns_total > 0
        self.turns_revealer.set_reveal_child(talking)
        if talking:
            total = max(st.turns_total, st.turns_left, 1)
            self.turns_bar.set_max_value(total)
            self.turns_bar.set_value(st.turns_left)
            self.turns_label.set_label(f"{st.turns_left}/{total}")
            alive = sum(1 for v in st.seats if v.alive)
            (self.turns_box.add_css_class if st.turns_left <= alive else self.turns_box.remove_css_class)("low")
        self.end_btn.set_visible(talking and st.would_end)
        self.end_btn.set_label(_("To the vote") if st.vote_next else _("To night"))
        cost = st.cost()
        self.cost_label.set_label(_("About ${cost}").format(cost=f"{cost:.3f}") if cost >= 0.0005 else "")
        self.pause_btn.set_icon_name("media-playback-start-symbolic" if st.paused else "media-playback-pause-symbolic")
        self.pause_btn.set_tooltip_text(_("Resume") if st.paused else _("Pause"))
        self.pause_btn.set_sensitive(st.result is None and self.controls is not None)
        self.result_btn.set_visible(st.result is not None and self.on_end is not None)
        self.god_btn.set_sensitive(st.result is None)
        if changed is None or changed.kind in ("ledger", "note", "thought", "call", "death", "end", "phase", "god", "start"):
            self.inspector.update(st)

    # ---- the person's turn and the powers ---------------------------------------------------------------
    def enable_powers(self) -> None:
        from .god import GodPopover
        self.god_btn.set_popover(GodPopover(self))
        self.god_btn.set_visible(True)

    def ask_human(self, req: dict[str, Any]) -> None:
        from .human import ActionCard, card_box
        self.clear_card()
        me = self.st.seats[self.human_seat].name if self.human_seat is not None else ""
        others = [v.name for v in self.st.seats if v.alive and v.name != me]

        def send(obj: dict[str, Any]) -> None:
            self.clear_card()
            if self.controls is not None:
                self.controls.answer(obj)
        card = ActionCard(req, send, others)
        self.card = card_box(card)
        self.bottom.append(self.card)
        self.on_sound("turn")
        focus = card.say or card.whisper_text
        if focus is not None:
            focus.grab_focus()
        self._scroll_soon()

    def clear_card(self) -> None:
        if self.card is not None:
            self.bottom.remove(self.card)
            self.card = None

    # ---- pieces -----------------------------------------------------------------------------------------
    def _night(self, on: bool) -> None:
        (self.root.add_css_class if on else self.root.remove_css_class)("night")

    def show_banner(self, text: str) -> None:
        self.banner.set_label(text)
        if self._banner_anim is not None:
            self._banner_anim.skip()
        target = Adw.CallbackAnimationTarget.new(self._banner_opacity)
        anim = Adw.TimedAnimation.new(self.banner_box, 0, 1, 2200, target)
        anim.set_easing(Adw.Easing.LINEAR)
        self._banner_anim = anim
        anim.play()

    def _banner_opacity(self, t: float) -> None:
        # fade in for the first 15 %, hold, fade out for the last 25 %
        a = t / 0.15 if t < 0.15 else 1.0 if t < 0.75 else max(0.0, (1 - t) / 0.25)
        self.banner_box.set_opacity(a)

    def _scroll_soon(self) -> None:
        adj = self.scroll.get_vadjustment()
        near = adj.get_value() + adj.get_page_size() >= adj.get_upper() - 160

        def go() -> bool:
            a = self.scroll.get_vadjustment()
            a.set_value(a.get_upper() - a.get_page_size())
            return False
        if near:
            GLib.timeout_add(30, go)

    def _keep(self, row: Gtk.ListBoxRow) -> bool:
        kind = getattr(row, "kind", "system")
        if kind == "reasoning":  # the models' own reasoning has its own view only
            return self.filter == "reasoning"
        return self.filter == "all" or kind == self.filter  # thoughts show in 전체 as muted notes

    def _filter_changed(self, *_: Any) -> None:
        self.filter = self.filters.get_active_name() or "all"
        self.timeline.invalidate_filter()

    def _picked(self, _lb: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None:
            return
        seat = getattr(row, "seat", None)
        if self.st.viewer is not None and seat != self.st.viewer and self.st.result is None:
            seat = self.st.viewer  # a playing human only reads their own ledger
        self.selected = seat
        self.inspector.show_seat(self.st, seat)
        if self.split.get_collapsed():
            self.split.set_show_sidebar(True)

    def _toggle_pause(self, *_: Any) -> None:
        if self.controls is not None:
            self.controls.pause(not self.st.paused)

    def _speed_popover(self) -> Gtk.Popover:
        box = vbox(2)
        for text, secs in SPEEDS:
            b = Gtk.Button(label=_(text))
            b.add_css_class("flat")
            b.connect("clicked", self._set_speed, text, secs)
            box.append(b)
        pop = Gtk.Popover(child=box)
        return pop

    def _set_speed(self, btn: Gtk.Button, text: str, secs: float) -> None:
        self.speed_btn.set_label(_(text))
        btn.get_ancestor(Gtk.Popover).popdown()
        if self.controls is not None and hasattr(self.controls, "set_delay"):
            self.controls.set_delay(secs)
