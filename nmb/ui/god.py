"""신의 권능: the powers popover on the game screen header, for the god view with powers on
(관전 with the switch, or 참가 with 치트). Every use goes to the engine, which records it in the timeline."""
from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from ..view import ViewState, role_label  # noqa: E402
from .widgets import hbox, label, vbox  # noqa: E402

ON_LIVING = [("천벌", "Smite"), ("보호", "Protect"), ("침묵", "Silence")]


class GodPopover(Gtk.Popover):
    def __init__(self, page: Any):
        super().__init__()
        self.page = page
        self.add_css_class("god-popover")
        self.notice = Gtk.Entry(placeholder_text=_("Announce to everyone"), hexpand=True, max_length=300)
        self.notice.connect("activate", lambda *_a: self._announce())
        send = self._btn(_("Announce"), self._announce)

        self.who = Gtk.DropDown.new_from_strings([v.name for v in page.st.seats])
        self.who.set_hexpand(True)
        self.who.connect("notify::selected", lambda *_a: self._sync())
        self.living = {power: self._btn(_(text), lambda p=power: self._on_one(p)) for power, text in ON_LIVING}
        self.revive = self._btn(_("Revive"), lambda: self._on_one("부활"))
        self.secret = Gtk.Entry(placeholder_text=_("Revelation, true or false"), hexpand=True, max_length=300)
        self.secret.connect("activate", lambda *_a: self._reveal())
        reveal = self._btn(_("Reveal"), self._reveal)
        self.roles = sorted({v.role for v in page.st.seats if v.role} | {"시민", "마피아"})
        self.role = Gtk.DropDown.new_from_strings([role_label(r) for r in self.roles])
        self.role.set_hexpand(True)
        change = self._btn(_("Change role"), self._change_role)
        skip = self._btn(_("Next step"), lambda: self._power("다음 단계로"))

        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=4, column_spacing=6,
                              row_spacing=6, homogeneous=True)
        for b in [*self.living.values(), self.revive]:
            actions.append(b)
        body = vbox(10,
                    label(_("Everyone"), "heading"), hbox(6, self.notice, send),
                    Gtk.Separator(),
                    label(_("One player"), "heading"), self.who, actions,
                    hbox(6, self.secret, reveal), hbox(6, self.role, change),
                    Gtk.Separator(), skip)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(8)
        body.set_size_request(320, -1)
        self.set_child(body)
        self.connect("show", lambda *_a: self._sync())

    @staticmethod
    def _btn(text: str, cb: Any) -> Gtk.Button:
        b = Gtk.Button(label=text)
        b.add_css_class("god-power")
        b.connect("clicked", lambda *_a: cb())
        return b

    @property
    def st(self) -> ViewState:
        return self.page.st

    def _seat(self) -> int:
        return int(self.who.get_selected())

    def _sync(self) -> None:
        if not self.st.seats:
            return
        alive = self.st.seats[self._seat()].alive
        over = self.st.result is not None
        for b in self.living.values():
            b.set_sensitive(alive and not over)
        self.revive.set_sensitive(not alive and not over)

    def _power(self, power: str, seat: int | None = None, text: str = "", role: str | None = None) -> None:
        if self.page.controls is not None and self.st.result is None:
            self.page.controls.god(power, seat, text, role)

    def _announce(self) -> None:
        text = self.notice.get_text().strip()
        if text:
            self._power("공지", text=text)
            self.notice.set_text("")
            self.popdown()

    def _reveal(self) -> None:
        text = self.secret.get_text().strip()
        if text:
            self._power("계시", self._seat(), text)
            self.secret.set_text("")
            self.popdown()

    def _on_one(self, power: str) -> None:
        self._power(power, self._seat())
        self.popdown()

    def _change_role(self) -> None:
        self._power("역할 바꾸기", self._seat(), role=self.roles[int(self.role.get_selected())])
        self.popdown()
