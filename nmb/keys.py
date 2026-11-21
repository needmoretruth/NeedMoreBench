"""API keys in the operating system's own key store through the `keyring` package: Windows Credential Manager,
the macOS Keychain, the Secret Service (GNOME keyring, KWallet) on Linux. Never printed, logged or saved elsewhere.

Reads are made reliable for a game, where several threads and async calls ask for keys at once: every access to
the key store goes through one lock, each route's key is read once per app start and kept in memory (Settings
changes it through put and forget), and a failing read is tried once more. A read that still fails raises
KeyringError ("could not read the keyring"), never "no key": a seat whose key is stored was once swapped out
mid-game because a concurrent read came back empty.

Keys stored by earlier builds under the libsecret schema `org.needmorebench.NeedMoreBench.Key` are copied over
the first time a route is read. The old item is left in place so an older build on the same machine keeps
working; removing a key in Settings removes both, so a removed key never comes back.

First run (nmb.firstrun) also looks at the standard environment variables and at opencode's own login file,
tests each candidate with the cheapest call and stores the ones that work.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .i18n import _
from .providers.base import ProviderError

SERVICE = "NeedMoreBench"
ROUTES = ("openrouter", "anthropic", "venice")
ENV = {"anthropic": "ANTHROPIC_API_KEY", "openrouter": "OPENROUTER_API_KEY", "venice": "VENICE_API_KEY"}
OLD_SCHEMA = "org.needmorebench.NeedMoreBench.Key"

_lock = threading.RLock()
_cache: dict[str, str | None] = {}  # route -> key, or None when the store answered that there is none
_backend: Any = None  # tests put a fake here; otherwise the keyring module once it has a usable backend


class KeyringError(ProviderError):
    """The key store did not answer. Not the same as no key: the seat is not swapped for it."""

    def __init__(self, route: str):
        super().__init__("keyring", _("Could not read the keyring"))
        self.route = route


def _keyring() -> Any:
    """The keyring module when a usable backend exists, else None (a Linux session without a key store)."""
    if _backend is not None:
        return _backend
    try:
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            return None
        return keyring
    except Exception:  # noqa: BLE001  a broken backend means no key store, never a crash
        return None


def available() -> bool:
    return _keyring() is not None


def _read(kr: Any, route: str) -> str | None:
    """One read with one retry; KeyringError when both fail. An empty answer is asked once more too: read from
    many threads at once, the Secret Service backend answered empty for a stored key (1 in 300 reads)."""
    failed = False
    for attempt in range(2):
        try:
            key = kr.get_password(SERVICE, route)
        except Exception:  # noqa: BLE001  a busy or locked store: once more, then say so
            failed = True
            if attempt == 0:
                time.sleep(0.2)
            continue
        if key:
            return key
        failed = False
    if failed:
        raise KeyringError(route)
    return None


def get(route: str) -> str | None:
    """The route's key, None when none is stored. Raises KeyringError when the store could not be read."""
    with _lock:
        if route in _cache:
            return _cache[route]
        kr = _keyring()
        if kr is None:
            return None  # no key store and no key given in this session
        key = _read(kr, route) or _migrate(route, kr)
        _cache[route] = key
        return key


def has(route: str) -> bool:
    """Whether a key is stored, for Settings; a store that cannot be read counts as no key there."""
    try:
        return bool(get(route))
    except KeyringError:
        return False


def put(route: str, key: str) -> bool:
    """Store the key. Without a key store it is kept in memory until the app closes, so the person can still play."""
    key = key.strip()
    with _lock:
        kr = _keyring()
        if not key:
            return False
        if kr is None:
            _cache[route] = key
            return True
        try:
            kr.set_password(SERVICE, route, key)
            ok = _read(kr, route) == key
        except Exception:  # noqa: BLE001
            ok = False
        _cache.pop(route, None)
        if ok:
            _cache[route] = key
        return ok


def forget(route: str) -> None:
    with _lock:
        kr = _keyring()
        if kr is not None:
            try:
                kr.delete_password(SERVICE, route)
            except Exception:  # noqa: BLE001  nothing stored
                pass
        schema = _old_schema()
        if schema is not None:
            try:
                from gi.repository import Secret
                Secret.password_clear_sync(schema, {"route": route}, None)
            except Exception:  # noqa: BLE001
                pass
        _cache[route] = None


def reload() -> None:
    """Forget what was read, so the next read asks the store again (keys kept only in memory stay)."""
    with _lock:
        if _keyring() is not None:
            _cache.clear()


def _old_schema() -> Any:
    """The libsecret schema of builds before the keyring package; None where libsecret is not installed."""
    if sys.platform in ("win32", "darwin") or _backend is not None:
        return None
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
        return Secret.Schema.new(OLD_SCHEMA, Secret.SchemaFlags.NONE, {"route": Secret.SchemaAttributeType.STRING})
    except Exception:  # noqa: BLE001
        return None


def _migrate(route: str, kr: Any) -> str | None:
    """Copy a key an earlier build stored. Returns the key when one was moved (called under the lock)."""
    schema = _old_schema()
    if schema is None:
        return None
    try:
        from gi.repository import Secret
        old = Secret.password_lookup_sync(schema, {"route": route}, None)
    except Exception:  # noqa: BLE001
        return None
    if not old:
        return None
    try:
        kr.set_password(SERVICE, route, old)
    except Exception:  # noqa: BLE001  the copy failed: use the old key now, try the copy again next start
        pass
    return old


def opencode_auth_file() -> Path:
    """opencode's login file. opencode keeps its data under XDG_DATA_HOME or ~/.local/share on every system."""
    from .providers.opencode import host_xdg
    return host_xdg("XDG_DATA_HOME", ".local", "share") / "opencode" / "auth.json"


def found_on_machine() -> dict[str, list[tuple[str, str]]]:
    """Candidate keys per route as (where it came from, key): the standard environment variables, then keys the
    user gave opencode. The caller tests them; nothing is printed."""
    out: dict[str, list[tuple[str, str]]] = {r: [] for r in ROUTES}
    for route, var in ENV.items():
        value = os.environ.get(var, "").strip()
        if value:
            out[route].append((var, value))
    try:
        auth = json.loads(opencode_auth_file().read_text(encoding="utf-8"))
        for route in ROUTES:
            k = (auth.get(route) or {}).get("key")
            if isinstance(k, str) and k.strip():
                out[route].append(("opencode", k.strip()))
    except (OSError, ValueError, AttributeError):
        pass
    for route in ROUTES:  # same key from two places: test it once
        seen: set[str] = set()
        out[route] = [(w, k) for w, k in out[route] if not (k in seen or seen.add(k))]
    return out
