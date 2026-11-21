"""The lobby's 직업 구성: 기본 or 직접 in 단순 마피아; 랜덤, 정해진 구성 or 직접 in 복잡한 마피아.

직접 shows every role of the game with a stepper: any count of any role (1 마피아 and 9 경찰 is a lineup), 연인 by
pairs, 시민 filling the rest. Under it the mafia side's expected win chance from NMB's own games, shown once
30 games of that type are recorded (before, the prior alone would read like a fact). A lineup that cannot
be played is said on the start button (`GameSetup.problem`).
"""
from __future__ import annotations

from collections import Counter
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from ..engine.lineups import CUSTOM, NAMED, NAMED_LINEUPS, RANDOM, by_counts, counted_lineup, mode_of, with_cult  # noqa: E402
from ..engine.roles import (COMPLEX, COMPLEX_SLOTS, CULT, CULT_FROM, GAME_ROLES, MAFIA, ROLES, SIMPLE, TOWN,  # noqa: E402
                            simple_lineup)
from ..engine.pins import Fit, cover_pins, fit_table, set_count  # noqa: E402
from ..engine.setup import playable  # noqa: E402
from ..i18n import _, counted  # noqa: E402
from ..view import role_label  # noqa: E402
from .widgets import hbox, label, vbox  # noqa: E402


def roles_now(page: Any) -> list[str] | None:
    """The lineup the lobby would deal now, or None when it is drawn at the start (랜덤)."""
    s = page.full_setup()
    n = len(s.seats)
    if by_counts(s):
        return counted_lineup(s.counts, n, [x.role for x in s.seats if x.role])
    if s.kind == SIMPLE:
        return [r for r, c in simple_lineup(n).items() for _i in range(c)]
    if mode_of(s) == NAMED and n in NAMED_LINEUPS:
        return list(NAMED_LINEUPS[n])
    return None


def fit(page: Any, stepper: tuple[str, int] | None = None, fresh: bool = False, seat: Any = None) -> bool:
    """Keep the lineup and the seats' roles one model (AL1, engine/pins.py). The newest action wins: a stepper
    (`stepper`), else the seats' roles (`seat`: the one just set, which stays). Says what gave way on the lineup's
    note; True when seats or counts changed. `fresh`: this call is the person's newest action, so an older note
    goes even when nothing gave way."""
    s = page.full_setup()
    seats = ([page.human] if page.mode == "play" else []) + list(page.setup.seats)
    pins = [x.role for x in s.seats]
    n = len(pins)
    keep = next((i for i, x in enumerate(seats) if x is seat), None)
    if not by_counts(s):  # 기본 and 정해진 구성: a fixed table, seats beyond it give way
        table = simple_lineup(n) if s.kind == SIMPLE else (
            dict(Counter(NAMED_LINEUPS[n])) if mode_of(s) == NAMED and n in NAMED_LINEUPS else None)
        f = Fit(dict(s.counts), fit_table(table, (n - 1) // 2, pins, keep))
    else:
        f = set_count(s.counts, n, pins, *stepper) if stepper else cover_pins(s.counts, n, pins)
    for i in f.unpin:
        seats[i].role = None
    page.setup.counts = f.counts
    if not f.nothing or fresh or stepper:
        page.lineup_note = _note(f, stepper)
    return not f.nothing


def _note(f: Any, stepper: tuple[str, int] | None) -> str:
    counts = ", ".join(f"{role_label(r)} {a} → {b}" for r, a, b in f.changed if not stepper or r != stepper[0])
    if f.unpin and counts:
        return counts_unpinned(len(f.unpin), counts)
    if f.unpin:
        return counted(len(f.unpin), "{n} seat's role went back to random",
                       "{n} seats' roles went back to random")
    if counts:
        return (_("Other counts gave way: {counts}") if stepper else _("Counts follow the roles set on seats: {counts}")
                ).format(counts=counts)
    return ""


def counts_unpinned(n: int, counts: str) -> str:
    return counted(n, "{n} seat's role went back to random; counts moved: {counts}",
                   "{n} seats' roles went back to random; counts moved: {counts}", counts=counts)


def chance_text(full: Any, roles: list[str] | None, folder: Any = None) -> tuple[str, str, bool]:
    """(value, subtitle, sure) of the mafia win chance row. Below 30 recorded games of this type the number would be
    the prior alone (the 복잡 table read 66~77 % with no game recorded), so the row says the games are coming."""
    from ..balance import ENOUGH, drawn_estimate, model
    m = model(full.kind, folder)
    if m.games < ENOUGH:
        return _("{n}/{all} games").format(n=m.games, all=ENOUGH), _("Shows once games are recorded"), False
    est = m.estimate(roles) if roles is not None else drawn_estimate(full, folder)
    bounds = {"lo": round(est.lo * 100), "hi": round(est.hi * 100)}
    if roles is None:  # 랜덤: the mean over draws made as the start makes them
        words = counted(est.games, "Average of random draws, range {lo}~{hi}%, from {n} game",
                        "Average of random draws, range {lo}~{hi}%, from {n} games", **bounds)
    else:
        words = counted(est.games, "Range {lo}~{hi}%, from {n} game", "Range {lo}~{hi}%, from {n} games", **bounds)
    return f"{est.p:.0%}", words, True


def numbers(page: Any) -> Gtk.Widget:
    """The strip on top: players and the main counts of the lineup."""
    n = page.count
    roles = roles_now(page)
    if page.setup.kind == SIMPLE and roles is not None:
        c = Counter(roles)
        items = [(n, _("Players"))] + [(c[r], role_label(r)) for r in ("마피아", "경찰", "의사", "시민")]
    elif roles is not None:
        mafia = sum(1 for r in roles if ROLES[r].team == MAFIA)
        items = [(n, _("Players")), (roles.count("마피아"), role_label("마피아")), (mafia - roles.count("마피아"), _("Helpers")),
                 (sum(1 for r in roles if ROLES[r].team != MAFIA and r != "시민"), _("Other roles")), (roles.count("시민"), role_label("시민"))]
    else:
        sl = COMPLEX_SLOTS[n]
        cult = sum(1 for r, k in CULT_FROM.items() if n >= k) if with_cult(page.setup, n) else 0
        items = [(n, _("Players")), (sl[0], role_label("마피아")), (sl[1], _("Helpers")), (sl[2] + sl[3], _("Police, doctor")),
                 (sl[4] + sl[5] - cult, _("Others"))] + ([(cult, _("Cult team"))] if cult else [])
    box = hbox(10)
    box.add_css_class("lobby-numbers")
    box.set_homogeneous(True)
    for value, text in items:
        cell = vbox(0, label(str(value), "value", xalign=0.5), label(text, "label", xalign=0.5))
        cell.add_css_class("lobby-number")
        box.append(cell)
    return box


class LineupGroup:
    def __init__(self, page: Any):
        self.page = page
        s = page.setup
        modes = [(NAMED, _("Standard")), (CUSTOM, _("Custom"))] if s.kind == SIMPLE else \
            [(RANDOM, _("Random")), (NAMED, _("Set lineup")), (CUSTOM, _("Custom"))]
        mode = Adw.ActionRow(title=_("How"), subtitle=self._mode_words(mode_of(s)))
        g = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        for name, text in modes:
            g.add(Adw.Toggle(name=name, label=text))
        g.set_active_name(mode_of(s))
        g.connect("notify::active-name", lambda w, _p: self._mode(w.get_active_name()))
        mode.add_suffix(g)
        lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        lb.add_css_class("boxed-list")
        lb.append(mode)
        self.citizens: Adw.ActionRow | None = None
        self.folds: dict[str, Adw.ExpanderRow] = {}
        if by_counts(page.full_setup()):
            self._steppers(lb)
        if s.kind == COMPLEX and mode_of(s) == RANDOM:
            self._random_rows(lb)
        self.chance = Adw.ActionRow(title=_("Mafia win chance"))
        self.chance_value = label("", "chance-value")
        self.chance.add_suffix(self.chance_value)
        lb.append(self.chance)
        self.box = vbox(8, label(_("Roles"), "heading"), lb)
        self.refresh()

    @staticmethod
    def _mode_words(mode: str) -> str:
        return {RANDOM: _("Drawn per kind of seat"), NAMED: _("The same lineup every game, known to all"),
                CUSTOM: _("Any number of any role; citizens fill the rest")}[mode]

    def _random_rows(self, lb: Gtk.ListBox) -> None:
        """랜덤's 직업 풀 (classic or full) and the 교주팀 switch (from 9 players)."""
        s = self.page.setup
        pool = Adw.ActionRow(title=_("Role pool"), subtitle=_("Which roles can be drawn"))
        g = Adw.ToggleGroup(valign=Gtk.Align.CENTER)
        for name, text in (("classic", _("Classic")), ("full", _("Full"))):
            g.add(Adw.Toggle(name=name, label=text))
        g.set_active_name(s.role_pool if s.role_pool in ("classic", "full") else "classic")
        g.connect("notify::active-name", lambda w, _p: self._set(role_pool=w.get_active_name() or "classic"))
        pool.add_suffix(g)
        lb.append(pool)
        enough = self.page.count >= CULT_FROM["교주"]
        cult = Adw.SwitchRow(title=_("Cult team"), active=s.cult and enough, sensitive=enough,
                             subtitle=_("A cult leader converts players at night") if enough else _("9 players or more"))
        cult.connect("notify::active", lambda w, _p: self._set(cult=w.get_active()))
        lb.append(cult)

    def _set(self, **kw: Any) -> None:
        s = self.page.setup
        if all(getattr(s, k) == v for k, v in kw.items()):
            return
        for k, v in kw.items():
            setattr(s, k, v)
        self.page.changed()

    def _steppers(self, lb: Gtk.ListBox) -> None:
        s = self.page.setup
        n = self.page.count
        roles = [r for r in GAME_ROLES[s.kind] if playable(r) and r != "시민"]
        rows = [self._stepper(r, n) for r in roles]
        if s.kind == SIMPLE:
            for r in rows:
                lb.append(r)
        else:  # 40 roles: one fold per team, the counts in its subtitle
            for team, words in ((MAFIA, _("Mafia team")), (TOWN, _("Citizen team")), (CULT, _("Cult team"))):
                fold = self.folds[team] = Adw.ExpanderRow(title=words, expanded=True)
                for r, row in zip(roles, rows):
                    if ROLES[r].team == team:
                        fold.add_row(row)
                lb.append(fold)
        sub = _("Fills the remaining seats")
        self.citizens = Adw.ActionRow(title=role_label("시민"), subtitle=", ".join(w for w in (sub, self._pin_words("시민")) if w))
        self.citizen_value = label("", "chance-value")
        self.citizens.add_suffix(self.citizen_value)
        lb.append(self.citizens)
        note = getattr(self.page, "lineup_note", "")
        if note:  # what gave way to the newest action (AL1)
            row = Adw.ActionRow(title=note, title_lines=3)
            row.add_css_class("lineup-note")
            row.add_prefix(Gtk.Image.new_from_icon_name("dialog-information-symbolic"))
            lb.append(row)

    def _pinned(self, role: str) -> int:
        return sum(1 for x in self.page.full_setup().seats if x.role == role)

    def _pin_words(self, role: str) -> str:
        k = self._pinned(role)
        return counted(k, "{n} of them set on a seat", "{n} of them set on seats") if k else ""

    def _stepper(self, role: str, n: int) -> Adw.SpinRow:
        pair = role == "연인"
        top = n - 1  # the other side keeps at least one seat
        row = Adw.SpinRow.new_with_range(0, top - top % 2 if pair else top, 2 if pair else 1)
        row.set_title(role_label(role))
        words = [w for w in (_("Comes in pairs") if pair else "", self._pin_words(role)) if w]
        if words:
            row.set_subtitle(", ".join(words))
        row.set_value(self.page.setup.counts.get(role, 0))
        row.connect("notify::value", lambda r, _p: self._count(role, int(r.get_value())))
        return row

    def _count(self, role: str, value: int) -> None:
        if value == self.page.setup.counts.get(role, 0):
            return
        moved = fit(self.page, stepper=(role, value))  # the stepper is the newest action (AL1)
        if moved or self.page.lineup_note:  # seats or other counts gave way: the whole lobby shows it
            from gi.repository import GLib
            GLib.idle_add(lambda: (self.page.changed(fresh=False), False)[1])
            return
        self.page.save()
        self.refresh()

    def _mode(self, mode: str | None) -> None:
        s = self.page.setup
        if not mode or mode == mode_of(s):
            return
        s.role_mode = mode if not (s.kind == SIMPLE and mode == NAMED) else RANDOM
        if mode == CUSTOM and not s.counts:  # start from the lineup shown so far
            start = roles_now(self.page) or [r for r, c in simple_lineup(self.page.count).items() for _i in range(c)]
            s.counts = {r: c for r, c in Counter(start).items() if r != "시민"}
        self.page.changed()

    def refresh(self) -> None:
        """The 시민 count, the win chance, the strip on top and the start button follow a stepper at once."""
        roles = roles_now(self.page)
        if self.citizens is not None and roles is not None:
            extra = self.page.count - len(roles) + roles.count("시민")
            self.citizen_value.set_label(str(max(0, extra)))
        for team, fold in self.folds.items():
            k = sum(1 for r in roles or [] if r != "시민" and ROLES[r].team == team)
            fold.set_subtitle(counted(k, "{n} seat", "{n} seats"))
        full = self.page.full_setup()
        playable_now = full.problem() is None
        self.chance.set_visible(playable_now)
        if playable_now:
            value, words, sure = chance_text(full, roles)
            self.chance_value.set_label(value)
            self.chance.set_subtitle(words)
            (self.chance_value.remove_css_class if sure else self.chance_value.add_css_class)("dim")
        self.page.lineup_changed()
