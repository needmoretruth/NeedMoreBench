"""다시보기: a saved game on the same game screen, read-only, with a timeline scrubber, play and
pause, speed, jumps to each day and night, and the god view or the blind view with a reveal switch.
"""
from __future__ import annotations

from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk  # noqa: E402

from ..engine.state import Event  # noqa: E402
from ..store import Saved, event_from_record  # noqa: E402
from ..i18n import _  # noqa: E402
from ..view import ViewState  # noqa: E402
from .game_page import GamePage  # noqa: E402
from .widgets import hbox, label  # noqa: E402

SPEEDS = [("0.5×", 1.6), ("1×", 0.8), ("2×", 0.4), ("4×", 0.15)]


class Replay:
    """Drives a GamePage from a saved record. Implements the controls the page calls (pause, set_delay)."""

    def __init__(self, saved: Saved, on_sound: Callable[[str], None] | None = None,
                 on_again: Callable[[], None] | None = None):
        self.saved = saved
        self.on_again = on_again
        self.events: list[Event] = [event_from_record(d) for d in saved.events]
        settings = saved.header.get("settings", {})
        self.blind_for_owner = not settings.get("named", True) and settings.get("blind_scope") == "me"
        self.reveal = not self.blind_for_owner
        self.pos = 0
        self.delay = 0.8
        self.playing = False
        self._timer = 0
        st = self._state()
        self.page = GamePage(st, _("Replay"), on_sound=on_sound, controls=self)
        self.page.set_title(_("Replay"))
        self.page.god_btn.set_visible(False)
        self.page.speed_btn.set_visible(False)
        self._build_bar()
        self.page.connect("hidden", lambda *_: self.pause(True))
        if saved.result is not None:
            self.page.on_end = self._show_end

    def _show_end(self) -> None:
        if self.saved.result is None or self.page.get_root() is None:
            return
        from .end import EndDialog
        EndDialog(self.saved.header, self.saved.result, None, on_again=self.on_again).present(self.page)

    def _state(self) -> ViewState:
        st = ViewState.from_header(self.saved.header, viewer=None, reveal_models=self.reveal)
        st.paused = not self.playing
        return st

    # ---- controls ------------------------------------------------------------------------------------------
    def _build_bar(self) -> None:
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, max(1, len(self.events)), 1)
        self.scale.set_draw_value(False)
        self.scale.set_hexpand(True)
        for i, e in enumerate(self.events):
            if e.kind == "phase":
                self.scale.add_mark(i, Gtk.PositionType.BOTTOM, None)
        self.scale.connect("change-value", self._scrubbed)
        self.play_btn = Gtk.Button(icon_name="media-playback-start-symbolic", tooltip_text=_("Play"))
        self.play_btn.add_css_class("circular")
        self.play_btn.connect("clicked", lambda *_: self.pause(self.playing))
        prev_btn = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=_("Previous phase"))
        prev_btn.add_css_class("flat")
        prev_btn.connect("clicked", lambda *_: self.jump(-1))
        next_btn = Gtk.Button(icon_name="go-next-symbolic", tooltip_text=_("Next phase"))
        next_btn.add_css_class("flat")
        next_btn.connect("clicked", lambda *_: self.jump(1))
        speed = Gtk.DropDown.new_from_strings([s for s, _ in SPEEDS])
        speed.set_selected(1)
        speed.connect("notify::selected", lambda d, _p: self.set_delay(SPEEDS[d.get_selected()][1]))
        self.where = label("", "meta")
        self.where.set_width_chars(16)
        bits = [prev_btn, self.play_btn, next_btn, self.scale, self.where, speed]
        if self.blind_for_owner:
            sw = Gtk.Switch(active=self.reveal, valign=Gtk.Align.CENTER)
            sw.connect("notify::active", lambda s, _p: self._set_reveal(s.get_active()))
            bits += [label(_("Show models"), "meta"), sw]
        bar = hbox(8, *bits)
        bar.add_css_class("turns-bar")
        bar.set_margin_start(6)
        bar.set_margin_end(6)
        self.page.bottom_bar.append(bar)
        status = _("Finished game") if self.saved.finished else _("Stopped game, shown up to where it stopped")
        self.page.cost_label.set_label(status)
        self.seek(len(self.events) if not self.saved.finished else 0)

    def _scrubbed(self, _s: Gtk.Scale, _scroll: Any, value: float) -> bool:
        self.seek(int(round(value)))
        return False

    def seek(self, pos: int) -> None:
        self.pos = max(0, min(len(self.events), pos))
        st = self._state()
        self.page.rebuild(self.events[: self.pos], st)
        self._sync()

    def jump(self, direction: int) -> None:
        marks = [i for i, e in enumerate(self.events) if e.kind == "phase"] + [len(self.events)]
        if direction > 0:
            nxt = next((m for m in marks if m > self.pos), len(self.events))
        else:
            nxt = max([m for m in marks if m < self.pos - 1] or [0])
        self.seek(nxt + (1 if direction > 0 and nxt < len(self.events) else 0))

    def pause(self, paused: bool) -> None:
        self.playing = not paused
        self.page.st.paused = paused
        if self.playing and self.pos >= len(self.events):
            self.seek(0)
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0
        if self.playing:
            self._timer = GLib.timeout_add(int(self.delay * 1000), self._step)
        self._sync()

    def set_delay(self, secs: float) -> None:
        self.delay = secs
        if self.playing:
            self.pause(False)

    def end_discussion(self) -> None:
        return None

    def _step(self) -> bool:
        # skip events that show nothing so playback keeps a steady pace on visible lines
        while self.pos < len(self.events):
            e = self.events[self.pos]
            self.pos += 1
            self.page.feed(e)
            if e.kind in ("say", "whisper", "mafia", "lover", "dead", "system", "death", "vote_result", "verdict_result", "phase", "god", "end"):
                break
        self._sync()
        if self.pos >= len(self.events):
            self.playing = False
            self._timer = 0
            self.page.st.paused = True
            self._sync()
            return False
        return True

    def _set_reveal(self, on: bool) -> None:
        self.reveal = on
        self.seek(self.pos)

    def _sync(self) -> None:
        self.scale.set_value(self.pos)
        self.play_btn.set_icon_name("media-playback-pause-symbolic" if self.playing else "media-playback-start-symbolic")
        self.play_btn.set_tooltip_text(_("Pause") if self.playing else _("Play"))
        self.where.set_label(f"{self.page.st.phase_title()}, {self.pos}/{len(self.events)}")
        self.page.pause_btn.set_visible(False)
        self.page.refresh()
