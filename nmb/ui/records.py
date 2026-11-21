"""기록: saved games to replay, play again or export, and the standings."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from ..store import Saved, export_game, import_file, list_games  # noqa: E402
from .widgets import chip, vbox  # noqa: E402

GAME_EN = {"simple": "Simple mafia", "complex": "Complex mafia"}
TEAM_EN = {"시민": "Citizens won", "마피아": "Mafia won", "교주": "Cult won"}


def when(saved: Saved) -> str:
    try:
        t = dt.datetime.fromisoformat(saved.header.get("created", "")).astimezone()
    except ValueError:
        return ""
    return t.strftime("%Y-%m-%d %H:%M")


def outcome(saved: Saved) -> str:
    r = saved.result
    if r is None:
        return _("Playing") if saved.live else _("Stopped")
    return _(TEAM_EN.get(r.get("team") or "", "Draw"))


def players_line(saved: Saved) -> str:
    named = saved.settings.get("named", True)
    names = []
    for s in saved.header.get("seats", []):
        if s.get("kind") == "human":
            names.append(_("You"))
        else:
            names.append(s.get("name") if named else s.get("model_name") or s.get("name"))
    return ", ".join(n for n in names if n)


class RecordsPage(Adw.NavigationPage):
    def __init__(self, app: Any):
        super().__init__(title=_("Records"), tag="records")
        self.app = app
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(switcher)
        imp = Gtk.Button(icon_name="document-open-symbolic", tooltip_text=_("Import a record"))
        imp.connect("clicked", lambda *_a: self._import())
        header.pack_end(imp)
        view.add_top_bar(header)

        self.search = Gtk.SearchEntry(placeholder_text=_("Search by model, name or result"))
        self.search.connect("search-changed", lambda *_a: self.list.invalidate_filter())
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self.list.add_css_class("boxed-list")
        self.list.set_filter_func(self._keep)
        self.empty = Adw.StatusPage(icon_name="document-open-recent-symbolic", title=_("No games yet"),
                                    description=_("Finished and stopped games show up here."))
        body = vbox(12, self.search, self.list)
        body.set_margin_top(18)
        body.set_margin_bottom(24)
        body.set_margin_start(16)
        body.set_margin_end(16)
        games = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                   child=Adw.Clamp(maximum_size=900, child=body))
        self.games_stack = Gtk.Stack()
        self.games_stack.add_named(games, "list")
        self.games_stack.add_named(self.empty, "empty")
        self.stack.add_titled_with_icon(self.games_stack, "games", _("Games"), "view-list-symbolic")
        if getattr(app, "standings_ready", False):
            from .standings import Standings
            self.stack.add_titled_with_icon(Standings(app), "standings", _("Standings"), "view-sort-descending-symbolic")
        view.set_content(self.stack)
        self.set_child(view)
        self.connect("showing", lambda *_a: self.reload())

    def reload(self) -> None:
        child = self.list.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self.list.remove(child)
            child = nxt
        games = list_games()
        for s in games:
            self.list.append(self._row(s))
        self.games_stack.set_visible_child_name("list" if games else "empty")

    def _row(self, s: Saved) -> Gtk.ListBoxRow:
        title = f"{_(GAME_EN.get(s.header.get('game', ''), 'Mafia'))}, {outcome(s)}"
        r = s.result or {}
        bits = [when(s), _("{n} players").format(n=len(s.header.get("seats", [])))]
        if r.get("day"):
            bits.append(_("to day {n}").format(n=r["day"]))
        if not s.settings.get("named", True):
            bits.append(_("Blind"))
        row = Adw.ActionRow(title=title, subtitle=", ".join(bits) + "\n" + players_line(s), activatable=True)
        row.set_subtitle_lines(2)
        row.saved = s
        row.text = (title + " " + players_line(s) + " " + " ".join(x.get("model_name") or "" for x in s.header.get("seats", []))).lower()
        row.connect("activated", lambda *_a: self._open(s))
        if s.intervened:  # the god changed this game; it does not count in the standings
            row.add_suffix(chip(_("God intervened"), "god"))
            row.set_tooltip_text(_("The god used powers in this game, so it is left out of the standings."))
            row.text += " " + _("God intervened").lower()
        row.add_suffix(self._export_button(s))
        again = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Play again"), valign=Gtk.Align.CENTER)
        again.add_css_class("flat")
        again.connect("clicked", lambda *_a: self._again(s))
        row.add_suffix(again)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        return row

    def _keep(self, row: Gtk.ListBoxRow) -> bool:
        q = self.search.get_text().strip().lower()
        return not q or q in getattr(row, "text", "")

    def _open(self, s: Saved) -> None:
        from .replay import Replay
        r = Replay(s, on_sound=self.app.play_sound, on_again=lambda: self._again(s))
        r.page.add_sound_button(self.app.sound.button())
        self.app.window.push(r.page)

    def _again(self, s: Saved) -> None:
        """같은 설정으로 다시 from a saved game: its settings with 랜덤 seats drawn again."""
        from ..engine.setup import GameSetup
        from .launch import start_game
        self.app.window.nav.pop_to_tag("home")
        start_game(self.app, GameSetup.from_json(s.settings).again())

    def _export_button(self, s: Saved) -> Gtk.MenuButton:
        """내보내기: the record file, and a Markdown copy only when asked (off by default)."""
        md = Gtk.CheckButton(label=_("Markdown copy too"))
        go = Gtk.Button(label=_("Export to a folder"))
        go.add_css_class("suggested-action")
        box = vbox(8, md, go)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(8)
        pop = Gtk.Popover(child=box)
        go.connect("clicked", lambda *_a: (pop.popdown(), self._export(s, md.get_active())))
        btn = Gtk.MenuButton(icon_name="document-save-symbolic", tooltip_text=_("Export"), valign=Gtk.Align.CENTER,
                             popover=pop)
        btn.add_css_class("flat")
        return btn

    def _export(self, s: Saved, markdown: bool = False) -> None:
        dlg = Gtk.FileDialog(title=_("Export to a folder"))

        def done(d: Gtk.FileDialog, res: Gio.AsyncResult) -> None:
            try:
                folder = d.select_folder_finish(res)
            except GLib.Error:
                return
            if folder is None or folder.get_path() is None:
                return
            paths = export_game(s, Path(folder.get_path()), markdown=markdown)
            self.app.window.toast(_("Saved {name}").format(name=paths[0].name))
        dlg.select_folder(self.app.window, None, done)

    def _import(self) -> None:
        dlg = Gtk.FileDialog(title=_("Import a record"))
        f = Gtk.FileFilter()
        f.set_name(_("NeedMoreBench records"))
        f.add_pattern("*.nmb.jsonl")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        dlg.set_filters(filters)

        def done(d: Gtk.FileDialog, res: Gio.AsyncResult) -> None:
            try:
                file = d.open_finish(res)
            except GLib.Error:
                return
            if file is None or file.get_path() is None:
                return
            try:
                import_file(Path(file.get_path()))
            except (OSError, ValueError) as e:
                self.app.window.toast(str(e))
                return
            self.reload()
        dlg.open(self.app.window, None, done)

