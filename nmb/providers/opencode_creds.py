"""What NMB's own opencode server needs to call the person's other opencode models (audit AA1/AB1).

Paid Zen models and the person's other opencode providers (phala, Venice and the rest) went through the person's
server's text endpoint, which returns no reasoning. NMB's server can call them too when it has their sign-in, so
this module hands it exactly that and nothing else:
- the person's `provider` definitions from their opencode settings (address, package, models), with no other part
  of their settings (no instructions, agents, plugins, MCP servers or permissions);
- the stored API keys of those providers from opencode's auth file, as each provider's `apiKey` option;
- for Zen, the access token of the active OpenCode login, read from opencode's database opened read-only.
Read-only throughout. A login of the refreshing kind (`oauth`) is never handed over: NMB's server would refresh
it and the person's opencode would lose its login, so such a provider stays on the person's server and the seat
row says so. The keys travel only in the child's environment; they are never written to a file or printed.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

ZEN = "opencode"
GO = "opencode-go"  # served by Go's own API (opencode_direct); never through NMB's server
# opencode's own settings parts that may not reach NMB's server: only `provider` (and the providers' on/off lists)
KEEP = ("provider", "disabled_providers", "enabled_providers")
_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.S)


def jsonc(text: str) -> dict[str, Any]:
    """opencode.jsonc: JSON with comments and trailing commas."""
    def keep(m: re.Match[str]) -> str:
        return m.group(0) if m.group(0).startswith('"') else ""
    plain = _TOKEN.sub(keep, text)
    plain = re.sub(r",(\s*[}\]])", r"\1", plain)
    d = json.loads(plain)
    return d if isinstance(d, dict) else {}


def _settings_file(folder: Path) -> Path | None:
    for name in ("opencode.jsonc", "opencode.json", "config.json"):
        if (folder / name).is_file():
            return folder / name
    return None


def _read_json(path: Path | None, parse: Callable[[str], dict[str, Any]] = jsonc) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        return parse(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Signins:
    """The sign-ins NMB's server may use, read fresh on each call (the login token changes)."""

    def __init__(self, config_dir: Callable[[], Path], auth_file: Callable[[], Path],
                 login: Callable[[], str | None]):
        self._config_dir, self._auth_file, self._login = config_dir, auth_file, login

    def config(self) -> dict[str, Any]:
        """The extra settings for NMB's server: provider definitions with their keys. Never logged."""
        mine = _read_json(_settings_file(self._config_dir()))
        out: dict[str, Any] = {k: mine[k] for k in KEEP if k in mine}
        providers: dict[str, Any] = {pid: dict(v) for pid, v in (out.get("provider") or {}).items()
                                     if isinstance(v, dict)}
        auth = _read_json(self._auth_file(), json.loads)
        for pid, entry in auth.items():
            if pid == GO or not isinstance(entry, dict) or entry.get("type") != "api" or not entry.get("key"):
                continue
            p = providers.setdefault(pid, {})
            p["options"] = dict(p.get("options") or {}, apiKey=str(entry["key"]))
        if ZEN not in auth:
            token = self._login()
            if token:
                p = providers.setdefault(ZEN, {})
                p["options"] = dict(p.get("options") or {}, apiKey=token)
        providers.pop(GO, None)
        if providers:
            out["provider"] = providers
        return out

    def can_call(self, provider: str, free: bool) -> bool:
        """NMB's server can call this provider: Zen's free models always; others with a key it was handed, or a
        provider whose definition carries its own key or reads it from the environment."""
        if provider == GO:
            return False
        if provider == ZEN and free:
            return True
        p = (self.config().get("provider") or {}).get(provider)
        return isinstance(p, dict) and bool((p.get("options") or {}).get("apiKey"))

    def refused(self, provider: str) -> bool:
        """The person signed in to this provider with a refreshing login NMB must not use."""
        entry = _read_json(self._auth_file(), json.loads).get(provider)
        return isinstance(entry, dict) and entry.get("type") not in (None, "api")


def persons() -> Signins:
    """The person's own opencode folders (also from inside a Flatpak) and login."""
    from ..keys import opencode_auth_file
    from .opencode import host_xdg
    from .opencode_direct import login_token
    return Signins(lambda: host_xdg("XDG_CONFIG_HOME", ".config") / "opencode", opencode_auth_file, login_token)


def fingerprint(config: dict[str, Any]) -> str:
    """Tells a running server whose sign-ins are out of date without keeping the keys around."""
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
