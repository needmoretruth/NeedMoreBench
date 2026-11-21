"""The person's turn: an action card under the timeline when the engine asks the human seat.

The card offers exactly what the request makes legal, the same choices a model gets: a line for the square,
a whisper to one name, the vote or night target (or the skip word when skipping is legal), 연장 / 단축 and
the poll pointer when the step has them. The answer is the same dict a model's parsed answer is, so the
engine checks it the same way.
"""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from ..i18n import _  # noqa: E402
from .widgets import hbox, label, vbox  # noqa: E402

TIME = [("", "Keep"), ("연장", "Longer"), ("단축", "Shorter")]  # discussion time: keep, 연장, 단축
TITLE = {"intro": "Introduce yourself", "discuss": "Your turn to speak", "vote": "Vote", "defense": "Your last defense", "verdict": "Guilty or not",
         "mafia": "Mafia meeting", "night": "Night action", "whisper": "Whisper time", "whisper_reply": "Reply to a whisper",
         "lover": "Lovers", "dead": "The dead", "shot": "Last shot", "interrogate": "The god asks you"}
HINT = {"intro": "Everyone hears this. Your role is yours to tell, truly, falsely or not at all.",
        "discuss": "Say something to everyone, or send nothing to pass.", "vote": "Pick who should go up for the vote.",
        "defense": "Everyone hears this before the guilty or not vote.", "verdict": "Should this player die?",
        "mafia": "Only the mafia hear this. Pick tonight's target.", "night": "Pick who to use your ability on.",
        "whisper": "Send one whisper, or send nothing to pass.", "whisper_reply": "Answer the whisper, or send nothing.",
        "lover": "Only your lover hears this.", "dead": "Only the dead and the medium hear this.",
        "shot": "You were executed. Pick one living player to take with you, or nobody.",
        "interrogate": "Only the god reads your answer."}
# a role's second choice on the same card (모방자, 폭탄마), in the person's words instead of the model's task line
EXTRA = {"steal": "Copy an ability for tonight", "take": "Take along if executed (only an enemy dies)",
         "role": "Their role", "second": "Second person", "check": "Check for Mafia (once a game)",
         "tap": "Learn their role at nightfall", "wake": "Wake from the spell"}
SAY_HINT = {"mafia": "Say to the mafia", "lover": "Say to your lover", "dead": "Say to the dead",
            "interrogate": "Answer the god"}


class Choice(Gtk.FlowBox):
    """One pick among names (and the skip word): pill toggles, nothing chosen at first."""

    def __init__(self, options: list[str], skip: str | None, on_change: Callable[[], None]):
        super().__init__(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=6,
                         row_spacing=6, homogeneous=False)
        self.value: str | None = None
        first: Gtk.ToggleButton | None = None
        for text in options + ([skip] if skip else []):
            b = Gtk.ToggleButton(label=text)
            b.add_css_class("pill")
            b.add_css_class("choice")
            if text == skip:
                b.add_css_class("skip")
            if first is None:
                first = b
            else:
                b.set_group(first)
            b.connect("toggled", self._toggled, text, on_change)
            self.append(b)

    def _toggled(self, b: Gtk.ToggleButton, text: str, on_change: Callable[[], None]) -> None:
        if b.get_active():
            self.value = text
            on_change()


class ActionCard(Gtk.Box):
    def __init__(self, req: dict[str, Any], send: Callable[[dict[str, Any]], None], others: list[str]):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("action-card")
        self.req = req
        self.send_fn = send
        kind = req.get("kind", "")
        title = _(TITLE.get(kind, "Your turn"))
        if req.get("named_by"):  # a reply turn: someone named the person
            title = _("{name} named you").format(name=req["named_by"])
        self.append(label(title, "action-title"))
        hint = HINT.get(kind)
        if hint:
            self.append(label(_(hint), "meta"))
        self.limit = float(req.get("limit") or 0)
        if self.limit > 0:  # the time left; when it runs out the turn passes
            self.clock = Gtk.ProgressBar(fraction=1.0)
            self.clock.add_css_class("turn-clock")
            self.append(self.clock)
            self.started = GLib.get_monotonic_time()
            GLib.timeout_add(200, self._tick)
        self.choice: Choice | None = None
        self.extra: Choice | None = None
        if req.get("field"):
            self.choice = Choice(list(req.get("options") or []), req.get("skip_word"), self._check)
            self.append(self.choice)
        if req.get("extra_field"):
            self.append(label(_(EXTRA[req["extra_field"]]) if req["extra_field"] in EXTRA else req.get("extra_task", ""), "meta"))
            self.extra = Choice(list(req.get("extra_options") or []), "없음", self._check)
            self.append(self.extra)

        self.say: Gtk.Entry | None = None
        if req.get("say"):
            self.say = Gtk.Entry(placeholder_text=_(SAY_HINT.get(kind, "Say to everyone")),
                                 hexpand=True, max_length=600)
            self.say.connect("activate", lambda *_a: self._send())
            self.append(self.say)

        self.whisper_to: Gtk.DropDown | None = None
        self.whisper_text: Gtk.Entry | None = None
        names = list(req.get("whisper_to") or [])
        if req.get("whispers") and names:
            self.whisper_to = Gtk.DropDown.new_from_strings([_("No whisper")] + names)
            self.whisper_text = Gtk.Entry(placeholder_text=_("Whisper"), hexpand=True, max_length=400)
            self.whisper_text.connect("activate", lambda *_a: self._send())
            self.whisper_text.connect("changed", lambda e: self._whisper_typed())
            self.append(hbox(8, self.whisper_to, self.whisper_text))

        extras = Gtk.Box(spacing=8)
        self.time: Adw.ToggleGroup | None = None
        if req.get("time"):
            self.time = Adw.ToggleGroup()
            for name, text in TIME:
                self.time.add(Adw.Toggle(name=name or "keep", label=_(text)))
            self.time.set_active_name("keep")
            extras.append(label(_("Discussion"), "meta"))
            extras.append(self.time)
        self.poll: Gtk.DropDown | None = None
        if req.get("poll"):
            self.poll_names = others
            if self.poll_names:
                self.poll = Gtk.DropDown.new_from_strings([_("Nobody")] + self.poll_names)
                extras.append(label(_("Most suspicious"), "meta"))
                extras.append(self.poll)
        self.send_btn = Gtk.Button(label=_("Send"))
        self.send_btn.add_css_class("pill")
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.set_halign(Gtk.Align.END)
        self.send_btn.set_hexpand(True)
        self.send_btn.connect("clicked", lambda *_a: self._send())
        extras.append(self.send_btn)
        self.append(extras)
        self._check()

    def _tick(self) -> bool:
        left = 1 - (GLib.get_monotonic_time() - self.started) / (self.limit * 1_000_000)
        self.clock.set_fraction(max(0.0, left))
        return left > 0

    def _whisper_typed(self) -> None:
        if self.whisper_to is not None and self.whisper_text is not None and self.whisper_text.get_text().strip() \
                and self.whisper_to.get_selected() == 0 and self.whisper_to.get_model().get_n_items() == 2:
            self.whisper_to.set_selected(1)  # the only name there is

    def ready(self) -> bool:
        if self.choice is not None and self.choice.value is None:
            return False
        return not (self.extra is not None and self.extra.value is None)

    def _check(self) -> None:
        self.send_btn.set_sensitive(self.ready())

    def answer(self) -> dict[str, Any]:
        r = self.req
        obj: dict[str, Any] = {}
        if self.choice is not None and r.get("field"):
            obj[r["field"]] = self.choice.value
        if self.extra is not None and r.get("extra_field"):
            obj[r["extra_field"]] = self.extra.value
        if self.say is not None:
            obj["say"] = self.say.get_text().strip()
        if self.whisper_to is not None and self.whisper_text is not None:
            i = self.whisper_to.get_selected()
            text = self.whisper_text.get_text().strip()
            names = list(r.get("whisper_to") or [])
            obj["whispers"] = [{"to": names[i - 1], "text": text}] if i > 0 and text else []
        if self.time is not None and self.time.get_active_name() in ("연장", "단축"):
            obj["time"] = self.time.get_active_name()
        if self.poll is not None and self.poll.get_selected() > 0:
            obj["poll"] = self.poll_names[self.poll.get_selected() - 1]
        return obj

    def _send(self) -> None:
        if not self.ready():
            return
        self.send_fn(self.answer())


def card_box(card: ActionCard) -> Gtk.Widget:
    box = vbox(0, card)
    box.add_css_class("action-dock")
    return box
