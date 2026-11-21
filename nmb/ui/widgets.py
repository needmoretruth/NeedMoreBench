"""Small building blocks of the game screen: labels, chips, avatars, player cards, timeline lines."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..engine.state import Event  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import LINE_STYLE, SPEECH, SeatView, ViewState, role_label, team_class  # noqa: E402


def label(text: str = "", *classes: str, wrap: bool = False, xalign: float = 0.0, selectable: bool = False) -> Gtk.Label:
    lb = Gtk.Label(label=text, xalign=xalign)
    for c in classes:
        lb.add_css_class(c)
    if wrap:
        lb.set_wrap(True)
        lb.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lb.set_selectable(selectable)
    return lb


def chip(text: str, kind: str = "plain") -> Gtk.Label:
    lb = label(text, "chip", kind)
    lb.set_valign(Gtk.Align.CENTER)
    return lb


def avatar(name: str, size: int = 36) -> Adw.Avatar:
    a = Adw.Avatar(size=size, text=name, show_initials=True)
    a.set_valign(Gtk.Align.CENTER)
    return a


def hbox(spacing: int = 8, *children: Gtk.Widget) -> Gtk.Box:
    b = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=spacing)
    for c in children:
        b.append(c)
    return b


def vbox(spacing: int = 4, *children: Gtk.Widget) -> Gtk.Box:
    b = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing)
    for c in children:
        b.append(c)
    return b


def clear(box: Gtk.Widget) -> None:
    child = box.get_first_child()
    while child is not None:
        nxt = child.get_next_sibling()
        box.remove(child)
        child = nxt


class Dots(Gtk.Label):
    """The only looping motion on screen: three dots while a model is thinking."""

    def __init__(self) -> None:
        super().__init__(label="")
        self.add_css_class("thinking-dots")
        self._n = 0
        self._id = 0

    def run(self, on: bool) -> None:
        if on and not self._id:
            self._id = GLib.timeout_add(380, self._tick)
            self._tick()
        elif not on and self._id:
            GLib.source_remove(self._id)
            self._id = 0
            self.set_label("")

    def _tick(self) -> bool:
        self._n = (self._n + 1) % 4
        self.set_label("•" * self._n + "◦" * (3 - self._n))
        return True


class PlayerCard(Gtk.ListBoxRow):
    """One seat in the left list: avatar, name, model line, role chip, poll and vote counts, thinking dots."""

    def __init__(self, v: SeatView):
        super().__init__()
        self.seat = v.seat
        self.add_css_class("player-row")
        self.avatar = avatar(v.name, 36)
        self.name = label(v.name, "name")
        self.name.set_ellipsize(Pango.EllipsizeMode.END)
        self.model = label("", "meta")
        self.model.set_ellipsize(Pango.EllipsizeMode.END)
        self.role = chip("")
        self.poll = label("", "poll-count")
        self.poll.set_tooltip_text(_("Picked in the poll"))
        self.votes = label("", "vote-count")
        self.voters = hbox(0)
        self.voters.add_css_class("voter-dots")
        self.dots = Dots()
        self.name.set_hexpand(True)
        self.model.set_hexpand(True)
        text = vbox(3, hbox(6, self.name, self.dots, self.poll), hbox(6, self.role, self.model, self.voters, self.votes))
        text.set_hexpand(True)
        self.set_child(hbox(10, self.avatar, text))

    def update(self, st: ViewState, v: SeatView) -> None:
        self.name.set_label(v.name)
        line = v.model_line if st.owner_sees_models or st.result is not None else ""
        if not v.alive:
            line = (_("Dead") + ", " + line) if line else _("Dead")
        self.model.set_label(line)
        self.model.set_visible(bool(line))
        show_role = st.role_visible(v) and bool(v.role)
        self.role.set_visible(show_role)
        if show_role:
            self.role.set_label(role_label(v.role))
            for c in ("mafia", "town", "cult", "plain"):
                self.role.remove_css_class(c)
            self.role.add_css_class(team_class(v.role))
        self.poll.set_visible(v.polls > 0 and st.step == "토론")
        self.poll.set_label(str(v.polls))
        self.votes.set_visible(v.votes is not None and v.votes > 0)
        self.votes.set_label(_("{n} votes").format(n=v.votes) if v.votes else "")
        clear(self.voters)
        for n in v.voters[:6]:
            self.voters.append(avatar(n, 18))
        self.voters.set_visible(bool(v.voters))
        self.dots.run(v.thinking and v.kind != "human")  # a person's turn is the card under the timeline
        for c, on in (("dead", not v.alive), ("speaking", v.thinking)):
            (self.add_css_class if on else self.remove_css_class)(c)


SYSTEM_STRONG = ("투표 시간입니다.", "토론 시간이 얼마 남지 않았습니다.")


def thought_note(e: Event) -> Gtk.Widget:
    """A 속마음: private thinking, never a message. No avatar and no bubble; a muted note indented under
    the speaker's line with its label and 「아무도 못 봄」, so it never reads as one model talking to another."""
    head = hbox(6, label(_("Thought"), "channel", "thought"), label(_("Seen by no one"), "thought-who"))
    box = vbox(1, head, label(e.text, "thought-text", wrap=True, selectable=True))
    box.add_css_class("thought-note")
    box.set_halign(Gtk.Align.START)
    return box


def reasoning_note(e: Event) -> Gtk.Widget:
    """The model's own reasoning, in the language it used: a closed note under the speaker's line that opens
    to the whole text, marked as Anthropic's summary when it is one."""
    head = hbox(6, label(_("Reasoning"), "channel", "reasoning"),
                label(_("Summary") if e.data.get("summarized") else _("Seen by no one"), "thought-who"))
    first = " ".join(e.text.split())
    preview = label(first[:90], "thought-who")
    preview.set_ellipsize(Pango.EllipsizeMode.END)  # a long first line must not hold the timeline wider than the window
    preview.set_max_width_chars(60)
    head.append(preview)
    body = label(e.text, "thought-text", wrap=True, selectable=True)
    exp = Gtk.Expander(label_widget=head, child=body)
    exp.add_css_class("thought-note")
    exp.add_css_class("reasoning-note")
    exp.set_halign(Gtk.Align.START)
    return exp


def timeline_row(st: ViewState, e: Event) -> Gtk.ListBoxRow | None:
    """One line in the timeline, or None for events that only change state."""
    row = Gtk.ListBoxRow(activatable=False, selectable=False)
    row.add_css_class("line-row")
    row.kind = _filter_kind(e)
    row.event_id = e.id
    k, d = e.kind, e.data
    name = st.name_of(e.actor)
    style = LINE_STYLE.get(k)
    if k in ("thought", "reasoning") and e.actor is not None:
        row.set_child(thought_note(e) if k == "thought" else reasoning_note(e))
        row.add_css_class("thought-row")
        return row
    if k in SPEECH and e.actor is not None and style is not None:
        if k == "mafia" and not e.text:
            return None
        head = hbox(6, label(name, "name"))
        if k == "whisper":  # 「귓속말 A → B」, only ever in 귓속말 시간
            lock = Gtk.Image.new_from_icon_name("changes-prevent-symbolic")
            lock.add_css_class("whisper-lock")
            head = hbox(5, lock, label(_(style[0]).format(a=name, b=st.name_of(e.target)), "whisper-to"))
        elif k == "mafia":  # its own channel with the team mark, only ever at night
            head.append(chip(_(style[0]), "mafia"))
            if d.get("pick"):
                head.append(label(_("Pick: {name}").format(name=d["pick"]), "channel", "mafia"))
        elif k in ("lover", "dead"):
            head.append(label(_(style[0]), "channel"))
        elif d.get("defense"):
            head.append(label(_("Last defense"), "channel"))
        elif d.get("intro"):
            head.append(label(_("Introduction"), "channel"))
        bubble = vbox(2, head, label(e.text, "bubble-text", wrap=True, selectable=True))
        bubble.add_css_class("bubble")
        if k != "say":
            bubble.add_css_class(style[1])
        if d.get("defense"):
            bubble.add_css_class("defense")
        bubble.set_halign(Gtk.Align.START)
        av = avatar(name, 32)
        av.set_valign(Gtk.Align.START)
        mine = st.viewer is not None and e.actor == st.viewer
        if mine:
            bubble.add_css_class("mine")
            bubble.set_halign(Gtk.Align.END)
            box = hbox(10, bubble)
            box.set_halign(Gtk.Align.END)
        else:
            box = hbox(10, av, bubble)
        bubble.set_size_request(-1, -1)
        row.set_child(box)
        return row
    if k == "phase":  # a clear line between day and night
        night = d.get("phase", e.phase) == "night"
        icon = Gtk.Image.new_from_icon_name("weather-clear-night-symbolic" if night else "weather-clear-symbolic")
        pill = hbox(6, icon, label(st.when(e)))
        pill.add_css_class("phase-divider")
        left, right = Gtk.Separator(hexpand=True, valign=Gtk.Align.CENTER), Gtk.Separator(hexpand=True, valign=Gtk.Align.CENTER)
        line = hbox(12, left, pill, right)
        line.add_css_class("phase-line")
        line.add_css_class("night" if night else "day")
        row.set_child(line)
        return row
    if k == "compaction":  # god view only: a player summed up its own history
        who = st.name_of(e.actor)
        how = _("by itself") if d.get("by") == "model" else _("by the engine")
        lb = label(_("{name} summed up older history ({how})").format(name=who, how=how), "system-line", xalign=0.5)
        lb.set_halign(Gtk.Align.CENTER)
        lb.set_tooltip_text(e.text[:600])
        row.set_child(lb)
        return row
    if k in ("vote_result", "verdict_result"):
        title = _("Vote result") if k == "vote_result" else _("Verdict result")
        body = e.text.split(": ", 1)[1] if ": " in e.text[:12] else e.text
        card = vbox(4, label(title, "section-title"), label(body, "tally", wrap=True))
        card.add_css_class("card")
        card.add_css_class("result-card")
        row.set_child(card)
        return row
    if k == "end":
        card = vbox(4, label(d.get("result", {}).get("label") or _("Game over"), "title-3"), label(e.text, wrap=True))
        card.add_css_class("card")
        card.add_css_class("result-card")
        row.set_child(card)
        return row
    if k in ("system", "death", "god", "moderator", "private", "saved", "contact", "would_end", "error", "route", "role",
             "seduce"):
        if not e.text:
            return None
        text = e.text
        if k == "private":
            who = st.name_of(min(e.to) if e.to else None)
            text = (_("Only {name} knows").format(name=who) if st.viewer is None else _("Only you know")) + ": " + e.text
        elif k == "moderator":
            text = _("Moderator") + ": " + e.text
        elif k == "god" and d.get("power") == "공지":
            text = _("God") + ": " + e.text
        elif k == "god" and d.get("power") == "계시":
            text = _("God to {name}").format(name=st.name_of(e.target)) + ": " + e.text
        lb = label(text, "system-line", wrap=True, xalign=0.5)
        lb.set_justify(Gtk.Justification.CENTER)
        lb.set_halign(Gtk.Align.CENTER)
        if k == "death":
            lb.add_css_class("death")
        elif k in ("god", "moderator"):
            lb.add_css_class("god")
        elif k == "system" and e.text in SYSTEM_STRONG:
            lb.add_css_class("strong")
        row.set_child(lb)
        return row
    return None


def _filter_kind(e: Event) -> str:
    if e.kind == "whisper":
        return "whisper"
    if e.kind in ("mafia", "lover", "dead"):  # the night chats
        return "mafia"
    if e.kind in ("thought", "reasoning"):
        return e.kind
    if e.kind == "say":
        return "say"
    return "system"
