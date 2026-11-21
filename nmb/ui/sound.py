"""Playing the sound effects and the 소리 and 음량 controls.

Each platform plays through what it always has: GTK's media stream (GStreamer) on Linux and in the Flatpak,
the system's PlaySound on Windows, afplay on macOS. The files come from nmb/sound.py with the volume already in
the samples, so the result sounds the same everywhere. A burst of events is rate-limited (sound.Limiter).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from .. import sound  # noqa: E402
from ..i18n import _  # noqa: E402

if TYPE_CHECKING:
    from ..config import Settings


class Plays(Protocol):
    def play(self, path: Path, muted: bool = False) -> object: ...


class Backend:
    """Plays one WAV file without waiting for it."""

    def __init__(self) -> None:
        self.kind = "windows" if sys.platform == "win32" else "macos" if sys.platform == "darwin" else "gtk"
        self._live: set[Gtk.MediaFile] = set()  # kept until they end, or GTK stops them half way
        self._afplay = shutil.which("afplay") if self.kind == "macos" else None

    def play(self, path: Path, muted: bool = False) -> Gtk.MediaFile | None:
        if self.kind == "windows":
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            return None
        if self.kind == "macos" and self._afplay:
            subprocess.Popen([self._afplay, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return None
        media = Gtk.MediaFile.new_for_filename(str(path))
        media.set_muted(muted)
        self._live.add(media)
        media.connect("notify::ended", lambda m, _p: self._live.discard(m))
        media.connect("notify::error", lambda m, _p: self._live.discard(m))
        media.play()
        return media


class SoundPlayer:
    def __init__(self, settings: "Settings", backend: Plays | None = None, folder: Path | None = None):
        self.settings = settings
        self.backend = backend or Backend()
        self.folder = folder
        self.limiter = sound.Limiter()
        self.off = bool(os.environ.get("NMB_NO_SOUND"))  # smoke runs, screenshots and tests stay quiet
        self.listeners: list[Callable[[], None]] = []

    def prepare(self) -> None:
        """Writes the files of the current volume (run in the background at start, so the first sound is quick)."""
        try:
            for name in sound.SOUNDS:
                sound.path_for(name, self.settings.volume, self.folder)
        except OSError:
            pass  # play() tries again and turns sound off if it still cannot

    def play(self, name: str) -> None:
        if self.off or not self.settings.sound or not self.limiter.allow(name):
            return
        try:
            path = sound.path_for(name, self.settings.volume, self.folder)
            if path is not None:
                self.backend.play(path)
        except (OSError, RuntimeError):
            self.off = True  # no sound device or no cache: the game goes on without sound

    def set(self, on: bool | None = None, volume: float | None = None) -> None:
        if on is not None:
            self.settings.sound = on
        if volume is not None:
            self.settings.volume = round(max(0.0, min(1.0, volume)), 2)
        self.settings.save()
        for f in list(self.listeners):
            f()

    # ---- controls ------------------------------------------------------------------------------------------
    def controls(self) -> Gtk.Widget:
        """소리 with its switch and 음량 under it: for the menus of the lobby and the game."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_start=10, margin_end=6, margin_bottom=4)
        box.add_css_class("sound-controls")
        top = Gtk.Box(spacing=12)
        name = Gtk.Label(label=_("Sound"), xalign=0.0, hexpand=True)
        switch = Gtk.Switch(active=self.settings.sound, valign=Gtk.Align.CENTER)
        switch.update_property([Gtk.AccessibleProperty.LABEL], [_("Sound")])
        top.append(name)
        top.append(switch)
        scale = self.scale_widget()
        switch.connect("notify::active", lambda w, _p: self.set(on=w.get_active()))
        low = Gtk.Box(spacing=12)
        low.append(Gtk.Label(label=_("Volume"), xalign=0.0))
        low.append(scale)
        box.append(top)
        box.append(low)

        def follow() -> None:
            if switch.get_active() != self.settings.sound:
                switch.set_active(self.settings.sound)
            scale.set_sensitive(self.settings.sound)
            if abs(scale.get_value() - self.settings.volume) > 1e-6:
                scale.set_value(self.settings.volume)
        self.listeners.append(follow)
        box.connect("destroy", lambda *_a: follow in self.listeners and self.listeners.remove(follow))
        follow()
        return box

    def scale_widget(self) -> Gtk.Scale:
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        scale.set_value(self.settings.volume)
        scale.set_draw_value(False)
        scale.set_size_request(180, -1)
        scale.set_hexpand(True)
        scale.update_property([Gtk.AccessibleProperty.LABEL], [_("Volume")])
        scale.set_tooltip_text(_("Volume"))
        scale.connect("value-changed", lambda s: self._volume(s.get_value()))
        return scale

    def _volume(self, value: float) -> None:
        if abs(value - self.settings.volume) < 1e-6:
            return
        self.set(volume=value)
        self.play("say")  # hear the new level at once

    def button(self) -> Gtk.MenuButton:
        """The game header's sound button: its icon says on or off, its popover holds the controls."""
        btn = Gtk.MenuButton(tooltip_text=_("Sound"))
        pop = Gtk.Popover(child=self.controls())
        btn.set_popover(pop)

        def icon() -> None:
            btn.set_icon_name("audio-volume-high-symbolic" if self.settings.sound and self.settings.volume > 0
                              else "audio-volume-muted-symbolic")
        self.listeners.append(icon)
        btn.connect("destroy", lambda *_a: icon in self.listeners and self.listeners.remove(icon))
        icon()
        return btn
