"""The NeedMoreBench application: window, cream style, colour scheme, pages."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from .. import APP_ID, i18n  # noqa: E402
from ..config import Settings  # noqa: E402
from ..providers.base import ModelInfo  # noqa: E402
from ..providers.registry import Routes  # noqa: E402
from . import bg  # noqa: E402

HERE = Path(__file__).resolve().parent
SCHEMES = {"light": Adw.ColorScheme.FORCE_LIGHT, "dark": Adw.ColorScheme.FORCE_DARK, "system": Adw.ColorScheme.DEFAULT}


def load_css() -> None:
    provider = Gtk.CssProvider()
    provider.connect("parsing-error", _css_error)
    provider.load_from_path(str(HERE / "style.css"))
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    icons = Gtk.IconTheme.get_for_display(display) if display is not None else None
    data_icons = HERE.parent.parent / "data/icons"
    if icons is not None and data_icons.exists():
        icons.add_search_path(str(data_icons))


def _css_error(_p: Gtk.CssProvider, section: Gtk.CssSection, error: GLib.Error) -> None:
    loc = section.get_start_location()
    print(f"style.css:{loc.lines + 1}: {error.message}", file=sys.stderr)


def apply_scheme(name: str) -> None:
    Adw.StyleManager.get_default().set_color_scheme(SCHEMES.get(name, Adw.ColorScheme.FORCE_LIGHT))


class Window(Adw.ApplicationWindow):
    def __init__(self, app: "App"):
        super().__init__(application=app, title="NeedMoreBench")
        self.app = app
        self.set_default_size(1280, 820)
        self.set_size_request(860, 600)
        self.toasts = Adw.ToastOverlay()
        self.nav = Adw.NavigationView()
        self.toasts.set_child(self.nav)
        self.set_content(self.toasts)
        # sp grows with large text; px holds on macOS, where text is read at 72 dpi and 1100sp is only 825 px
        bp = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 1100px or max-width: 1100sp"))
        bp.connect("apply", lambda *_: self._narrow(True))
        bp.connect("unapply", lambda *_: self._narrow(False))
        self.add_breakpoint(bp)
        self.narrow = False

    def _narrow(self, on: bool) -> None:
        self.narrow = on
        page = self.nav.get_visible_page()
        if page is not None and hasattr(page, "narrow"):
            page.narrow(on)

    def push(self, page: Adw.NavigationPage) -> None:
        self.nav.push(page)
        if hasattr(page, "narrow"):
            page.narrow(self.narrow)

    def show_only(self, page: Adw.NavigationPage) -> None:
        self.nav.replace([page])
        if hasattr(page, "narrow"):
            page.narrow(self.narrow)

    def toast(self, text: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))


class App(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.settings = Settings.load()
        i18n.setup(self.settings.language)
        from .sound import SoundPlayer
        self.sound = SoundPlayer(self.settings)  # soft effects, 소리 and 음량 in the menus and Settings
        self.window: Window | None = None
        from ..providers.health import Health
        from ..store import home
        self.health = Health(home() / "health.json")  # what the app learned about models, kept across restarts
        self.routes = self._routes()
        self.statuses: dict[str, tuple[str, str]] = {}
        self.loading = False
        self._again = False  # a refresh asked for while one was running
        self._listeners: list[Callable[[], None]] = []
        self.sessions: list[Any] = []
        self.bench: Any = None  # the bench run being played (nmb.bench_run.BenchRunner)
        self._bench_listeners: list[Callable[[], None]] = []
        self._bench_pending = False
        # pages that are not finished stay hidden so no visible button leads nowhere
        self.settings_ready = True
        self.standings_ready = True
        self.play_ready = True
        self.god_ready = True
        self.complex_ready = True
        GLib.set_application_name("NeedMoreBench")

    def _routes(self) -> Routes:
        return Routes.standard(self.settings.allow_training, self.settings.lmstudio_url, health=self.health)

    @property
    def models(self) -> list[ModelInfo]:
        """One entry per model, its route chosen by the user's order among the routes that work now."""
        return self.routes.entries()

    def models_changed(self) -> None:
        """Something learned about availability: lobby rows and open pickers show it."""
        for fn in list(self._listeners):
            fn()

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        apply_scheme(self.settings.scheme)
        load_css()
        Gtk.Window.set_default_icon_name(APP_ID)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = Window(self)
            from .home import HomePage
            self.window.nav.add(HomePage(self))
            self.refresh_models()
            self._first_run()
            self._resume_bench()
            import threading
            threading.Thread(target=self.sound.prepare, daemon=True).start()  # the files, before the first sound
        self.window.present()

    # ---- bench runs: played off the main loop, kept in the settings, resumed after a restart ------------
    def on_bench(self, fn: Callable[[], None]) -> None:
        self._bench_listeners.append(fn)

    def start_bench(self, run: Any) -> None:
        from ..bench_run import BenchRunner
        if self.bench is not None and self.bench.alive:
            return
        self.bench = BenchRunner(run, self.routes, self._bench_saved, self._bench_changed,
                                 offline=bool(os.environ.get("NMB_OFFLINE")))
        self.bench.start()
        self._notify_bench()

    def stop_bench(self) -> None:
        if self.bench is not None:
            self.bench.stop()
        self._notify_bench()

    def bench_run(self) -> Any:
        """The current run: the one playing, or the last one kept in the settings."""
        if self.bench is not None:
            return self.bench.run
        if self.settings.bench.get("plan"):
            from ..bench import Run
            return Run.from_json(self.settings.bench)
        return None

    def _resume_bench(self) -> None:
        if self.settings.bench.get("running") and self.settings.bench.get("plan"):
            from ..bench import Run
            self.start_bench(Run.from_json(self.settings.bench))

    def _bench_saved(self, run: Any) -> None:
        data = run.to_json()  # made on the worker, where the run changes; saved on the main loop

        def save() -> bool:
            self.settings.bench = data
            self.settings.save()
            return False
        GLib.idle_add(save)

    def _bench_changed(self) -> None:
        if not self._bench_pending:  # phase changes of three games come fast; one redraw per main-loop turn
            self._bench_pending = True
            GLib.idle_add(self._notify_bench)

    def _notify_bench(self) -> bool:
        self._bench_pending = False
        for fn in list(self._bench_listeners):
            fn()
        return False

    # ---- models and route status, loaded off the main loop ------------------------------------------------
    def on_models(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def refresh_models(self) -> None:
        """Load every route's list. A refresh asked for during a load runs right after it, so a key stored
        while the first load ran is never lost."""
        if os.environ.get("NMB_OFFLINE"):
            return
        if self.loading:
            self._again = True
            return
        self.loading = True
        routes = self.routes

        async def load() -> dict[str, tuple[str, str]]:
            _models, statuses = await asyncio.gather(routes.models(refresh=True), routes.statuses())
            return statuses

        def done(res: dict[str, tuple[str, str]] | None, err: BaseException | None) -> None:
            self.loading = False
            if res is not None:
                self.statuses = res
                self._report_routes(routes)
            if self._again:
                self._again = False
                self.refresh_models()
            self.models_changed()
        bg.run(load, done)

    def _report_routes(self, routes: Routes) -> None:
        """N1: a quiet line per route of models received against models reachable, and a toast for a route that
        returned nothing or failed, so a missing list is seen the day it happens."""
        from ..providers.base import ROUTE_LABEL
        counts = routes.counts()
        print("routes: " + ", ".join(f"{n} {got}/{shown}" for n, (got, shown) in counts.items()), file=sys.stderr, flush=True)
        lost = [n for n, (got, shown) in counts.items() if shown < got]
        if lost:
            print(f"routes: models not reachable on {', '.join(lost)}", file=sys.stderr, flush=True)
        broken = routes.broken()
        if broken and self.window is not None:
            from ..i18n import _
            self.window.toast(_("No models from {routes}").format(routes=", ".join(ROUTE_LABEL.get(n, n) for n in broken)))

    def rebuild_routes(self) -> None:
        """After a key, the training switch or the LM Studio address changed: what a key or setting may have
        fixed is forgotten and checked again."""
        self.health.clear(("auth", "credit", "policy", "nokey"))
        self.routes = self._routes()
        self.refresh_models()

    def _first_run(self) -> None:
        """Keys found on this machine go into the keyring once, tested first and never shown."""
        if self.settings.first_run_done or os.environ.get("NMB_OFFLINE"):
            return
        from ..firstrun import import_keys

        def done(found: Any, err: BaseException | None) -> None:
            self.settings.first_run_done = True
            self.settings.first_run = [{"route": f.route, "where": f.where, "reason": f.reason, "stored": f.stored}
                                       for f in (found or [])]
            self.settings.save()
            if found and any(f.stored for f in found):
                self.rebuild_routes()
        bg.run(lambda: import_keys(), done)

    def play_sound(self, name: str) -> None:
        self.sound.play(name)

    def set_language(self, code: str) -> None:
        """Pages build their text when made, so the lobby is made again in the new language."""
        i18n.setup(code)
        if self.window is None:
            return
        from .home import HomePage
        self._listeners = [f for f in self._listeners if not isinstance(getattr(f, "__self__", None), HomePage)]
        self.window.show_only(HomePage(self))

    def set_scheme(self, name: str) -> None:
        self.settings.scheme = name
        self.settings.save()
        apply_scheme(name)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv
    if "--smoke" in argv:  # CI on each system: render the main pages to pictures and exit
        from .smoke import run
        return run(argv)
    app = App()
    return app.run(argv)


def snapshot_png(widget: Gtk.Widget, path: Path) -> tuple[int, int]:
    """Render a widget at its real size into a PNG (screenshots without the user's display)."""
    gi.require_version("Graphene", "1.0")
    from gi.repository import Graphene
    w, h = widget.get_width(), widget.get_height()
    paintable = Gtk.WidgetPaintable.new(widget)
    snap = Gtk.Snapshot()
    paintable.snapshot(snap, w, h)
    node = snap.to_node()
    native = widget.get_native()
    if node is None or native is None:
        raise RuntimeError("nothing to render")
    rect = Graphene.Rect().init(0, 0, w, h)
    tex = native.get_renderer().render_texture(node, rect)
    path.parent.mkdir(parents=True, exist_ok=True)
    tex.save_to_png(str(path))
    return w, h
