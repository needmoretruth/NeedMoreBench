"""The right panel: the selected player's 장부, 노트 and 속마음.

Suspicion bars animate to their new value and the changed row flashes softly. A playing human sees only
their own panel (and edits it); the god view can open anyone's.
"""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..i18n import _, counted  # noqa: E402
from ..view import Row, SeatView, ViewState, role_label, team_class  # noqa: E402
from .own import OwnLedgerLine, OwnNotes  # noqa: E402
from .widgets import avatar, chip, clear, hbox, label, vbox  # noqa: E402


def _level(v: int) -> str:
    return "low" if v < 40 else "high" if v > 60 else "mid"


class LedgerLine(Gtk.Box):
    def __init__(self, name: str):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("ledger-row")
        self.who = label(name, "name")
        self.who.set_hexpand(True)
        self.who.set_ellipsize(Pango.EllipsizeMode.END)
        self.num = label("50", "sus-num", xalign=1.0)
        self.guess = chip(role_label("모름"))
        self.bar = Gtk.LevelBar(min_value=0, max_value=100, value=50)
        self.bar.add_css_class("sus-bar")
        self.bar.set_hexpand(True)
        self.bar.set_valign(Gtk.Align.CENTER)
        self.note = label("", "meta", wrap=True)
        self.sure = label(_("Confirmed"), "known-tag")
        self.sure.set_tooltip_text(_("The game told this player the other's team and role"))
        self.sure.set_visible(False)
        self.append(hbox(8, self.who, self.sure, self.guess))
        self.append(hbox(8, self.bar, self.num))
        self.append(self.note)
        self._shown = 50.0
        self._anim: Adw.TimedAnimation | None = None
        self._seen = -1

    def update(self, row: Row) -> None:
        self.sure.set_visible(row.known)
        self.guess.set_label(role_label(row.guess))
        for c in ("mafia", "town", "cult", "plain"):
            self.guess.remove_css_class(c)
        self.guess.add_css_class(team_class(row.guess) if row.guess != "모름" else "plain")
        self.note.set_label(row.note)
        self.note.set_visible(bool(row.note))
        self.num.set_label(str(row.suspicion))
        for c in ("low", "mid", "high"):
            self.bar.remove_css_class(c)
        self.bar.add_css_class(_level(row.suspicion))
        if abs(self._shown - row.suspicion) > 0.5:
            self._animate(row.suspicion)
        if row.changed != self._seen and row.changed >= 0 and self._seen != -1:
            self.add_css_class("flash")
            GLib.timeout_add(900, self._unflash)
        self._seen = row.changed

    def _animate(self, to: float) -> None:
        if self._anim is not None:
            self._anim.skip()
        target = Adw.CallbackAnimationTarget.new(self._set)
        self._anim = Adw.TimedAnimation.new(self.bar, self._shown, to, 650, target)
        self._anim.set_easing(Adw.Easing.EASE_OUT_CUBIC)
        self._anim.play()

    def _set(self, value: float) -> None:
        self._shown = value
        self.bar.set_value(value)

    def _unflash(self) -> bool:
        self.remove_css_class("flash")
        return False


class Inspector(Gtk.Box):
    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("inspector-pane")
        self.set_size_request(370, -1)
        self.seat: int | None = None
        # the playing person's seat, whose ledger and notes are editable (set by the game page)
        self.own_seat: int | None = None
        self.send_edit: Callable[[dict], None] | None = None
        self.guesses: list[str] = []
        self.own_notes: OwnNotes | None = None
        self._page_key: tuple | None = None
        self.head_avatar = avatar("?", 44)
        self.head_name = label("", "title-4")
        self.head_name.set_ellipsize(Pango.EllipsizeMode.END)
        self.head_meta = label("", "meta")
        self.head_meta.set_ellipsize(Pango.EllipsizeMode.END)
        self.head_role = chip("")
        head = hbox(12, self.head_avatar, vbox(2, hbox(6, self.head_name, self.head_role), self.head_meta))
        head.set_margin_top(14)
        head.set_margin_start(14)
        head.set_margin_end(14)
        self.append(head)
        self.stack = Adw.ViewStack()
        self.ledger_box = vbox(6)
        self.notes_box = vbox(6)
        self.thought_box = vbox(6)
        self.whisper_box = vbox(6)
        self.reasoning_box = vbox(6)
        self.lines: dict[str, LedgerLine] = {}
        for name, title, box in (("ledger", _("Ledger"), self.ledger_box), ("notes", _("Notes"), self.notes_box),
                                 ("thoughts", _("Thoughts"), self.thought_box), ("whispers", _("Whispers"), self.whisper_box),
                                 ("reasoning", _("Reasoning"), self.reasoning_box)):
            box.set_margin_start(12)
            box.set_margin_end(12)
            box.set_margin_bottom(16)
            sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
            sc.set_child(box)
            self.stack.add_titled(sc, name, title)
        # each tab as wide as its word: equal widths cut the English words to "L..." in this narrow pane
        switcher = Adw.InlineViewSwitcher(stack=self.stack, homogeneous=False, can_shrink=False)
        switcher.add_css_class("inspector-tabs")
        switcher.set_margin_top(12)
        switcher.set_margin_bottom(8)
        switcher.set_margin_start(8)
        switcher.set_margin_end(8)
        self.append(switcher)
        self.append(self.stack)
        self.empty = label(_("Pick a player on the left."), "dim", wrap=True, xalign=0.5)

    def show_seat(self, st: ViewState, seat: int | None) -> None:
        if seat != self.seat:
            self.seat = seat
            clear(self.ledger_box)
            self.lines = {}
            self.own_notes = None
        self.update(st)

    def _editable(self, st: ViewState) -> bool:
        return self.seat is not None and self.seat == self.own_seat and self.send_edit is not None and st.result is None

    def _send(self, obj: dict) -> None:
        if self.send_edit is not None:
            self.send_edit(obj)

    def update(self, st: ViewState) -> None:
        if self.seat is None:
            return
        v: SeatView = st.seats[self.seat]
        self.head_avatar.set_text(v.name)
        self.head_name.set_label(v.name)
        meta = v.model_line if (st.owner_sees_models or st.result is not None) else ""
        if v.calls:
            meta = (meta + ", " if meta else "") + counted(v.calls, "{n} call", "{n} calls") + (", " + _("{n} failed").format(n=v.failed) if v.failed else "")
        self.head_meta.set_label(meta)
        show = st.role_visible(v) and bool(v.role)
        self.head_role.set_visible(show)
        if show:
            self.head_role.set_label(role_label(v.role))
            for c in ("mafia", "town", "cult", "plain"):
                self.head_role.remove_css_class(c)
            self.head_role.add_css_class(team_class(v.role))
        editable = self._editable(st)
        for name, row in v.ledger.items():
            line = self.lines.get(name)
            if line is not None and isinstance(line, OwnLedgerLine) != editable:  # the game ended: read-only again
                self.ledger_box.remove(line)
                line = None
            if line is None:
                line = OwnLedgerLine(name, self.guesses, self._send) if editable else LedgerLine(name)
                self.lines[name] = line
                self.ledger_box.append(line)
            line.update(row)
            dead = st.by_name(name)
            line.set_opacity(0.55 if dead is not None and not dead.alive else 1.0)
        if editable:
            if self.own_notes is None:
                clear(self.notes_box)
                self._page_key = None
                self.own_notes = OwnNotes(self._send)
                self.notes_box.append(self.own_notes)
            self.own_notes.update(v.page)
        else:
            self.own_notes = None
            self._page(v)
        self._whispers(st, v)
        clear(self.thought_box)
        if not v.thoughts:
            self.thought_box.append(label(_("Nothing yet."), "dim"))
        for when, text in reversed(v.thoughts[-12:]):
            t = vbox(2, label(when, "note-id"), label(text, wrap=True, selectable=True))
            t.add_css_class("note-row")
            self.thought_box.append(t)
        page = self.stack.get_page(self.stack.get_child_by_name("reasoning"))
        page.set_visible(st.viewer is None)  # a seat without cheats never sees reasoning
        clear(self.reasoning_box)  # the model's own reasoning, as its route returned it
        if not v.reasonings:
            self.reasoning_box.append(label(_("Its route returns no reasoning.") if v.calls else _("Nothing yet."), "dim", wrap=True))
        for when, text, summarized in reversed(v.reasonings[-12:]):
            t = vbox(2, label(when + (", " + _("Summary") if summarized else ""), "note-id"), label(text, wrap=True, selectable=True))
            t.add_css_class("note-row")
            self.reasoning_box.append(t)

    def _page(self, v: SeatView) -> None:
        """The notebook page now, then the earlier versions newest first. Drawn again only when a
        version is added, so an open list of versions stays open."""
        key = (v.seat, len(v.pages), v.page)
        if key == self._page_key:
            return
        self._page_key = key
        clear(self.notes_box)
        if not v.page:
            self.notes_box.append(label(_("No notes."), "dim"))
        else:
            when = v.pages[-1][0] if v.pages else ""
            n = vbox(2, label(when, "note-id"), label(v.page, wrap=True, selectable=True))
            n.add_css_class("note-row")
            self.notes_box.append(n)
        older = v.pages[:-1]
        if not older:
            return
        box = vbox(6)
        for when, text in reversed(older):
            t = vbox(2, label(when, "note-id"), label(text or _("(empty)"), "meta", wrap=True, selectable=True))
            t.add_css_class("note-row")
            box.append(t)
        exp = Gtk.Expander(label=_("Earlier versions ({n})").format(n=len(older)), child=box)
        exp.set_margin_top(8)
        self.notes_box.append(exp)

    def _whispers(self, st: ViewState, v: SeatView) -> None:
        """This player's whispers as one conversation per partner, in order (pair view)."""
        clear(self.whisper_box)
        talks: dict[int, list] = {}
        for e in st.lines:
            if v.seat in (e.actor, e.target):
                other = e.target if e.actor == v.seat else e.actor
                talks.setdefault(other, []).append(e)
        if not talks:
            self.whisper_box.append(label(_("No whispers."), "dim"))
        for other, lines in talks.items():
            head = hbox(6, avatar(v.name, 20), label(v.name, "name"), label("↔", "meta"), avatar(st.name_of(other), 20),
                        label(st.name_of(other), "name"))
            head.set_margin_top(8)
            self.whisper_box.append(head)
            for e in lines:
                t = vbox(2, label(f"{st.name_of(e.actor)}, {st.when(e)}", "note-id"),
                         label(e.text, wrap=True, selectable=True))
                t.add_css_class("note-row")
                if e.actor == v.seat:
                    t.add_css_class("mine-whisper")
                self.whisper_box.append(t)
