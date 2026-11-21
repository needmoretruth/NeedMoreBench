"""Smoke run of an installed or packaged app, for CI on each system:

    NeedMoreBench --smoke <out folder> [--record <game.nmb.jsonl>]

Opens the real window with empty settings, no keys and no network, renders the lobby, a replay of the recorded game
and the Settings connections page in English and in Korean, saves each as a PNG at the window's real size and
exits 0. Exits 1 when a page fails to render, a picture comes out blank, one picture takes longer than PER_SHOT, or
(in a built app) the shipped opencode is missing, does not run, or the Settings row does not report it.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

SIZE = (1280, 820)
PER_SHOT = 150  # seconds for one picture; the Intel Mac runner needed 84 for Settings


def _args(argv: list[str]) -> tuple[Path, Path | None]:
    out = Path(argv[argv.index("--smoke") + 1]) if argv.index("--smoke") + 1 < len(argv) else Path("smoke")
    record = Path(argv[argv.index("--record") + 1]) if "--record" in argv else None
    return out, record


class _NoKeys:
    """An empty key store that keeps nothing."""

    def get_password(self, _service: str, _route: str) -> None:
        return None

    def set_password(self, _service: str, _route: str, _key: str) -> None:
        return None

    def delete_password(self, _service: str, _route: str) -> None:
        return None


def blank(path: Path) -> bool:
    """A picture with almost no distinct colours is an empty window, not a rendered page."""
    from gi.repository import Gdk
    tex = Gdk.Texture.new_from_filename(str(path))
    data, _stride = Gdk.TextureDownloader.new(tex).download_bytes()
    raw = data.get_data() or b""
    step = 4 * 97  # a sample of pixels across the picture
    colours = {raw[i:i + 3] for i in range(0, len(raw) - 3, step)}
    return len(colours) < 40


def packaged() -> bool:
    """A built app (PyInstaller bundle or Flatpak), which must carry opencode; a source checkout need not."""
    return bool(getattr(sys, "frozen", False) or os.environ.get("FLATPAK_ID"))


def check_opencode(say: Callable[[str], None]) -> str | None:
    """The shipped opencode is where the app looks and runs here (signature, quarantine, permissions): the
    failure, or None."""
    import subprocess
    import time

    from ..providers.opencode import NO_WINDOW, bundled, server_executable
    exe = bundled()
    if exe is None:
        return "opencode is not in the app" if packaged() else None
    if server_executable() != exe:
        return f"NMB's server would not run the shipped opencode: {server_executable()}"
    t = time.monotonic()
    try:
        p = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=180, check=False, **NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"the shipped opencode did not run: {e!r}"
    say(f"smoke: opencode {p.stdout.strip() or p.stderr.strip()[:200]} at {exe} in {time.monotonic() - t:.1f} s")
    return None if p.returncode == 0 else f"the shipped opencode exited with {p.returncode}"


def run(argv: list[str]) -> int:
    out, record = _args(argv)
    out.mkdir(parents=True, exist_ok=True)
    out = out.resolve()
    tmp = Path(tempfile.mkdtemp(prefix="nmb-smoke-"))
    os.environ["NMB_OFFLINE"] = "1"
    os.environ["NMB_CONFIG"] = str(tmp / "config")
    os.environ["NMB_HOME"] = str(tmp / "data")
    os.environ["NMB_NO_SOUND"] = "1"

    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    gi.require_version("Graphene", "1.0")
    from gi.repository import Gio, GLib

    from .. import keys
    from ..config import Settings
    Settings(language="en", first_run_done=True).save()
    keys._backend = _NoKeys()  # the pictures show a new user's screens and never read this computer's keys
    from .app import App, Window, snapshot_png

    failures: list[str] = []
    saved: list[Path] = []
    log = out / "smoke.log"
    log.write_text("", encoding="utf-8")

    def say(line: str) -> None:
        """To the console and to smoke.log beside the pictures (a windowed Windows app has no console)."""
        if sys.stdout is not None:
            print(line, flush=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def lobby(win: Window) -> None:
        from .home import HomePage
        win.show_only(HomePage(win.app))

    def replay(win: Window) -> None:
        from ..store import load
        from .replay import Replay
        if record is None:
            raise RuntimeError("no --record given")
        r = Replay(load(record))
        win.show_only(r.page)
        says = [i for i, e in enumerate(r.events) if e.kind == "say"]
        r.seek(says[min(8, len(says) - 1)] + 1 if says else len(r.events))

    def settings(win: Window) -> None:
        from .home import HomePage
        from .settings import SettingsDialog
        win.show_only(HomePage(win.app))
        dlg = SettingsDialog(win.app)
        dlg.present(win)
        dlg.set_visible_page_name("connections")
        row = dlg.status_rows["opencode"].get_subtitle() or ""
        say(f"smoke: OpenCode row 「{row.splitlines()[0] if row else ''}」")
        from .settings import bundled_opencode
        if packaged() and not (bundled_opencode() and "OpenCode" in row.splitlines()[0]):
            failures.append("settings: the OpenCode row does not report the opencode shipped in the app")

    def in_language(lang: str, setup: Callable[[Window], None]) -> Callable[[Window], None]:
        def go(win: Window) -> None:
            from .. import i18n
            i18n.setup(lang)
            setup(win)
        return go

    broken = check_opencode(say)
    if broken:
        failures.append(broken)

    pages: list[tuple[str, Callable[[Window], None]]] = [("lobby", lobby)] + ([("replay", replay)] if record else [])
    pages.append(("settings", settings))
    shots = [(f"{name}-{lang}", in_language(lang, fn)) for lang in ("en", "ko") for name, fn in pages]

    class SmokeApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.set_flags(Gio.ApplicationFlags.NON_UNIQUE)  # never reach a copy the user has open

        def do_activate(self) -> None:
            from gi.repository import Gtk
            # pages are pictured at rest: on macOS the Settings dialog was caught halfway through fading in
            Gtk.Settings.get_default().set_property("gtk-enable-animations", False)
            queue = list(shots)
            self.hold()
            # each picture has its own budget: a slow runner (the Intel Mac VM renders without a GPU) is not a hang
            current: dict[str, Any] = {"name": "start", "since": time.monotonic()}

            def watchdog() -> bool:
                if time.monotonic() - current["since"] > PER_SHOT:
                    failures.append(f"{current['name']}: timed out after {PER_SHOT} s")
                    self.quit()
                    return False
                return True
            GLib.timeout_add_seconds(1, watchdog)

            def next_shot() -> bool:
                if self.window is not None:  # a fresh window per shot: a swapped page under Xvfb gets no frames
                    self.window.destroy()
                if not queue:
                    self.release()
                    self.quit()
                    return False
                name, setup = queue.pop(0)
                current.update(name=name, since=time.monotonic())
                win = Window(self)
                win.set_default_size(*SIZE)
                self.window = win
                try:
                    setup(win)
                except Exception as e:  # noqa: BLE001  reported and counted, the other shots still run
                    failures.append(f"{name}: {e!r}")
                    GLib.timeout_add(100, next_shot)
                    return False
                built = time.monotonic() - current["since"]
                win.present()
                GLib.timeout_add(1500, lambda: (shoot(name, built=built), False)[1])
                return False

            def shoot(name: str, tries: int = 0, built: float = 0.0) -> None:
                path = out / f"{name}.png"
                t = time.monotonic()
                try:
                    w, h = snapshot_png(self.window, path)
                except RuntimeError as e:
                    if tries < 10:
                        GLib.timeout_add(400, lambda: (shoot(name, tries + 1, built), False)[1])
                        return
                    failures.append(f"{name}: {e}")
                else:
                    renderer = type(self.window.get_renderer()).__name__ if self.window.get_renderer() else "-"
                    took = time.monotonic() - current["since"]
                    # where the time goes: building the page, then the wait, then drawing the picture itself
                    say(f"smoke: {path} {w}x{h} renderer {renderer}, {took:.1f} s (page {built:.1f} s, "
                        f"picture {time.monotonic() - t:.1f} s)")
                    saved.append(path)
                    if blank(path):
                        failures.append(f"{name}: blank picture")
                GLib.timeout_add(100, next_shot)

            GLib.timeout_add(300, next_shot)

    SmokeApp().run([sys.argv[0]])
    for f in failures:
        say(f"smoke failed: {f}")
    ok = not failures and len(saved) == len(shots)
    say(f"smoke: {len(saved)}/{len(shots)} pictures, {'ok' if ok else 'FAILED'}")
    return 0 if ok else 1
