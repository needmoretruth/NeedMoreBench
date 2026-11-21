"""Small building blocks of the game screen: labels, chips, avatars, player cards, timeline lines."""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from ..engine.state import Event  # noqa: E402
from ..providers.base import STATUS_TEXT  # noqa: E402
from ..i18n import _, counted  # noqa: E402
from ..view import (LINE_STYLE, SPEECH, SeatView, ViewState, line_text, power_label, result_text, result_word, role_label,  # noqa: E402
                    team_class)


PILLS = frozenset({"badge", "chip"})  # style.css gives these a rounded background


def label(text: str = "", *classes: str, wrap: bool = False, xalign: float = 0.0, selectable: bool = False) -> Gtk.Label:
    lb = Gtk.Label(label=text, xalign=xalign)
    for c in classes:
        lb.add_css_class(c)
    if PILLS.intersection(classes):  # a pill stretched to the row's height reads as a tall capsule (picker)
        lb.set_valign(Gtk.Align.CENTER)
    if wrap:
        lb.set_wrap(True)
        lb.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    lb.set_selectable(selectable)
    return lb


def chip(text: str, kind: str = "plain") -> Gtk.Label:
    lb = label(text, "chip", kind)
    lb.set_valign(Gtk.Align.CENTER)
    return lb


GOD_ICON = "weather-clear-symbolic"  # the god's mark: the header's powers button and every god line


def god_icon() -> Gtk.Image:
    img = Gtk.Image.new_from_icon_name(GOD_ICON)
    img.add_css_class("god-spark")
    img.set_valign(Gtk.Align.CENTER)
    return img


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
        self.name.set_width_chars(5)  # a short name stays whole; the talk chip gives way first
        self.model = label("", "meta")
        self.model.set_ellipsize(Pango.EllipsizeMode.END)
        self.role = chip("")
        self.poll = label("", "poll-count")
        self.poll.set_tooltip_text(_("Picked in the poll"))
        self.votes = label("", "vote-count")
        self.voters = hbox(0)
        self.voters.add_css_class("voter-dots")
        self.dots = Dots()
        self.talk = label("", "talk-state")
        self.talk.set_ellipsize(Pango.EllipsizeMode.END)
        self.name.set_hexpand(True)
        self.model.set_hexpand(True)
        # the pick count sits on the second line, so the talk chip beside the name reads whole at 1280
        text = vbox(3, hbox(6, self.name, self.dots, self.talk),
                    hbox(6, self.role, self.model, self.poll, self.voters, self.votes))
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
        self.poll.set_label(_("Picked {n}").format(n=v.polls))  # a bare number beside 손 듦 said nothing
        self.votes.set_visible(v.votes is not None and v.votes > 0)
        self.votes.set_label(counted(v.votes, "{n} vote", "{n} votes") if v.votes else "")
        clear(self.voters)
        for n in v.voters[:6]:
            self.voters.append(avatar(n, 18))
        self.voters.set_visible(bool(v.voters))
        state = v.talk if st.step == "토론" and v.alive else ""
        thinking = v.thinking or state == "thinking"
        # a person's turn is the card under the timeline; the dots say thinking only where the talk chip does not,
        # so the name keeps its room beside the chip at the 13 px text floor
        self.dots.run(thinking and v.kind != "human" and state != "thinking")
        human_turn = state == "thinking" and v.kind == "human"  # a person is not thinking; it is their turn
        self.talk.set_label(_("Their turn") if human_turn else _(TALK_STATE[state]) if state in TALK_STATE else "")
        self.talk.set_visible(state in TALK_STATE)
        for c in TALK_STATE:
            (self.talk.add_css_class if c == state else self.talk.remove_css_class)(c)
        # the whole state on hover, since a narrow side panel cuts the chip short
        self.talk.set_tooltip_text(failure_text(v.talk_why) if state == "failed" else self.talk.get_label() or None)
        for c, on in (("dead", not v.alive), ("speaking", thinking)):
            (self.add_css_class if on else self.remove_css_class)(c)


# each player's state in the talk, so a quiet model never looks broken
TALK_STATE = {"speaking": "Speaking", "thinking": "Thinking", "hand": "Hand up", "done": "Nothing to add", "failed": "No answer"}


def failure_text(reason: str) -> str:
    if reason == "timeout":
        return _("No answer in time")
    return _(STATUS_TEXT[reason]) if reason in STATUS_TEXT else _("The call failed")


SYSTEM_STRONG = ("투표 시간입니다.", "토론 시간이 얼마 남지 않았습니다.")  # message keys (and the text of older records)


def thought_note(e: Event, name: str = "") -> Gtk.Widget:
    """A 속마음: private thinking, never a message. No bubble; a muted note with the thinker's small
    avatar and 「(이름)의 속마음」 and 「아무도 못 봄」, so it never reads as one model talking to another and it is
    always clear whose it is, also alone at night."""
    head = hbox(6, avatar(name, 18), label(_("{name}'s thought").format(name=name), "channel", "thought"),
                label(_("Seen by no one"), "thought-who"))
    box = vbox(1, head, label(e.text, "thought-text", wrap=True, selectable=True))
    box.add_css_class("thought-note")
    box.set_halign(Gtk.Align.START)
    return box


def reasoning_note(e: Event, name: str = "") -> Gtk.Widget:
    """The model's own reasoning, in the language it used: a closed note under the speaker's line that opens
    to the whole text, marked as Anthropic's summary when it is one; it names whose it is."""
    head = hbox(6, avatar(name, 18), label(_("{name}'s reasoning").format(name=name), "channel", "reasoning"),
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
        row.set_child(thought_note(e, name) if k == "thought" else reasoning_note(e, name))
        row.add_css_class("thought-row")
        return row
    if k == "action" and e.actor is not None:  # an ability used, with whose and which role
        mine = st.viewer is not None and e.actor == st.viewer
        text = _("You: {what}").format(what=line_text(e, "what")) if mine else line_text(e)
        line = hbox(6, avatar(name, 22), chip(role_label(d.get("role")), team_class(d.get("role"))),
                    label(text, "action-text", wrap=True))
        line.add_css_class("action-line")
        line.set_halign(Gtk.Align.CENTER)
        row.set_child(line)
        return row
    if k == "god" and d.get("god_effect") and st.viewer is None and not d.get("answer"):
        return None  # the god view reads the god's own record line of this power instead
    god = god_line(st, e)
    if god is not None:
        row.set_child(god)
        row.add_css_class("god-row")
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
        elif k in ("lover", "dead", "cult"):
            head.append(label(_(style[0]), "channel"))
        elif d.get("defense"):
            head.append(label(_("Last defense"), "channel"))
        elif d.get("intro"):
            head.append(label(_("Introduction"), "channel"))
        if d.get("god_effect") and st.viewer is None:  # only the god view learns the god made this line
            mark = hbox(4, god_icon(), chip(_("Forged") if k == "whisper" else _("Possessed"), "god"))
            mark.set_tooltip_text(_("The players read this as real"))
            head.append(mark)
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
        text = line_text(e)
        body = text.split(": ", 1)[1] if ": " in text[:16] else text
        card = vbox(4, label(title, "section-title"), label(body, "tally", wrap=True))
        card.add_css_class("card")
        card.add_css_class("result-card")
        row.set_child(card)
        return row
    if k == "end":
        title = result_text(d.get("result") or {}, "label") or _("Game over")
        body = result_text(d.get("result") or {}, "reason") or line_text(e)
        if body.startswith(title):  # the end line opens with the result the card's title already says
            body = body[len(title):].lstrip(" .:,")
        if body and body[-1] not in ".!?":
            body += "."
        card = vbox(4, label(title, "title-3"))
        if body:
            card.append(label(body, wrap=True))
        card.add_css_class("card")
        card.add_css_class("result-card")
        row.set_child(card)
        return row
    if k in ("system", "death", "god", "moderator", "private", "saved", "contact", "would_end", "error", "route", "role",
             "seduce", "frog", "spare", "trick", "convert"):
        if not e.text:
            return None
        text = shown = line_text(e)
        if k == "private":
            who = st.name_of(min(e.to) if e.to else None)
            text = (_("Only {name} knows").format(name=who) if st.viewer is None else _("Only you know")) + ": " + shown
        elif k == "moderator":
            text = _("Moderator") + ": " + shown
        lb = label(text, "system-line", wrap=True, xalign=0.5)
        lb.set_justify(Gtk.Justification.CENTER)
        lb.set_halign(Gtk.Align.CENTER)
        if k == "death":
            lb.add_css_class("death")
        elif k in ("god", "moderator"):
            lb.add_css_class("god")
        elif k == "system" and ((d.get("msg") or {}).get("k") or e.text) in SYSTEM_STRONG:
            lb.add_css_class("strong")
        row.set_child(lb)
        return row
    return None


def god_line(st: ViewState, e: Event) -> Gtk.Widget | None:
    """A power's line in the god colour, with the god's sun icon and the power's name; it glows once when new.
    The god view gets the god's own record line, the answer to a 심문 and a delivered 거짓 결과 with the truth
    beside it. A player's screen gets what the power showed that player, which never says who the 신 is."""
    k, d = e.kind, e.data
    if not (k == "god" or k == "private" and d.get("false_result") and st.viewer is None):
        return None
    if not e.text:
        return None
    power = d.get("power")
    me = st.viewer is not None
    shown = line_text(e)  # the interface language, from the message the record keeps
    if k == "private":
        head = _("False result")
        text = _("Only {name} knows").format(name=st.name_of(min(e.to) if e.to else None))
        text += ": " + shown + " (" + _("true: {result}").format(result=result_word(d.get("real_result", ""))) + ")"
    elif d.get("answer"):
        who = _("You") if me else st.name_of(e.target)
        head, text = power_label(power), _("{name} to the god").format(name=who) + ": " + shown
    elif power == "공지":
        head, text = _("God"), shown
    elif me and power in ("계시", "심문") and e.to:
        head, text = (_("Revelation to you") if power == "계시" else _("God's question to you")), shown
    else:
        head, text = power_label(power) if power else _("God"), shown
    lb = label(text, "god-text", wrap=True, xalign=0.5)
    lb.set_justify(Gtk.Justification.CENTER)
    box = hbox(8, god_icon(), chip(head, "god"), lb)
    box.add_css_class("god-line")
    box.set_halign(Gtk.Align.CENTER)
    if d.get("record") and d.get("used_by") not in (None, "관전자"):
        box.set_tooltip_text(_("Used by {name}").format(name=st.name_of(d["used_by"])))
    return box


def _filter_kind(e: Event) -> str:
    if e.kind == "whisper":
        return "whisper"
    if e.kind in ("mafia", "lover", "dead", "cult"):  # the night chats
        return "mafia"
    if e.kind in ("thought", "reasoning"):
        return e.kind
    if e.kind == "say":
        return "say"
    return "system"
