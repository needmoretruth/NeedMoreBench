"""The lobby's 프리셋 menu: built-in lineups, saved ones, and saving the current seats."""
from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk  # noqa: E402

from .. import presets  # noqa: E402
from ..engine.roles import PLAYER_RANGE  # noqa: E402
from ..i18n import _  # noqa: E402
from ..pools import PRESETS  # noqa: E402
from .widgets import hbox, label, vbox  # noqa: E402


class PresetMenu(Gtk.MenuButton):
    def __init__(self, home: Any):
        super().__init__(label=_("Presets"), valign=Gtk.Align.CENTER, tooltip_text=_("Load or save a lineup"))
        self.add_css_class("flat")
        self.home = home
        self.pop = Gtk.Popover()
        self.set_popover(self.pop)
        self.pop.connect("show", lambda *_a: self._fill())

    @property
    def app(self) -> Any:
        return self.home.app

    def _fill(self) -> None:
        box = vbox(4)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.append(label(_("Built in"), "caption-heading"))
        names = {"major": _("Major models"), "free": _("Free models"), "china": _("Chinese models"),
                 "usa": _("American models")}
        for name in PRESETS:
            b = Gtk.Button(label=names.get(name, name))
            b.add_css_class("flat")
            b.get_child().set_xalign(0)
            b.connect("clicked", lambda *_a, n=name: self._built_in(n))
            box.append(b)
        mine = self.app.settings.presets
        if mine:
            box.append(label(_("Saved"), "caption-heading"))
        for name in sorted(mine):
            load = Gtk.Button(label=name, hexpand=True)
            load.add_css_class("flat")
            load.get_child().set_xalign(0)
            load.connect("clicked", lambda *_a, n=name: self._load(n))
            drop = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=_("Delete"))
            drop.add_css_class("flat")
            drop.connect("clicked", lambda *_a, n=name: self._delete(n))
            box.append(hbox(2, load, drop))
        entry = Gtk.Entry(placeholder_text=_("Preset name"), hexpand=True)
        save = Gtk.Button(label=_("Save"))
        save.connect("clicked", lambda *_a: self._save(entry.get_text()))
        entry.connect("activate", lambda e: self._save(e.get_text()))
        row = hbox(6, entry, save)
        row.set_margin_top(6)
        box.append(row)
        self.pop.set_child(box)

    def _seats_range(self) -> tuple[int, int, int]:
        h = self.home
        lo, hi = PLAYER_RANGE[h.setup.kind]
        me = 1 if h.mode == "play" else 0
        return len(h.setup.seats), lo - me, hi - me

    def _built_in(self, name: str) -> None:
        self.pop.popdown()
        n, lo, hi = self._seats_range()
        seats, missing = presets.built_in(self.app.routes, name, n, lo, hi)
        if not any(s.model_key for s in seats):
            self.app.window.toast(_("No model for this preset answers right now"))
            return
        self.home.setup.seats = seats
        self.home.changed()
        if missing:
            self.app.window.toast(_("Left out, no route offers them now: {makers}").format(makers=", ".join(missing)))

    def _load(self, name: str) -> None:
        self.pop.popdown()
        _n, lo, hi = self._seats_range()
        seats = presets.from_saved(self.app.settings.presets.get(name, {}))[:hi]
        while len(seats) < lo:
            seats.append(presets.SeatSpec(pool="free"))
        self.home.setup.seats = seats
        self.home.changed()

    def _save(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self.pop.popdown()
        self.app.settings.presets[name] = presets.saved(self.home.setup.seats)
        self.app.settings.save()
        self.app.window.toast(_("Saved as {name}").format(name=name))

    def _delete(self, name: str) -> None:
        self.app.settings.presets.pop(name, None)
        self.app.settings.save()
        self._fill()
