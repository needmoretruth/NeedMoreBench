"""신의 권능: the powers popover on the game screen header, for the god view with powers on
(관전 with the switch, or 참가 with 치트). Two steps: the four groups of powers, each greyed with its reason when it
makes no sense now; a tap opens that power's own small form with only what it takes (the player, the words, the
role...), its one-line summary and 쓰기. The engine checks again and records every use; ? opens the help at the
powers."""
from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Pango  # noqa: E402

from .. import help as helptext  # noqa: E402
from ..engine import god  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import ViewState, power_label, role_label  # noqa: E402
from .widgets import clear, hbox, label, vbox  # noqa: E402

FAKE_EN = {god.VERDICTS[0]: "Says mafia", god.VERDICTS[1]: "Says not mafia"}
# what the two players of a two-player power are called on its form
PAIR_EN = {"속삭임 위조": ("To", "Seems from"), "역할 맞바꾸기": ("Player", "Second player")}


class GodPopover(Gtk.Popover):
    def __init__(self, page: Any):
        super().__init__()
        self.page = page
        self.add_css_class("god-popover")
        self.power: str | None = None  # the power whose form is open
        self.seats: list[int] = []  # what each row of `who` stands for
        self.buttons: dict[str, Gtk.Button] = {}
        self.reasons: dict[str, Gtk.Label] = {}
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vhomogeneous=False,
                               interpolate_size=True)
        self.stack.add_named(self._list_page(), "list")
        self.stack.add_named(self._form_page(), "form")
        self.set_child(self.stack)
        self._tick = 0
        self.connect("show", lambda *_a: self._shown())
        self.connect("closed", lambda *_a: self._stop())

    @property
    def st(self) -> ViewState:
        return self.page.st

    @property
    def game(self) -> Any:
        return getattr(self.page.controls, "game", None)

    def _help_button(self) -> Gtk.Button:
        b = Gtk.Button(icon_name="help-about-symbolic", tooltip_text=_("What each power does"))
        b.add_css_class("flat")
        b.connect("clicked", lambda *_a: self._help())
        return b

    @staticmethod
    def _margins(w: Gtk.Widget) -> Gtk.Widget:
        for m in ("top", "bottom", "start", "end"):
            getattr(w, f"set_margin_{m}")(12)
        return w

    # ---- step one: the powers ----------------------------------------------------------------------------
    def _list_page(self) -> Gtk.Widget:
        groups = vbox(12)
        for name, powers in god.GROUPS:
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=5, min_children_per_line=5,
                               column_spacing=6, row_spacing=6, homogeneous=True)
            for p in powers:
                flow.append(self._button(p))
            groups.append(vbox(4, label(_(god.GROUP_EN[name]), "heading", xalign=0), flow))
        self.status = label("", "meta", wrap=True, xalign=0)
        self.status.set_visible(False)
        self.standing = vbox(4)
        top = hbox(8, label(_("God powers"), "title-4"), Gtk.Box(hexpand=True), self._help_button())
        body = self._margins(vbox(10, top, groups, self.status, self.standing))
        body.set_size_request(620, -1)  # five buttons a line: all four groups fit a 820 px window
        return Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, propagate_natural_height=True,
                                  max_content_height=700, child=body)

    def _button(self, power: str) -> Gtk.Button:
        why = label("", "god-why", wrap=True, xalign=0.5)
        why.set_justify(Gtk.Justification.CENTER)
        why.set_wrap_mode(Pango.WrapMode.WORD_CHAR)  # at 13 px a reason takes two short lines, broken at spaces
        why.set_ellipsize(Pango.EllipsizeMode.END)  # never reached by the reasons we have; the tooltip says it whole
        why.set_lines(3)
        why.set_visible(False)
        b = Gtk.Button(child=vbox(1, label(power_label(power), xalign=0.5), why))
        b.add_css_class("god-power")
        b.connect("clicked", lambda *_a: self.open_power(power))
        self.buttons[power], self.reasons[power] = b, why
        return b

    # ---- step two: one power's form ----------------------------------------------------------------------
    def _form_page(self) -> Gtk.Widget:
        back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=_("All powers"))
        back.add_css_class("flat")
        back.connect("clicked", lambda *_a: self.show_list())
        self.title = label("", "title-4")
        self.summary = label("", "dim-label", wrap=True, xalign=0)
        self.who = Gtk.DropDown.new_from_strings([])
        self.other = Gtk.DropDown.new_from_strings([v.name for v in self.st.seats])
        self.text = Gtk.Entry(hexpand=True, max_length=300)
        self.text.connect("activate", lambda *_a: self.send())
        self.roles = sorted({v.role for v in self.st.seats if v.role} | {"시민", "마피아"})
        self.role = Gtk.DropDown.new_from_strings([role_label(r) for r in self.roles])
        self.fakes: list[str] = []
        self.fake = Gtk.DropDown.new_from_strings([])
        self.turns = Gtk.SpinButton.new_with_range(-20, 20, 1)
        self.turns.set_value(2)
        for w in (self.who, self.other, self.role, self.fake, self.turns):
            w.set_hexpand(True)
        for w in (self.who, self.other, self.role, self.fake):
            w.connect("notify::selected", lambda *_a: self._sync_form())
        self.text.connect("changed", lambda *_a: self._sync_form())
        self.turns.connect("value-changed", lambda *_a: self._sync_form())
        self.fields = Gtk.Grid(column_spacing=10, row_spacing=8)
        self.field_names: dict[str, Gtk.Label] = {}
        for i, (key, w) in enumerate((("who", self.who), ("other", self.other), ("text", self.text),
                                      ("role", self.role), ("result", self.fake), ("number", self.turns))):
            self.field_names[key] = label("", "meta", xalign=0)
            self.fields.attach(self.field_names[key], 0, i, 1, 1)
            self.fields.attach(w, 1, i, 1, 1)
        self.why = label("", "god-reason", wrap=True, xalign=0)
        self.use_btn = Gtk.Button(label=_("Use"))
        self.use_btn.add_css_class("pill")
        self.use_btn.add_css_class("god-use")
        self.use_btn.connect("clicked", lambda *_a: self.send())
        foot = hbox(10, self.why, self.use_btn)
        self.why.set_hexpand(True)
        top = hbox(6, back, self.title, Gtk.Box(hexpand=True), self._help_button())
        body = self._margins(vbox(12, top, self.summary, self.fields, foot))
        body.set_size_request(420, -1)
        return body

    def open_power(self, power: str) -> None:
        """Step two for one power: only the fields it takes, filled with a player it makes sense on."""
        self.power = power
        self.title.set_label(power_label(power))
        self.summary.set_label(helptext.powers()[power][0])
        tgt, need = god.TARGET.get(power), god.NEEDS.get(power)
        names = PAIR_EN.get(power, ("Player", "Second player"))
        shown = {"who": tgt is not None, "other": tgt == "two", "text": need == "text", "role": need == "role",
                 "result": need == "result", "number": need == "number"}
        for key, on in shown.items():
            self.field_names[key].set_visible(on)
            self.fields.get_child_at(1, list(shown).index(key)).set_visible(on)
        self.field_names["who"].set_label(_(names[0]))
        self.field_names["other"].set_label(_(names[1]))
        self.field_names["text"].set_label(_("Words"))
        self.field_names["role"].set_label(_("New role"))
        self.field_names["result"].set_label(_("Result"))
        self.field_names["number"].set_label(_("Turns"))
        self.text.set_text("")
        self.text.set_placeholder_text(_(TEXT_HINT.get(power, "")) if power in TEXT_HINT else "")
        self.seats = []
        self._sync_targets()
        g, seat = self.game, self._seat()
        if tgt == "two" and g is not None and seat is not None:  # open on a pair that works, not one player twice
            ok = [p.seat for p in g.players if p.seat != seat and god.why_not(g, power, seat, p.seat, inputs=False) is None]
            pair = ok[0] if ok else None
            if pair is not None:
                self.other.set_selected(pair)
        self.stack.set_visible_child_name("form")
        if need == "text":
            self.text.grab_focus()
        self._sync_form()

    def show_list(self) -> None:
        self.power = None
        self.stack.set_visible_child_name("list")
        self._sync()

    def select(self, seat: int | None = None, other: int | None = None) -> bool:
        """Pick the players on the open form (as a click on the lists does); False if one is not offered."""
        if seat is not None:
            if seat not in self.seats:
                return False
            self.who.set_selected(self.seats.index(seat))
        if other is not None:
            self.other.set_selected(other)
        self._sync_form()
        return True

    def use(self, power: str, seat: int | None = None, other: int | None = None, text: str = "",
            choice: str | None = None, n: int | None = None) -> bool:
        """Open the power, fill its form and tap 쓰기, the way a person does (tools and tests)."""
        self.open_power(power)
        if not self.select(seat, other):
            return False
        self.text.set_text(text)
        if choice is not None and god.NEEDS.get(power) == "role" and choice in self.roles:
            self.role.set_selected(self.roles.index(choice))
        if choice is not None and god.NEEDS.get(power) == "result" and choice in self.fakes:
            self.fake.set_selected(self.fakes.index(choice))
        if n is not None:
            self.turns.set_value(n)
        return self.send()

    # ---- what can be used now ------------------------------------------------------------------------------
    def _shown(self) -> None:
        self.show_list()
        if not self._tick:
            self._tick = GLib.timeout_add(700, lambda: (self._sync(), True)[1])

    def _stop(self) -> None:
        if self._tick:
            GLib.source_remove(self._tick)
            self._tick = 0

    def _offered(self, power: str) -> list[int]:
        """The players this power makes sense on now (all players for a two-player power: its form says why)."""
        g = self.game
        if g is None:
            return []
        if god.TARGET.get(power) == "two":
            return [p.seat for p in g.players]
        return [p.seat for p in g.players if god.why_not(g, power, p.seat, inputs=False) is None]

    def _state_reason(self, power: str) -> str | None:
        """Why a power cannot be used now on anyone (the list greys it), or None."""
        g = self.game
        tgt = god.TARGET.get(power)
        if tgt is None:
            return god.why_not(g, power, inputs=False)
        seats = [p.seat for p in g.players]
        if tgt == "two":
            why = [god.why_not(g, power, a, b, inputs=False) for a in seats for b in seats if a != b]
        else:
            why = [god.why_not(g, power, s, inputs=False) for s in seats]
        if None in why:
            return None
        return max(set(why), key=why.count)

    def _sync(self) -> None:
        g = self.game
        if g is None or not self.st.seats:
            return
        for p, b in self.buttons.items():
            reason = self._state_reason(p)
            b.set_sensitive(reason is None)
            self.reasons[p].set_label(keep_words(_(god.REASONS[reason])) if reason else "")
            self.reasons[p].set_visible(reason is not None)
            b.set_tooltip_text(_(god.REASONS[reason]) if reason else None)
        self._standing(g)
        if self.power is not None:
            self._sync_targets()
            self._sync_form()

    def _sync_targets(self) -> None:
        if self.power is None or god.TARGET.get(self.power) is None:
            return
        seats = self._offered(self.power)
        if seats == self.seats:
            return
        keep = self._seat()
        self.seats = seats
        self.who.set_model(Gtk.StringList.new([self.st.seats[s].name for s in seats]))
        if keep in seats:
            self.who.set_selected(seats.index(keep))

    def _seat(self) -> int | None:
        i = int(self.who.get_selected())
        return self.seats[i] if 0 <= i < len(self.seats) else None

    def _inputs(self) -> tuple[int | None, int | None, str, str | None, int]:
        power = self.power or ""
        seat = self._seat() if god.TARGET.get(power) else None
        other = int(self.other.get_selected()) if god.TARGET.get(power) == "two" else None
        choice: str | None = None
        if god.NEEDS.get(power) == "role":
            i = int(self.role.get_selected())
            choice = self.roles[i] if 0 <= i < len(self.roles) else None
        elif god.NEEDS.get(power) == "result":
            i = int(self.fake.get_selected())
            choice = self.fakes[i] if 0 <= i < len(self.fakes) else None
        return seat, other, self.text.get_text().strip(), choice, int(self.turns.get_value())

    def _sync_form(self) -> None:
        g = self.game
        if g is None or self.power is None:
            return
        seat = self._seat()
        if god.NEEDS.get(self.power) == "result" and seat is not None:
            fakes = god.result_choices(g, g.players[seat])
            if fakes != self.fakes:
                self.fakes = fakes
                self.fake.set_model(Gtk.StringList.new([_(FAKE_EN[f]) if f in FAKE_EN else role_label(f) for f in fakes]))
        seat, other, text, choice, n = self._inputs()
        if god.TARGET.get(self.power) and seat is None:
            reason: str | None = self._state_reason(self.power) or "pick"
        else:
            reason = god.why_not(g, self.power, seat, other, text, choice, n)
        self.use_btn.set_sensitive(reason is None)
        self.why.set_label(_(god.REASONS[reason]) if reason else "")

    def _standing(self, g: Any) -> None:
        """the revelations in force, per player, each with 거두기."""
        clear(self.standing)
        rows = [(p, rid, text) for p in g.players for rid, text in p.revelations]
        if not rows:
            return
        self.standing.append(label(_("Revelations in force"), "heading", xalign=0))
        for p, rid, text in rows:
            line = label(f"{p.name}: {text}", wrap=True, xalign=0)
            line.set_hexpand(True)
            lift = Gtk.Button(label=_("Lift"), valign=Gtk.Align.CENTER)
            lift.add_css_class("flat")
            lift.connect("clicked", lambda *_a, s=p.seat, r=rid: self._send(god.LIFT, s, n=r))
            self.standing.append(hbox(6, line, lift))

    # ---- using one ---------------------------------------------------------------------------------------
    def send(self) -> bool:
        """쓰기: send the open power with its form, back to the list with a line saying it was used."""
        g, power = self.game, self.power
        if g is None or power is None or self.st.result is not None:
            return False
        seat, other, text, choice, n = self._inputs()
        reason = god.why_not(g, power, seat, other, text, choice, n)
        if reason is not None:
            self.why.set_label(_(god.REASONS[reason]))
            return False
        self._send(power, seat, text, choice, other, n)
        self.status.set_label(_("{power} used").format(power=power_label(power)))
        self.status.set_visible(True)
        self.show_list()
        return True

    def _send(self, power: str, seat: int | None, text: str = "", choice: str | None = None, other: int | None = None,
              n: int = 0) -> None:
        if self.page.controls is not None and self.st.result is None:
            self.page.controls.god(power, seat, text, choice, other=other, n=n)
        GLib.timeout_add(150, lambda: (self._sync(), False)[1])

    def _help(self) -> None:
        from .help import open_help
        self.popdown()
        open_help(self.page, "powers")


def keep_words(text: str) -> str:
    """Break a line only at spaces: Hangul may break between any two syllables, which left one syllable alone on
    a line (플레이 / 어). A word joiner between the letters of each word keeps the word whole."""
    return " ".join("⁠".join(word) for word in text.split(" "))


TEXT_HINT = {"공지": "What everyone reads from the god", "계시": "What this player must follow until you lift it",
             "속삭임 위조": "The whisper, in the sender's voice", "빙의": "The line this player says to everyone",
             "심문": "Your question; only you see the answer"}
