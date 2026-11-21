"""The playing person's own 장부 and 노트, editable in the right panel (참가).

Every change goes to the engine as the same ledger and notes edits a model sends; the engine checks it and
the panel then shows what the engine kept."""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ..engine.state import NOTE_PAGE  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import Row, role_label  # noqa: E402
from .widgets import hbox, label  # noqa: E402

Send = Callable[[dict[str, Any]], None]


class OwnLedgerLine(Gtk.Box):
    """One other player in the person's ledger: suspicion slider, role guess and a short remark."""

    def __init__(self, name: str, guesses: list[str], send: Send):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.add_css_class("ledger-row")
        self.add_css_class("own")
        self.name, self.guesses, self.send = name, guesses or ["모름"], send
        self._quiet = False
        self._timer = 0
        who = label(name, "name")
        who.set_hexpand(True)
        who.set_ellipsize(Pango.EllipsizeMode.END)
        self.guess = Gtk.DropDown.new_from_strings([role_label(g) for g in self.guesses])
        self.guess.add_css_class("flat")
        self.guess.set_tooltip_text(_("Role guess"))
        self.guess.connect("notify::selected", lambda *_a: self._changed({"guess": self.guesses[self.guess.get_selected()]}))
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        self.scale.add_css_class("sus-scale")
        self.scale.set_tooltip_text(_("Suspicion"))
        self.scale.connect("value-changed", lambda *_a: self._slid())
        self.num = label("50", "sus-num", xalign=1.0)
        self.num.set_width_chars(3)
        self.note = Gtk.Entry(placeholder_text=_("Remark"), max_length=200)
        self.note.add_css_class("own-note")
        self.note.connect("activate", lambda *_a: self._note())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_a: self._note())
        self.note.add_controller(focus)
        self.sure = label(_("Confirmed"), "known-tag")
        self.sure.set_tooltip_text(_("The game told you this player's team and role"))
        self.sure.set_visible(False)
        self.append(hbox(8, who, self.sure, self.guess))
        self.append(hbox(8, self.scale, self.num))
        self.append(self.note)
        self.kept = Row()

    def update(self, row: Row) -> None:
        self.kept = row
        self.sure.set_visible(row.known)
        self._quiet = True
        if self._timer == 0:
            self.scale.set_value(row.suspicion)
            self.num.set_label(str(row.suspicion))
        if row.guess in self.guesses:
            self.guess.set_selected(self.guesses.index(row.guess))
        if not self.note.has_focus() and self.note.get_text() != row.note:
            self.note.set_text(row.note)
        self._quiet = False

    def _changed(self, edit: dict[str, Any]) -> None:
        if not self._quiet:
            self.send({"ledger": [{"name": self.name, **edit}]})

    def _slid(self) -> None:
        v = int(round(self.scale.get_value()))
        self.num.set_label(str(v))
        if self._quiet:
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(350, self._send_slide)  # one edit when the hand stops, not one per pixel

    def _send_slide(self) -> bool:
        self._timer = 0
        self._changed({"suspicion": int(round(self.scale.get_value()))})
        return False

    def _note(self) -> None:
        text = self.note.get_text().strip()
        if text != self.kept.note:
            self._changed({"note": text})


class OwnNotes(Gtk.Box):
    """The person's notebook page: one page of up to 1,200 characters, written whole, as a model
    sends its whole new page. Saved when the person presses 저장 or leaves the page."""

    def __init__(self, send: Send):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.send = send
        self.set_vexpand(False)
        self.view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, accepts_tab=False, vexpand=False)
        page = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=False, min_content_height=340,
                                  max_content_height=340, child=self.view)  # a full page scrolls inside; 저장 stays in sight
        page.add_css_class("note-page")
        self.buf = self.view.get_buffer()
        self.buf.connect("changed", lambda *_a: self._count())
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_a: self._save())
        self.view.add_controller(focus)
        self.count = label("", "meta", xalign=0.0)
        self.count.set_hexpand(True)
        self.save = Gtk.Button(label=_("Save"))
        self.save.add_css_class("pill")
        self.save.connect("clicked", lambda *_a: self._save())
        self.append(page)
        self.append(hbox(8, self.count, self.save))
        self.kept = ""
        self._count()

    def _text(self) -> str:
        return self.buf.get_text(self.buf.get_start_iter(), self.buf.get_end_iter(), False)

    def _count(self) -> None:
        n = len(self._text().strip())
        self.count.set_label(_("{n} / {limit} chars").format(n=f"{n:,}", limit=f"{NOTE_PAGE:,}"))
        over = n > NOTE_PAGE
        if over:
            self.count.add_css_class("error")
        else:
            self.count.remove_css_class("error")
        self.save.set_sensitive(not over and self._text().strip() != self.kept)

    def update(self, page: str) -> None:
        if page == self.kept:
            return
        self.kept = page
        if not self.view.has_focus():
            self.buf.set_text(page)
        self._count()

    def _save(self) -> None:
        text = self._text().strip()
        if text != self.kept and len(text) <= NOTE_PAGE:
            self.send({"notes": text})
