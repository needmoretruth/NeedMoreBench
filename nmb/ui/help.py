"""도움말: one dialog with four parts, opened from the main menu, and from the ? of the powers popover
straight at the powers. The words live in nmb.help; this file only lays them out."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import help as text  # noqa: E402
from ..engine import god  # noqa: E402
from ..engine.roles import ROLES, TEAM_EN  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import power_label, role_label, team_class  # noqa: E402
from .widgets import chip, label, vbox  # noqa: E402

GAME_EN = {"simple": "Simple mafia", "complex": "Complex mafia, the other roles"}


def _page(*children: Gtk.Widget) -> Gtk.Widget:
    body = vbox(18, *children)
    for m in ("top", "bottom", "start", "end"):
        getattr(body, f"set_margin_{m}")(18)
    return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                              child=Adw.Clamp(maximum_size=760, child=body))


def _group(title: str, rows: list[Gtk.Widget], description: str = "") -> Adw.PreferencesGroup:
    g = Adw.PreferencesGroup(title=title, description=description)
    for r in rows:
        g.add(r)
    return g


def _plain(title: str, body: str) -> Adw.ActionRow:
    row = Adw.ActionRow(title=title, subtitle=body)
    row.set_subtitle_lines(0)
    row.add_css_class("help-row")
    return row


def _power_row(power: str, fields: tuple[str, str, str, str, str]) -> Adw.ExpanderRow:
    row = Adw.ExpanderRow(title=power_label(power), subtitle=fields[0])
    row.set_subtitle_lines(0)
    row.add_css_class("help-power")
    for name, body in zip(text.FIELDS[1:], fields[1:]):
        r = Adw.ActionRow(title=_(name), subtitle=body)
        r.set_subtitle_lines(0)
        r.add_css_class("property")
        row.add_row(r)
    return row


def _role_row(role: str) -> Adw.ActionRow:
    row = _plain(role_label(role), text.role_text(role))
    team = ROLES[role].team
    c = chip(_(TEAM_EN.get(team, team)), team_class(role))
    c.set_valign(Gtk.Align.CENTER)
    row.add_suffix(c)
    return row


class HelpDialog(Adw.Dialog):
    def __init__(self, section: str = "flow"):
        super().__init__(title=_("Help"), content_width=760, content_height=680)
        self.stack = Adw.ViewStack()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        view.set_content(self.stack)
        self.set_child(view)

        flow = _page(_group(_("How a game goes"), [_plain(t, b) for t, b in text.flow()]))
        self.stack.add_titled_with_icon(flow, "flow", _("Game"), "media-playlist-repeat-symbolic")

        roles = [_group(_(GAME_EN[game]), [_role_row(r) for r in rs]) for game, rs in text.roles_by_game()]
        self.stack.add_titled_with_icon(_page(*roles), "roles", _("Roles"), "system-users-symbolic")

        watch = _page(_group(_("Watching and cheats"), [_plain(t, b) for t, b in text.watching()]))
        self.stack.add_titled_with_icon(watch, "watching", _("Watching"), "view-reveal-symbolic")

        intro = label(text.power_intro(), "help-intro", wrap=True, xalign=0)
        groups = [_group(_(god.GROUP_EN[name]), [_power_row(p, f) for p, f in entries])
                  for name, entries in text.power_entries()]
        self.stack.add_titled_with_icon(_page(intro, *groups), "powers", _("God powers"), "weather-clear-symbolic")
        self.stack.set_visible_child_name(section)


def open_help(widget: Gtk.Widget, section: str = "flow") -> HelpDialog:
    dlg = HelpDialog(section)
    dlg.present(widget)
    return dlg
