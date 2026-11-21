"""The playing person's line box during 토론: always open, so the person can talk at any moment.
A sent line goes in right after the current speaker; until it is said the box shows 「다음 차례에 말합니다」."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from .widgets import hbox, label, vbox  # noqa: E402


class Composer(Gtk.Box):
    def __init__(self, send: Callable[[str], None], press: Callable[[str], None]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("action-dock")
        self.send_fn = send
        self.time_btns: dict[str, Gtk.Button] = {}
        for word, text in (("연장", "Longer"), ("단축", "Shorter")):  # once a day each, public
            b = Gtk.Button(label=_(text))
            b.add_css_class("pill")
            b.connect("clicked", lambda _b, w=word: (press(w), self.used(w)))
            self.time_btns[word] = b
        self.waiting = 0  # lines sent and not said yet
        self.entry = Gtk.Entry(placeholder_text=_("Say to everyone"), hexpand=True, max_length=600)
        self.entry.connect("activate", lambda *_a: self._send())
        self.entry.connect("changed", lambda *_a: self._check())
        self.btn = Gtk.Button(label=_("Send"))
        self.btn.add_css_class("pill")
        self.btn.add_css_class("suggested-action")
        self.btn.connect("clicked", lambda *_a: self._send())
        self.status = label("", "meta")
        self.status.set_halign(Gtk.Align.START)
        row = hbox(8, self.status, self.time_btns["연장"], self.time_btns["단축"])
        self.status.set_hexpand(True)
        card = vbox(8, hbox(8, self.entry, self.btn), row)
        card.add_css_class("action-card")
        card.add_css_class("composer")
        self.append(card)
        self._check()
        self._show_status()

    def _check(self) -> None:
        self.btn.set_sensitive(bool(self.entry.get_text().strip()))

    def _send(self) -> None:
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.send_fn(text)

    def queued(self) -> None:
        self.waiting += 1
        self._show_status()

    def said(self) -> None:
        self.waiting = max(0, self.waiting - 1)
        self._show_status()

    def reset(self) -> None:
        """A new step: nothing waiting, and 연장 and 단축 open again for the next discussion."""
        self.waiting = 0
        self._show_status()
        for b in self.time_btns.values():
            b.set_sensitive(True)

    def used(self, word: str) -> None:
        if word in self.time_btns:
            self.time_btns[word].set_sensitive(False)

    def mode(self, meeting: bool) -> None:
        """At night a person on the mafia team talks into the meeting; 연장 and 단축 are for 토론 only."""
        self.entry.set_placeholder_text(_("Say to the mafia team") if meeting else _("Say to everyone"))
        for b in self.time_btns.values():
            b.set_visible(not meeting)

    def _show_status(self) -> None:
        self.status.set_label(_("You speak next") if self.waiting else "")
