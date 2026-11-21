"""End screen: who won and why, every role, the models (revealed in blind games too), one line of
numbers per player, 다시 하기 and where the game was saved. Shown over the game page when a live game or a replay
reaches its end, and again from the header's result button."""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from ..view import ViewState, role_label, team_class  # noqa: E402
from .widgets import avatar, chip, hbox, label, vbox  # noqa: E402

TEAM_WON = {"시민": "Citizens win", "마피아": "Mafia wins", "교주": "Cult wins"}


def player_line(p: dict[str, Any]) -> str:
    """Survived or the day of death, then votes on the other team and right role guesses."""
    if p.get("alive"):
        bits = [_("Survived")]
    else:
        bits = [_("Died on day {n}").format(n=p["died_day"]) if p.get("died_day") else _("Died")]
    if p.get("votes"):
        bits.append(_("Votes on the other team {a}/{b}").format(a=p.get("votes_right", 0), b=p["votes"]))
    if p.get("guesses"):
        bits.append(_("Role guesses {a}/{b}").format(a=p.get("guesses_right", 0), b=p["guesses"]))
    return ", ".join(bits)


def end_view(header: dict[str, Any], result: dict[str, Any], stats: list[dict[str, Any]] | None,
             roles: dict[int, str] | None = None) -> tuple[ViewState, dict[int, dict[str, Any]]]:
    """The seats with models shown (blind games reveal them here) and each seat's numbers."""
    st = ViewState.from_header(header, viewer=None, reveal_models=True)
    for seat, role in (roles or {}).items():
        if 0 <= seat < len(st.seats):
            st.seats[seat].role = role
    for k, role in (result.get("roles") or {}).items():
        if 0 <= int(k) < len(st.seats):
            st.seats[int(k)].role = role
    by_seat = {int(p["seat"]): p for p in (stats or result.get("players") or [])}
    return st, by_seat


class EndDialog(Adw.Dialog):
    def __init__(self, header: dict[str, Any], result: dict[str, Any], stats: list[dict[str, Any]] | None,
                 roles: dict[int, str] | None = None, on_again: Callable[[], None] | None = None,
                 on_records: Callable[[], None] | None = None, human_seat: int | None = None):
        super().__init__(title=_("Game over"), content_width=600, content_height=720)
        self.add_css_class("end-dialog")
        st, by_seat = end_view(header, result, stats, roles)
        winners = set(result.get("winners") or [])
        team = result.get("team")

        head = vbox(4)
        head.add_css_class("end-head")
        head.add_css_class(team_class("마피아" if team == "마피아" else "시민") if team else "plain")
        title = _(TEAM_WON[team]) if team in TEAM_WON else _("Stopped") if result.get("stopped") else _("Draw")
        facts = [result.get("reason") or "", _("to day {n}").format(n=result["day"]) if result.get("day") else ""]
        if human_seat is not None and team:  # the person's own result is the headline, the team's goes below
            facts.insert(0, title)
            title = _("You win") if human_seat in winners else _("You lose")
            if human_seat not in winners:  # team colour stays on the winners' side; a loss reads plain
                for c in ("mafia", "town"):
                    head.remove_css_class(c)
        head.append(label(title, "title-1", wrap=True))
        facts = [x for x in facts if x]
        head.append(label(", ".join(facts), "dim-label", wrap=True))

        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        order = sorted(st.seats, key=lambda v: (v.seat not in winners, v.seat))
        for v in order:
            p = by_seat.get(v.seat, {})
            row = Adw.ActionRow(title=v.name, subtitle=v.model_line or "", use_markup=False)
            row.set_subtitle_lines(1)
            row.add_prefix(avatar(v.name, 40))
            side = vbox(4)
            side.set_valign(Gtk.Align.CENTER)
            top = hbox(6)
            top.set_halign(Gtk.Align.END)
            if v.seat in winners:
                top.append(chip(_("Win"), "win"))
            top.append(chip(role_label(v.role), team_class(v.role)))
            side.append(top)
            if p:
                numbers = label(player_line(p), "meta", xalign=1.0)
                side.append(numbers)
            row.add_suffix(side)
            if not (p.get("alive", v.alive)):
                row.add_css_class("dead")
            rows.append(row)

        again = Gtk.Button(label=_("Play again"))
        again.add_css_class("pill")
        again.add_css_class("suggested-action")
        again.set_visible(on_again is not None)
        again.connect("clicked", lambda *_a: (self.close(), on_again and on_again()))
        look = Gtk.Button(label=_("Back to the game"))
        look.add_css_class("pill")
        look.connect("clicked", lambda *_a: self.close())
        buttons = hbox(10, look, again)
        buttons.set_halign(Gtk.Align.CENTER)

        body = vbox(16, head, rows)
        if on_records is not None:
            saved = Gtk.Button(label=_("Saved to records"))
            saved.add_css_class("flat")
            saved.add_css_class("saved-link")
            saved.set_halign(Gtk.Align.CENTER)
            saved.set_tooltip_text(_("Open records"))
            saved.connect("clicked", lambda *_a: (self.close(), on_records()))
            body.append(saved)
        for m in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{m}")(20)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True,
                                    child=Adw.Clamp(maximum_size=640, child=body))
        view = Adw.ToolbarView()
        view.add_top_bar(Adw.HeaderBar())
        view.set_content(scroll)
        bottom = vbox(0, buttons)
        bottom.add_css_class("end-actions")
        view.add_bottom_bar(bottom)
        self.set_child(view)
