"""Model picker: search, filter chips, a price tag per row, unusable rows dimmed with the reason.
A seat can also take a pool (랜덤) instead of one model."""
from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..choose import kept, route_key, seat_routes  # noqa: E402
from ..i18n import _  # noqa: E402
from ..providers.base import ModelInfo, ModelRef  # noqa: E402
from ..providers.health import words  # noqa: E402
from ..providers.merge import keys_of, rank, route_name  # noqa: E402
from ..providers.registry import Routes  # noqa: E402
from ..view import country_label  # noqa: E402
from .widgets import label  # noqa: E402

FILTERS = [("all", "All"), ("free", "Free"), ("opencode", "OpenCode"), ("go", "Go"), ("anthropic", "Anthropic"),
           ("venice", "Venice"), ("openrouter", "OpenRouter"), ("lmstudio", "LM Studio")]
POOLS = [("all", "All models"), ("free", "Free models"), ("latest", "Latest models")]


def route_label(m: ModelInfo) -> str:
    """The route as the user names it, so Zen free and Zen paid are told apart."""
    name = route_name(m)
    return {"OpenCode free": _("OpenCode free"), "Venice (OpenCode)": _("Venice (OpenCode)")}.get(name, name)


def price_text(m: ModelInfo | None) -> str:
    if m is None:
        return ""
    if m.free:
        return _("Free")
    if m.status == "가격 모름":
        return _("Price unknown")
    return f"${m.price_in:g} / ${m.price_out:g}"


def seat_price(m: ModelInfo | None) -> str:
    """What a seat costs in words: 무료, Go 구독 for OpenCode Go's paid models (they draw on the Go
    subscription's included usage), or the price."""
    if m is not None and not m.free and route_name(m) == "OpenCode Go":
        return _("Go subscription")
    return price_text(m)


def place_text(m: ModelInfo) -> str:
    unknown = _("Unknown")
    return ", ".join([m.maker or unknown, country_label(m.country) if m.country else unknown, route_label(m)])


def why_not(routes: Routes, m: ModelInfo) -> str:
    """Why the model cannot be used now, in plain words with the time it clears; '' when it can."""
    p = routes.problem(m)
    if p is None or p.kind == "busy":
        return ""
    if p.kind == "trains":
        return _("Trains on prompts (allow in Settings)")
    if p.kind == "big":
        return _("Too big: load it in LM Studio yourself")
    text = words(m.name, p, m.ref.route)
    return text.split(": ", 1)[1] if text.startswith(m.name + ": ") else text


def route_menu(parent: Gtk.Widget, routes: Routes, key: str, on_pick: Callable[[str], None]) -> Gtk.Popover:
    """A popover under the seat row: the same model on each route, the one in use marked, unusable ones dimmed
    with the reason. Picking one overrides the route chosen by the user's order."""
    current = ModelRef.parse(key)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=6, margin_bottom=6, margin_start=6,
                  margin_end=6)
    box.append(label(_("Route"), "caption-heading"))
    pop = Gtk.Popover(child=box)
    for m in seat_routes(routes, key):
        reason = why_not(routes, m)
        on = (m.ref.route, m.ref.provider, m.ref.id) == (current.route, current.provider, current.id)
        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        text.append(label(route_label(m)))
        text.append(label(reason or price_text(m), "meta"))
        line.append(text)
        if on:
            line.append(Gtk.Image.new_from_icon_name("object-select-symbolic"))
        b = Gtk.Button(child=line, sensitive=not reason or on)
        b.add_css_class("flat")
        b.connect("clicked", lambda *_a, k=m.key: (pop.popdown(), on_pick(k)))
        box.append(b)
    pop.set_parent(parent)
    pop.connect("closed", lambda p: GLib.idle_add(p.unparent))
    pop.popup()
    return pop


class Picker(Adw.Dialog):
    """on_pick(kind, value): kind "model" with a model key, or "pool" with a pool name."""

    def __init__(self, routes: Routes, models: list[ModelInfo], on_pick: Callable[[str, str], None],
                 pools: bool = True, title: str = "", user_pools: dict[str, dict] | None = None,
                 on_pools: Callable[[str | None, str | None], None] | None = None):
        """user_pools: the user's saved pools, edited in place; on_pools(old, new) after one is made, renamed
        (old and new), or deleted (new None), so the caller saves them and moves seats along."""
        super().__init__(title=title or _("Choose a model"), content_width=680, content_height=680)
        self.routes, self.on_pick, self.flt = routes, on_pick, "all"
        self.models, self.user_pools, self.on_pools = models, user_pools, on_pools
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        self.search = Gtk.SearchEntry(placeholder_text=_("Search models"), hexpand=True)
        self.search.connect("search-changed", lambda *_a: self.list.invalidate_filter())
        self.chips = chips = Adw.ToggleGroup()
        for name, text in FILTERS:
            chips.add(Adw.Toggle(name=name, label=_(text)))
        chips.set_active_name("all")
        chips.connect("notify::active-name", self._chip)
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=16, margin_end=16, margin_bottom=8)
        top.append(self.search)
        sc_chips = Gtk.ScrolledWindow(vscrollbar_policy=Gtk.PolicyType.NEVER, child=chips)
        top.append(sc_chips)
        view.add_top_bar(top)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, margin_start=16, margin_end=16,
                       margin_top=6, margin_bottom=16)
        if pools:
            self.pool_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            self.pool_list.add_css_class("boxed-list")
            self._fill_pools()
            body.append(label(_("Random"), "section-title"))
            body.append(self.pool_list)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.set_filter_func(self._keep)
        for m in sorted(models, key=lambda m: (bool(why_not(routes, m)), not m.free, rank(m), m.name.lower())):
            self.list.append(self._row(m))
        if not models:
            self.list.append(Adw.ActionRow(title=_("No models yet"), subtitle=_("Check the connections in Settings")))
        body.append(label(_("Models"), "section-title"))
        body.append(self.list)
        clamp = Adw.Clamp(maximum_size=760, child=body)
        sc = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=clamp)
        view.set_content(sc)
        self.set_child(view)
        self.search.grab_focus()

    def shown_rows(self) -> list[str]:
        """The titles of the model rows the filter and search keep, in order (checks and shots)."""
        out, row = [], self.list.get_first_child()
        while row is not None:
            if getattr(row, "m", None) is not None and self._keep(row):
                out.append(row.get_title())
            row = row.get_next_sibling()
        return out

    def _row(self, m: ModelInfo) -> Gtk.ListBoxRow:
        reason = why_not(self.routes, m)
        row = Adw.ActionRow(title=m.name, subtitle=reason or place_text(m), activatable=not reason)
        row.set_title_lines(1)
        row.m, row.reason = m, reason
        row.tag = tag = label(price_text(m), "price")
        tag.set_valign(Gtk.Align.CENTER)
        if m.trains:
            row.add_suffix(label(_("Trains"), "badge"))
        if m.status and m.status not in ("가격 모름",) and not reason and m.ref.route == "lmstudio":
            row.add_suffix(label(_("Loads on call") if m.status == "부를 때 올림" else m.status, "meta"))
        row.add_suffix(tag)
        row.set_sensitive(not reason)
        row.connect("activated", lambda *_a: self._pick_model(m))
        return row

    def _keep(self, row: Gtk.ListBoxRow) -> bool:
        m = getattr(row, "m", None)
        if m is None:
            return True
        return kept(self.routes, m, self.flt, self.search.get_text())

    def _chip(self, group: Adw.ToggleGroup, _p: object) -> None:
        """Under a route chip each row shows that route's own model: its name, route and price."""
        self.flt = group.get_active_name() or "all"
        row = self.list.get_first_child()
        while row is not None:
            m = getattr(row, "m", None)
            if m is not None:
                key = route_key(m, self.flt) if self.flt not in ("all", "free") else None
                own = (self.routes.info(key) if key else None) or m
                row.set_title(own.name)
                row.set_subtitle(row.reason or place_text(own))
                row.tag.set_label(price_text(own))
            row = row.get_next_sibling()
        self.list.invalidate_filter()

    def _pick_model(self, m: ModelInfo) -> None:
        """Under a route chip the seat takes that route; otherwise the entry's chosen route."""
        key = route_key(m, self.flt) if self.flt not in ("all", "free") else None
        self.on_pick("model", key or m.key)
        self.close()

    def _fill_pools(self) -> None:
        """Built-in pools, then the user's own with an edit button, then a row to make one."""
        from ..pools import USER, pool_models
        lst = self.pool_list
        while (child := lst.get_first_child()) is not None:
            lst.remove(child)
        for name, text in POOLS:
            n = len(pool_models(self.models, name, self.routes.usable))
            row = Adw.ActionRow(title=_(text), subtitle=_("{n} models now").format(n=n), activatable=n > 0)
            row.add_prefix(Gtk.Image.new_from_icon_name("media-playlist-shuffle-symbolic"))
            row.connect("activated", self._pick_pool, name)
            lst.append(row)
        if self.user_pools is None:
            return
        for name, d in self.user_pools.items():
            n = len(pool_models(self.models, "user", self.routes.usable, d))
            row = Adw.ActionRow(title=name, subtitle=_("My pool, {n} models now").format(n=n), activatable=n > 0)
            row.add_prefix(Gtk.Image.new_from_icon_name("media-playlist-shuffle-symbolic"))
            edit = Gtk.Button(icon_name="document-edit-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Edit"))
            edit.add_css_class("flat")
            edit.connect("clicked", lambda *_a, name=name: self._edit_pool(name))
            row.add_suffix(edit)
            row.connect("activated", self._pick_pool, USER + name)
            lst.append(row)
        new = Adw.ActionRow(title=_("New pool"), subtitle=_("Filters plus models you put in or leave out"), activatable=True)
        new.add_prefix(Gtk.Image.new_from_icon_name("list-add-symbolic"))
        new.connect("activated", lambda *_a: self._edit_pool(None))
        lst.append(new)

    def _edit_pool(self, name: str | None) -> None:
        from .pool_edit import PoolEditor

        def done(new: str | None) -> None:
            if self.on_pools is not None:
                self.on_pools(name, new)
            self._fill_pools()
        PoolEditor(self.routes, self.models, self.user_pools if self.user_pools is not None else {}, name, done).present(self)

    def _pick_pool(self, _row: Adw.ActionRow, name: str) -> None:
        self.on_pick("pool", name)
        self.close()
