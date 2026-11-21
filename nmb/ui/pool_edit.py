"""내 풀: a named pool a 랜덤 seat draws from, made of filters (무료만, 계열별 최신판만, route,
maker) plus models put in or taken out by hand. The 학습 모델 허용 switch and LM Studio's by-hand rule always apply."""
from __future__ import annotations

import copy
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from ..pools import automatic, pool_models  # noqa: E402
from ..providers.base import ModelInfo  # noqa: E402
from ..providers.merge import keys_of  # noqa: E402
from ..providers.registry import Routes  # noqa: E402
from .widgets import label  # noqa: E402

ROUTES = [("opencode", "OpenCode"), ("anthropic", "Anthropic"), ("venice", "Venice"), ("openrouter", "OpenRouter")]


def empty_pool() -> dict[str, Any]:
    return {"filters": {"free": False, "latest": False, "route": [], "maker": []}, "include": [], "exclude": []}


class PoolEditor(Adw.Dialog):
    """on_done(name or None): called after a save (the name) or a delete (None)."""

    def __init__(self, routes: Routes, models: list[ModelInfo], pools: dict[str, dict], name: str | None,
                 on_done: Callable[[str | None], None]):
        super().__init__(title=_("My pool") if name is None else name, content_width=620, content_height=760)
        self.routes, self.models, self.pools, self.old, self.on_done = routes, models, pools, name, on_done
        self.d = copy.deepcopy(pools.get(name or "", empty_pool()))
        f = self.d.setdefault("filters", {})
        for k in ("route", "maker"):
            f.setdefault(k, [])
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        page = Adw.PreferencesPage()

        g = Adw.PreferencesGroup()
        self.name = Adw.EntryRow(title=_("Name"), text=name or "")
        self.name.connect("changed", lambda *_a: self._update())
        self.free = Adw.SwitchRow(title=_("Free only"), active=bool(f.get("free")))
        self.free.connect("notify::active", lambda r, _p: self._flag("free", r.get_active()))
        self.latest = Adw.SwitchRow(title=_("Latest of each line only"), subtitle=_("With Opus 5.5 there, Opus 5 is left out"),
                                    active=bool(f.get("latest")))
        self.latest.connect("notify::active", lambda r, _p: self._flag("latest", r.get_active()))
        for w in (self.name, self.free, self.latest):
            g.add(w)
        page.add(g)

        g = Adw.PreferencesGroup(title=_("Filters"), description=_("None chosen means all"))
        self.route_row = Adw.ExpanderRow(title=_("Route"))
        for rid, text in ROUTES:
            sw = Adw.SwitchRow(title=text, active=rid in f["route"])
            sw.connect("notify::active", lambda r, _p, rid=rid: self._toggle("route", rid, r.get_active()))
            self.route_row.add_row(sw)
        self.maker_row = Adw.ExpanderRow(title=_("Maker"))
        counts: dict[str, int] = {}
        for m in models:
            if automatic(m) and m.maker:
                counts[m.maker] = counts.get(m.maker, 0) + 1
        for maker in sorted(counts, key=lambda k: (-counts[k], k.lower())):
            sw = Adw.SwitchRow(title=maker, subtitle=_("{n} models").format(n=counts[maker]), active=maker in f["maker"])
            sw.connect("notify::active", lambda r, _p, mk=maker: self._toggle("maker", mk, r.get_active()))
            self.maker_row.add_row(sw)
        g.add(self.route_row)
        g.add(self.maker_row)
        page.add(g)

        self.list = Adw.PreferencesGroup(title=_("Models in the pool"))
        add = Gtk.Button(child=Adw.ButtonContent(icon_name="list-add-symbolic", label=_("Add")), valign=Gtk.Align.CENTER)
        add.connect("clicked", lambda *_a: self._add())
        self.list.set_header_suffix(add)
        self.rows: list[Gtk.Widget] = []
        page.add(self.list)
        view.set_content(page)

        self.delete = Gtk.Button(label=_("Delete"), visible=name is not None)
        self.delete.add_css_class("destructive-action")
        self.delete.connect("clicked", lambda *_a: self._delete())
        self.problem = label("", "error")
        self.save = Gtk.Button(label=_("Save"))
        self.save.add_css_class("pill")
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", lambda *_a: self._save())
        bar = Gtk.Box(spacing=12)
        bar.add_css_class("start-bar")
        spacer = Gtk.Box(hexpand=True)
        for w in (self.delete, spacer, self.problem, self.save):
            bar.append(w)
        view.add_bottom_bar(bar)
        self.set_child(view)
        self._update()

    # ---- editing ----------------------------------------------------------------------------------------------
    def _flag(self, key: str, on: bool) -> None:
        self.d["filters"][key] = on
        self._update()

    def _toggle(self, key: str, value: str, on: bool) -> None:
        lst = self.d["filters"][key]
        if on and value not in lst:
            lst.append(value)
        elif not on and value in lst:
            lst.remove(value)
        self._update()

    def _drop(self, m: ModelInfo) -> None:
        keys = keys_of(m)
        self.d["include"] = [k for k in self.d.get("include", []) if k not in keys]
        if m.key not in self.d.setdefault("exclude", []):
            self.d["exclude"].append(m.key)
        self._update()

    def _add(self) -> None:
        from .picker import Picker

        def got(_kind: str, key: str) -> None:
            e = self.routes.entry(key)
            keys = keys_of(e) if e is not None else [key]
            self.d["exclude"] = [k for k in self.d.get("exclude", []) if k not in keys]
            if not set(keys) & set(self.d.setdefault("include", [])):
                self.d["include"].append(key)
            self._update()
        Picker(self.routes, self.models, got, pools=False, title=_("Add a model")).present(self)

    def members(self) -> list[ModelInfo]:
        return pool_models(self.models, "user", self.routes.usable, self.d)

    def _update(self) -> None:
        f = self.d["filters"]
        self.route_row.set_subtitle(", ".join(t for r, t in ROUTES if r in f["route"]) or _("All"))
        self.maker_row.set_subtitle(", ".join(f["maker"]) or _("All"))
        for r in self.rows:
            self.list.remove(r)
        self.rows = []
        ms = self.members()
        self.list.set_description(_("{n} models now").format(n=len(ms)))
        for m in sorted(ms, key=lambda m: (m.maker or "", m.name.lower())):
            row = Adw.ActionRow(title=m.name, subtitle=", ".join(x for x in (m.maker, _("Free") if m.free else "") if x))
            rm = Gtk.Button(icon_name="list-remove-symbolic", valign=Gtk.Align.CENTER, tooltip_text=_("Leave out"))
            rm.add_css_class("flat")
            rm.connect("clicked", lambda *_a, m=m: self._drop(m))
            row.add_suffix(rm)
            self.list.add(row)
            self.rows.append(row)
        out = [self.routes.entry(k) for k in self.d.get("exclude", [])]
        out_rows = [e for e in out if e is not None]
        if out_rows:
            exp = Adw.ExpanderRow(title=_("Left out by hand"), subtitle=str(len(out_rows)))
            for e in out_rows:
                r = Adw.ActionRow(title=e.name)
                back = Gtk.Button(label=_("Put back"), valign=Gtk.Align.CENTER)
                back.add_css_class("flat")
                back.connect("clicked", lambda *_a, e=e: self._put_back(e))
                r.add_suffix(back)
                exp.add_row(r)
            self.list.add(exp)
            self.rows.append(exp)
        msg = self._problem()
        self.problem.set_label(msg)
        self.save.set_sensitive(not msg)

    def _put_back(self, e: ModelInfo) -> None:
        keys = keys_of(e)
        self.d["exclude"] = [k for k in self.d.get("exclude", []) if k not in keys]
        self._update()

    def _problem(self) -> str:
        name = self.name.get_text().strip()
        if not name:
            return _("Give it a name")
        if name != self.old and name in self.pools:
            return _("A pool with this name exists")
        if not self.members():
            return _("No model in the pool now")
        return ""

    def _save(self) -> None:
        name = self.name.get_text().strip()
        if self.old is not None and self.old != name:
            self.pools.pop(self.old, None)
        self.pools[name] = self.d
        self.on_done(name)
        self.close()

    def _delete(self) -> None:
        if self.old is not None:
            self.pools.pop(self.old, None)
        self.on_done(None)
        self.close()
