"""The playing person's own 장부 and 노트, editable in the right panel (참가).

Every change goes to the engine as the same ledger and notes edits a model sends; the engine checks it and
the panel then shows what the engine kept."""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from ..i18n import _  # noqa: E402
from ..view import Row, role_label  # noqa: E402
from .widgets import clear, hbox, label, vbox  # noqa: E402

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
        self.append(hbox(8, who, self.guess))
        self.append(hbox(8, self.scale, self.num))
        self.append(self.note)
        self.kept = Row()

    def update(self, row: Row) -> None:
        self.kept = row
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
    """The person's notebook: add, edit and delete, as a model does through its answer."""

    def __init__(self, send: Send):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.send = send
        self.entry = Gtk.Entry(placeholder_text=_("New note"), max_length=400, hexpand=True)
        self.entry.connect("activate", lambda *_a: self._add())
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=_("Add note"))
        add.connect("clicked", lambda *_a: self._add())
        self.append(hbox(6, self.entry, add))
        self.list = vbox(6)
        self.append(self.list)
        self.shown: dict[int, str] | None = None
        self.last: dict[int, str] = {}
        self.editing: int | None = None

    def update(self, notes: dict[int, str]) -> None:
        self.last = dict(notes)
        if notes == self.shown or self.editing is not None:
            return
        self.shown = dict(notes)
        clear(self.list)
        if not notes:
            self.list.append(label(_("No notes."), "dim"))
        for nid, text in sorted(notes.items()):
            self.list.append(self._row(nid, text))

    def _row(self, nid: int, text: str) -> Gtk.Widget:
        body = label(text, wrap=True, selectable=True)
        body.set_hexpand(True)
        edit = Gtk.Button(icon_name="document-edit-symbolic", tooltip_text=_("Edit"))
        delete = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Delete"))
        for b in (edit, delete):
            b.add_css_class("flat")
            b.set_valign(Gtk.Align.START)
        row = vbox(2, label(f"#{nid}", "note-id"), hbox(4, body, edit, delete))
        row.add_css_class("note-row")
        edit.connect("clicked", lambda *_a: self._edit(row, nid, text))
        delete.connect("clicked", lambda *_a: self.send({"notes": {"delete": [nid]}}))
        return row

    def _edit(self, row: Gtk.Box, nid: int, text: str) -> None:
        self.editing = nid
        entry = Gtk.Entry(text=text, max_length=400, hexpand=True)
        clear(row)
        row.append(label(f"#{nid}", "note-id"))
        row.append(entry)
        entry.grab_focus()

        def done(*_a: Any) -> None:
            if self.editing != nid:
                return
            self.editing = None
            new = entry.get_text().strip()
            if new and new != text:
                self.send({"notes": {"edit": [{"id": nid, "text": new}]}})
            self.shown = None  # draw the list again from what the engine keeps
            GLib.idle_add(lambda: (self.update(self.last), False)[1])
        entry.connect("activate", done)
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", done)
        entry.add_controller(focus)

    def _add(self) -> None:
        text = self.entry.get_text().strip()
        if text:
            self.send({"notes": {"add": [text]}})
            self.entry.set_text("")
