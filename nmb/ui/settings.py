"""Settings: connections with their status and keys, the training switch, LM Studio,
the colour scheme and the interface language. Keys go straight into the keyring after a test call; the dialog
never shows a stored key, only whether one is there.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from .. import i18n, keys  # noqa: E402
from ..i18n import _  # noqa: E402
from ..providers.base import STATUS_TEXT  # noqa: E402
from . import bg  # noqa: E402

ROUTES = [("opencode", "OpenCode"), ("anthropic", "Anthropic"), ("venice", "Venice"), ("openrouter", "OpenRouter"), ("lmstudio", "LM Studio")]
KEYED = ("anthropic", "venice", "openrouter")
SCHEMES = [("light", "Light"), ("dark", "Dark"), ("system", "Follow system")]
WHERE = {"keyring": "Keyring"}
# For someone with no key yet: what each route offers and where its key (or program) comes from.
GUIDE = [("opencode", "Free models with a daily limit, no key needed", "Download", "https://opencode.ai"),
         ("openrouter", "Free models with a daily limit, and paid models", "Make a key", "https://openrouter.ai/keys"),
         ("anthropic", "Claude models, paid", "Make a key", "https://platform.claude.com/settings/keys"),
         ("venice", "Open models, paid", "Make a key", "https://venice.ai/settings/api"),
         ("lmstudio", "Models on this computer, free", "Download", "https://lmstudio.ai")]
LINKS = {name: url for name, _s, _b, url in GUIDE}
STORES = {"win32": "Windows Credential Manager", "darwin": "macOS Keychain", "linux": "the keyring"}  # where keys live


def _lmstudio_installed() -> bool:
    from ..providers import lmstudio_ctl
    return lmstudio_ctl.home() is not None


def status_text(reason: str, text: str) -> str:
    """The route's own line when it has one (credit left, model count), else the plain status."""
    return text or _(STATUS_TEXT.get(reason, reason))


class SettingsDialog(Adw.PreferencesDialog):
    def __init__(self, app: Any):
        super().__init__(title=_("Settings"), search_enabled=False)
        self.app = app
        self.status_rows: dict[str, Adw.ActionRow] = {}
        self.add(self._general())
        self.add(self._connections())
        self._show_statuses()
        app.on_models(self._show_statuses)
        self.connect("closed", lambda *_a: self._forget_listener())

    def _forget_listener(self) -> None:
        if self._show_statuses in self.app._listeners:
            self.app._listeners.remove(self._show_statuses)

    # ---- general ---------------------------------------------------------------------------------------
    def _general(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage(title=_("General"), icon_name="preferences-system-symbolic", name="general")
        look = Adw.PreferencesGroup()
        scheme = Adw.ComboRow(title=_("Style"), model=Gtk.StringList.new([_(t) for _n, t in SCHEMES]))
        names = [n for n, _t in SCHEMES]
        scheme.set_selected(names.index(self.app.settings.scheme) if self.app.settings.scheme in names else 0)
        scheme.connect("notify::selected", lambda r, _p: self.app.set_scheme(names[r.get_selected()]))
        look.add(scheme)
        langs = [("", _("Follow system"))] + [(code, name) for code, name in i18n.LANGS.items()]
        self.lang_title = _("Interface language")
        lang = Adw.ComboRow(title=self.lang_title, model=Gtk.StringList.new([t for _c, t in langs]))
        codes = [c for c, _t in langs]
        lang.set_selected(codes.index(self.app.settings.language) if self.app.settings.language in codes else 0)
        lang.connect("notify::selected", lambda r, _p: self._language(codes[r.get_selected()]))
        look.add(lang)
        page.add(look)
        play = Adw.PreferencesGroup(title=_("Watching"))
        delay = Adw.SpinRow.new_with_range(0, 6, 0.2)
        delay.set_digits(1)
        delay.set_title(_("Reading time"))
        delay.set_subtitle(_("Seconds between public lines while watching"))
        delay.set_value(self.app.settings.delay)
        delay.connect("notify::value", lambda r, _p: self._save("delay", round(r.get_value(), 1)))
        play.add(delay)
        page.add(play)
        return page

    def _language(self, code: str) -> None:
        self.app.settings.language = code
        self.app.settings.save()
        self.app.set_language(code)
        self.close()

    def _save(self, name: str, value: Any) -> None:
        setattr(self.app.settings, name, value)
        self.app.settings.save()

    # ---- connections -------------------------------------------------------------------------------------
    def _connections(self) -> Adw.PreferencesPage:
        """One list: each route with its state in words, what it offers, and its one action (a key to paste, a
        site to make the key, a program to download or start). Free routes first."""
        page = Adw.PreferencesPage(title=_("Connections"), icon_name="network-server-symbolic", name="connections")
        routes = Adw.PreferencesGroup(title=_("Connections"), description=self._store_words())
        for name, sub, _b, url in GUIDE:
            title = dict(ROUTES)[name]
            if name in KEYED:
                saved = keys.has(name)
                row: Any = Adw.ExpanderRow(title=title, expanded=not saved)
                entry = Adw.PasswordEntryRow(title=self._key_title(name, saved))
                entry.set_show_apply_button(True)
                entry.connect("apply", lambda e, n=name: self._store_key(n, e))
                forget = self._button(_("Remove"), lambda b, n=name: self._forget_key(n, b))
                forget.set_visible(saved)
                entry.add_suffix(forget)
                entry.forget = forget
                row.add_row(entry)
                row.make_btn = self._button(_("Make a key"), lambda b, u=url: self._open(b, u))
                row.make_btn.set_visible(not saved)
                row.add_suffix(row.make_btn)
            else:
                row = Adw.ActionRow(title=title)
                row.start_btn = self._button(_("Start"), lambda *_a, n=name: self._start_opencode() if n == "opencode" else self._start_lmstudio())
                row.add_suffix(row.start_btn)
                row.get_btn = self._button(_("Download"), lambda b, u=url: self._open(b, u))
                row.add_suffix(row.get_btn)
            row.offer = _(sub)
            row.set_subtitle_lines(2)
            self.status_rows[name] = row
            routes.add(row)
        refresh = self._button(_("Check again"), lambda *_a: self.app.refresh_models())
        routes.set_header_suffix(refresh)
        page.add(routes)

        rules = Adw.PreferencesGroup(title=_("Models"))
        train = Adw.SwitchRow(title=_("Allow models that train on prompts"),
                              subtitle=_("Off: such models are hidden and OpenRouter is asked not to keep prompts"),
                              active=self.app.settings.allow_training)
        train.connect("notify::active", lambda r, _p: self._training(r.get_active()))
        rules.add(train)
        lm = Adw.EntryRow(title=_("LM Studio address"), text=self.app.settings.lmstudio_url, show_apply_button=True)
        lm.connect("apply", lambda e: self._lmstudio_url(e.get_text()))
        rules.add(lm)
        page.add(rules)

        if self.app.settings.first_run:
            found = Adw.PreferencesGroup(title=_("Found on first start"),
                                         description=_("Keys this computer already had, tested once. Working ones went into the keyring."))
            for f in self.app.settings.first_run:
                where = WHERE.get(f.get("where", ""), f.get("where", ""))
                row = Adw.ActionRow(title=f"{dict(ROUTES).get(f.get('route', ''), f.get('route', ''))}, {_(where)}",
                                    subtitle=_(STATUS_TEXT.get(f.get("reason", ""), f.get("reason", ""))))
                if f.get("stored"):
                    row.add_suffix(Gtk.Image.new_from_icon_name("emblem-ok-symbolic"))
                found.add(row)
            page.add(found)
        return page

    @staticmethod
    def _store_words() -> str:
        if keys.available():
            store = _(STORES.get(sys.platform, STORES["linux"]))
            return (_("To play, connect at least one. Keys stay in {store} on this computer and are never shown again.")
                    .format(store=store))
        return _("This computer has no keyring, so a key you paste is kept only until the app closes. "
                 "To keep keys, install GNOME Keyring or KWallet and sign in again.")

    def _open(self, widget: Gtk.Widget, url: str) -> None:
        win = widget.get_root()
        Gtk.UriLauncher.new(url).launch(win if isinstance(win, Gtk.Window) else None, None, None, None)

    @staticmethod
    def _key_title(route: str, saved: bool) -> str:
        name = dict(ROUTES)[route]
        return _("{route} key saved").format(route=name) if saved else _("Paste the {route} key").format(route=name)

    @staticmethod
    def _button(text: str, cb: Any) -> Gtk.Button:
        b = Gtk.Button(label=text, valign=Gtk.Align.CENTER)
        b.add_css_class("flat")
        b.connect("clicked", cb)
        return b

    def _show_statuses(self) -> None:
        st = self.app.statuses
        for name, row in self.status_rows.items():
            reason, text = st.get(name, ("", ""))
            if self.app.loading and name not in st:
                state = _("Checking")
            elif not reason and name in KEYED and not keys.has(name):
                reason, state = "nokey", status_text("nokey", "")
            elif not reason and name in ("opencode", "lmstudio"):  # not checked (offline): what is on this computer
                from ..providers.opencode import executable
                reason = "off" if (executable() if name == "opencode" else _lmstudio_installed()) else "missing"
                state = status_text(reason, "")
            else:
                state = status_text(reason, text) if reason else ""
            installed = name != "lmstudio" or _lmstudio_installed()
            if name == "lmstudio" and reason == "off" and not installed:
                state = status_text("missing", "")
            row.set_subtitle(f"{state}\n{row.offer}" if state and reason != "ok" else state or row.offer)
            btn = getattr(row, "start_btn", None)
            if btn is not None:
                btn.set_visible(reason == "off" and installed)
            get = getattr(row, "get_btn", None)
            if get is not None:
                get.set_visible(reason == "missing" or not installed)

    def _store_key(self, route: str, entry: Adw.PasswordEntryRow) -> None:
        key = entry.get_text().strip()
        if not key:
            return
        entry.set_sensitive(False)
        from ..firstrun import test_key

        def done(res: tuple[str, str] | None, err: BaseException | None) -> None:
            entry.set_sensitive(True)
            entry.set_text("")
            reason, text = res if res else ("network", str(err or ""))
            if reason in ("ok", "credit") and keys.put(route, key):
                entry.forget.set_visible(True)
                entry.set_title(self._key_title(route, True))
                self.status_rows[route].make_btn.set_visible(False)
                self.add_toast(Adw.Toast(title=_("Saved. {status}").format(status=status_text(reason, text)), timeout=4))
                self.app.rebuild_routes()
            else:
                self.add_toast(Adw.Toast(title=status_text(reason, text), timeout=5))
        bg.run(lambda: test_key(route, key), done)

    def _forget_key(self, route: str, btn: Gtk.Button) -> None:
        keys.forget(route)
        btn.set_visible(False)
        entry = btn.get_ancestor(Adw.PasswordEntryRow)
        if entry is not None:
            entry.set_title(self._key_title(route, False))
        self.status_rows[route].make_btn.set_visible(True)
        self.app.rebuild_routes()

    def _training(self, on: bool) -> None:
        self._save("allow_training", on)
        self.app.rebuild_routes()

    def _lmstudio_url(self, url: str) -> None:
        self._save("lmstudio_url", url.strip() or "http://127.0.0.1:1234/v1")
        self.app.rebuild_routes()

    def _start_opencode(self) -> None:
        """Only when the user's service is down (never restart a running one)."""
        from ..providers.opencode import NO_WINDOW, executable
        exe = executable()

        async def start() -> int:
            p = await asyncio.create_subprocess_exec(exe or "opencode", "service", "start", stdout=asyncio.subprocess.DEVNULL,
                                                     stderr=asyncio.subprocess.DEVNULL, **NO_WINDOW)
            return await asyncio.wait_for(p.wait(), 30)

        if self.app.statuses.get("opencode", ("",))[0] != "off" or exe is None:
            return
        bg.run(start, lambda _r, _e: self.app.rebuild_routes())

    def _start_lmstudio(self) -> None:
        from ..providers import lmstudio_ctl

        async def start() -> tuple[bool, str]:
            return await asyncio.to_thread(lmstudio_ctl.start_server)

        def done(res: tuple[bool, str] | None, err: BaseException | None) -> None:
            if res and not res[0]:
                self.add_toast(Adw.Toast(title=res[1] or _("LM Studio did not start"), timeout=5))
            self.app.rebuild_routes()
        bg.run(start, done)
