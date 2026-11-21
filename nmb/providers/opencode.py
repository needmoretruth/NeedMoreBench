"""OpenCode route: the user's local opencode background server (`opencode service`). OpenCode Zen free models,
Go models and the other providers configured in opencode all go through `POST /api/experimental/generate/text`.

This module reads the server's address and password and calls it; Settings may start the server when it is off.
The password is never logged. Where opencode keeps things is the same on Windows, macOS and Linux (it builds the
paths from the home folder, read from opencode 2.3): the running server writes its address and password to
$XDG_STATE_HOME/opencode/service.json (default ~/.local/state), its settings live in $XDG_CONFIG_HOME/opencode
(default ~/.config).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

import httpx

from .base import Completion, ModelInfo, ModelRef, ProviderError, Timer, cost_of, estimate_tokens
from .catalog import efforts, maker_of, special_purpose, split_maker, trains
from .opencode_direct import GoDirect
from .opencode_creds import GO, ZEN
from .opencode_private import PrivateServer
from ..i18n import _

# a console program started from the windowed app on Windows would flash a console window
NO_WINDOW: dict[str, int] = {"creationflags": 0x08000000} if sys.platform == "win32" else {}
# Providers that have a direct route of their own in the app are left out here.
SKIP_PROVIDERS = {"openrouter", "anthropic", "lmstudio"}
REASON = {"authentication": "auth", "rate_limit": "rate_limit", "content_filter": "declined",
          "invalid_request": "invalid", "overloaded": "overloaded", "provider": "provider"}


def host_xdg(var: str, *default: str) -> Path:
    """The user's XDG folder as programs outside the app see it. Inside a Flatpak the XDG variables name the app's
    own folders, so the default under the home folder is the one opencode uses."""
    value = "" if os.environ.get("FLATPAK_ID") else os.environ.get(var, "")
    return Path(value) if value else Path.home().joinpath(*default)


def state_file() -> Path:
    """Written by the running server: url, password, pid, version."""
    return host_xdg("XDG_STATE_HOME", ".local", "state") / "opencode" / "service.json"


def config_file() -> Path:
    """The server's saved settings; holds the password before the server has written its state."""
    return host_xdg("XDG_CONFIG_HOME", ".config") / "opencode" / "service.json"


def _name() -> str:
    return "opencode.exe" if sys.platform == "win32" else "opencode"


def bundled() -> str | None:
    """The opencode program NMB ships (Y1; opencode is MIT): /app/bin in the Flatpak, `opencode/` inside the
    Windows and macOS bundles. Only NMB's own server runs it; it is never taken for the person's install."""
    places = []
    if os.environ.get("FLATPAK_ID"):
        places.append(Path("/app/bin") / _name())
    if getattr(sys, "frozen", False):
        places.append(Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "opencode" / _name())
    return next((str(p) for p in places if p.is_file()), None)


def executable() -> str | None:
    """The person's own opencode program: on PATH, or where its own installer puts it (~/.opencode/bin). The copy
    NMB ships does not count: it cannot see or start the person's server."""
    found = shutil.which("opencode")
    if found and found != bundled():
        return found
    p = Path.home() / ".opencode" / "bin" / _name()
    return str(p) if p.is_file() else None


def server_executable() -> str | None:
    """What runs NMB's own server: the shipped copy first (its plugin hooks are tested on that version), else the
    person's own."""
    return bundled() or executable()


def _read(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


async def service_url() -> str | None:
    exe = executable()
    if not exe:
        return None
    proc = await asyncio.create_subprocess_exec(exe, "service", "status", stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL, **NO_WINDOW)
    out, _ = await asyncio.wait_for(proc.communicate(), 15)
    for word in out.decode(errors="replace").split():
        if word.startswith("http://") or word.startswith("https://"):
            return word.rstrip("/")
    return None


def parse(data: dict) -> list[ModelInfo]:
    """The server's `/api/model` list as the app's models. A provider's 'Maker: ' part (phala) is the maker, not
    part of the name; a model with no price at all (a block of the user's own config, such as Go's retired
    deepseek-v4-flash) is 가격 모름, never free and never picked automatically."""
    out = []
    for m in data.get("data", []):
        pid, mid = m.get("providerID", ""), m.get("id", "")
        if pid in SKIP_PROVIDERS:
            continue
        maker_text, name = split_maker(m.get("name") or mid)
        cost = (m.get("cost") or [{}])[0] or {}
        pin, pout = cost.get("input"), cost.get("output")
        priced = pin is not None or pout is not None
        free = priced and pin == 0 and pout == 0
        maker, country = maker_of(mid, name, maker_text)
        status = str(m.get("status") or "")
        info = ModelInfo(ModelRef("opencode", pid, mid), name, maker, country, float(pin or 0), float(pout or 0),
                         int((m.get("limit") or {}).get("context") or 0), free=free,
                         trains=trains(name, zen_free=free and pid in ("opencode", "opencode-go")),
                         variants=efforts([v.get("id") for v in m.get("variants") or []]),
                         status=status if priced else "가격 모름",
                         created=int(((m.get("time") or {}).get("released") or 0) / 1000),
                         retiring=status if status in ("deprecated", "retired") else "",
                         special=special_purpose(name))
        out.append(info)
    return out


class OpenCodeRoute:
    name = "opencode"

    def __init__(self, url: str | None = None, password: str | None = None, timeout: float = 180,
                 direct: "GoDirect | None" = None, private: "PrivateServer | None" = None):
        self._url = url
        self._password = password
        self.timeout = timeout
        self._info: dict[str, ModelInfo] = {}
        # Go and Zen models called through Go's own API, with reasoning; None: always the text endpoint
        self.direct = direct
        if direct is not None:
            direct._info_of = self.info
        # free Zen models Go does not serve, through NMB's own opencode server with reasoning
        self.private = private
        self.own_list = False  # the last model list came from NMB's own server, not the person's

    async def _base(self) -> tuple[str, httpx.BasicAuth]:
        if self._url is None:
            state = _read(state_file())
            if isinstance(state.get("url"), str) and isinstance(state.get("password"), str):
                self._url, self._password = state["url"].rstrip("/"), state["password"]
            elif executable() is None:
                raise ProviderError("missing", _("OpenCode is not installed"))
            else:
                self._url = await service_url()
        if self._url is None:
            raise ProviderError("off", _("The opencode server is off"))
        if self._password is None:
            password = _read(config_file()).get("password")
            if not isinstance(password, str):
                raise ProviderError("nokey", _("Could not read the opencode server password"))
            self._password = password
        return self._url, httpx.BasicAuth("opencode", self._password)

    async def models(self) -> list[ModelInfo]:
        """The person's server's list; without that server (not installed, off, or out of reach as in the Flatpak)
        the list NMB's own server gives, so free Zen models work out of the box."""
        try:
            out = await self._persons_models()
            self.own_list = False
            return out
        except ProviderError as e:
            if self.private is None or e.reason not in ("missing", "off") or self.private.problem is not None:
                raise
            try:
                out = parse(await self.private.model_list())
                self.own_list = True
            except ProviderError:
                raise e from None
        self._info.update({m.ref.key: m for m in out})
        if self.direct is not None:
            await self.direct.load()
        return out

    async def _persons_models(self) -> list[ModelInfo]:
        url, auth = await self._base()
        try:
            async with httpx.AsyncClient(timeout=30, auth=auth) as c:
                r = await c.get(f"{url}/api/model")
        except httpx.ConnectError as e:  # the server left its address behind when it stopped
            self._url = self._password = None
            raise ProviderError("off" if executable() else "missing",
                                _("The opencode server is off") if executable() else _("OpenCode is not installed")) from e
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code == 401:
            raise ProviderError("auth", _("The opencode server refused its password"), 401)
        r.raise_for_status()
        out = parse(r.json())
        self._info.update({m.ref.key: m for m in out})
        if self.direct is not None:
            await self.direct.load()
        return out

    def why_no_reasoning(self, ref: ModelRef) -> str:
        """Empty when this seat's reasoning is recorded; otherwise why not, in plain words for the seat row.
        Go's models go to Go's own API; every other OpenCode model to NMB's own server (audit AA1/AB1)."""
        if self._direct(ref) or self._private(ref):
            return ""
        d, p = self.direct, self.private
        if ref.provider == GO:
            if d is None or d.problem is not None:
                return d.why_no_reasoning() if d is not None else _("No reasoning: no OpenCode Go key and no OpenCode login")
            return _("No reasoning: OpenCode Go does not serve this model")
        if p is None or p.problem is not None:
            return _("No reasoning: OpenCode could not start inside NeedMoreBench")
        if p.signins is not None and p.signins.refused(ref.provider):
            return _("No reasoning: this provider's sign-in works only inside OpenCode")
        if ref.provider in p.refused:
            return _("No reasoning: this provider did not take the key")
        if ref.provider == ZEN:
            return _("No reasoning: no OpenCode login")
        return _("No reasoning: no key for this provider")

    def _direct(self, ref: ModelRef) -> bool:
        """Go's own API serves this seat: a Go model, or a free Zen model Go also lists. A paid Zen model stays on
        the opencode server, so it is billed to Zen as the person chose, not to the Go plan."""
        if self.direct is None or not self.direct.serves(ref):
            return False
        info = self.info(ref)
        return ref.provider == "opencode-go" or bool(info and info.free)

    def _private(self, ref: ModelRef) -> bool:
        """NMB's own opencode server serves this seat: any model Go's API does not take, free Zen always, paid Zen
        and the person's other providers when their key or login could be handed over (opencode_creds)."""
        if self.private is None or ref.provider == GO or self._direct(ref):
            return False
        info = self.info(ref)
        return self.private.can_call(ref.provider, bool(info and info.free))

    def info(self, ref: ModelRef) -> ModelInfo | None:
        return self._info.get(ModelRef(ref.route, ref.provider, ref.id).key)

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1200) -> Completion:
        if self.direct is not None and self._direct(ref):
            try:
                return await self.direct.complete(ref, system, user, max_tokens)
            except ProviderError as e:
                if e.reason != "auth":
                    raise
                self.direct.problem = e  # the key or login stopped working: the text endpoint from now on
        if self.private is not None and self._private(ref):
            try:
                return await self.private.complete(ref, system, user, max_tokens, self.info(ref))
            except ProviderError as e:
                if e.reason == "auth":
                    self.private.refused.add(ref.provider)  # the key it was handed is refused: the person's server
                elif e.reason in ("off", "missing"):
                    self.private.problem = e  # it could not start: the text endpoint from now on, the seat row says so
                else:
                    raise
        url, auth = await self._base()
        prompt = f"{system}\n\n{user}" if system else user
        model: dict[str, str] = {"providerID": ref.provider, "id": ref.id}
        if ref.variant:
            model["variant"] = ref.variant
        t = Timer()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, auth=auth) as c:
                r = await c.post(f"{url}/api/experimental/generate/text", json={"prompt": prompt, "model": model})
        except httpx.TimeoutException as e:
            raise ProviderError("network", _("No answer in time")) from e
        except httpx.HTTPError as e:
            if isinstance(e, httpx.ConnectError):  # restarted on another port: read its address again next time
                self._url = self._password = None
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise self._error(r)
        text = ((r.json() or {}).get("data") or {}).get("text") or ""
        tin, tout = estimate_tokens(prompt), estimate_tokens(text)
        return Completion(text, t.ms, tin, tout, True, cost_of(self.info(ref), tin, tout))

    @staticmethod
    def _error(r: httpx.Response) -> ProviderError:
        try:
            body = r.json()
        except ValueError:
            body = {}
        msg = str(body.get("message") or r.text[:300])
        if r.status_code == 502 and body.get("reason"):
            reason = REASON.get(body["reason"], "provider")
            if reason == "provider" and any(w in msg.lower() for w in ("credit", "balance", "quota", "billing")):
                reason = "credit"
            ra = body.get("retryAfterMs")
            return ProviderError(reason, msg, body.get("status"), ra / 1000 if ra else None)
        if r.status_code == 401:
            return ProviderError("auth", _("The opencode server refused its password"), 401)
        if r.status_code in (404, 422):
            return ProviderError("invalid", msg, r.status_code)
        if r.status_code == 503:
            return ProviderError("overloaded", msg, 503)
        return ProviderError("provider", msg, r.status_code)

    async def status(self) -> tuple[str, str]:
        try:
            models = await self.models()
        except ProviderError as e:
            return e.reason, str(e)
        if self.own_list:  # the person's server is out of reach: NMB's own server gave the list
            return "ok", _("Models: {n}, through the OpenCode inside NeedMoreBench").format(n=len(models))
        return "ok", _("Models: {n}").format(n=len(models))
