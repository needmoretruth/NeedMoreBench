"""NMB's own opencode server for the free Zen models.

Zen answers its free models only to the opencode program, and the person's opencode server answers NMB only through
its text endpoint, which returns no reasoning. So NMB starts a second opencode server of its own: on a free local
port with its own password, its own folders under NMB's data folder (settings, data, state, cache and session
database), nothing from the person's opencode setup, home or projects, and NMB's plugin (data/opencode_clean.js).
Each call is one new session with one message; the plugin turns it back into exactly NMB's system text and user
text with no tools before it leaves, and the session's reasoning parts are kept for the record. The server stops
when the app does, also when the app crashes or is killed (keeper.py). The person's own opencode server is never
touched. Paid Zen models and the person's other opencode providers come here too, with the provider definitions
and keys `opencode_creds.Signins` hands over; when a key or the login token changes, the server starts again
between calls.
"""
from __future__ import annotations

import asyncio
import atexit
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from .base import Completion, ModelInfo, ModelRef, ProviderError, Timer, answer_limit, cost_of
from .opencode_creds import ZEN, Signins, fingerprint
from ..i18n import _

PLUGIN = Path(__file__).resolve().parent.parent / "data" / "opencode_clean.js"
KEEPER = Path(__file__).resolve().parent / "keeper.py"
ENVELOPE = "NMB-ENVELOPE "  # the plugin reads the call from a user message that starts with this
AGENT = "nmb"
CONFIG: dict[str, Any] = {
    "$schema": "https://opencode.ai/config.json", "autoupdate": False, "share": "disabled",
    "agents": {AGENT: {"description": "NeedMoreBench player", "mode": "primary",
                       "permissions": [{"action": "*", "resource": "*", "effect": "deny"}]}}}
# opencode reads these to find the person's settings, instructions and Claude Code files; none may reach the server
FLAGS = {"OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT": "1",
         "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1", "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
         "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_FILEWATCHER": "1"}
ERRORS = {"provider.free-limit": "rate_limit", "provider.auth": "auth", "provider.rate-limit": "rate_limit"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def environment(root: Path, password: str, extra: dict[str, Any] | None = None) -> dict[str, str]:
    """The child's environment: the person's own OPENCODE_* settings dropped, every opencode folder under root."""
    config = dict(CONFIG, **(extra or {}))
    env = {k: v for k, v in os.environ.items() if not k.startswith("OPENCODE_")}
    env.update(FLAGS)
    env.update({"XDG_CONFIG_HOME": str(root / "config"), "XDG_DATA_HOME": str(root / "data"),
                "XDG_STATE_HOME": str(root / "state"), "XDG_CACHE_HOME": str(root / "cache"),
                "OPENCODE_CONFIG_DIR": str(root / "config" / "opencode"), "OPENCODE_DB": str(root / "nmb.db"),
                "OPENCODE_CONFIG_CONTENT": json.dumps(config), "OPENCODE_SERVER_PASSWORD": password})
    return env


def envelope(system: str, user: str, max_tokens: int) -> str:
    return ENVELOPE + json.dumps({"system": system, "user": user, "max_tokens": max_tokens}, ensure_ascii=False)


def read_answer(messages: Any) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    """(text, reasoning, tokens, error) of the assistant's message in a session's message list."""
    items = messages.get("data", messages) if isinstance(messages, dict) else messages
    text, reasoning, tokens, error = [], [], {}, None
    for msg in items or []:
        if not isinstance(msg, dict) or msg.get("type") != "assistant":
            continue
        for part in msg.get("content") or []:
            kind = part.get("type") if isinstance(part, dict) else None
            if kind == "text":
                text.append(str(part.get("text") or ""))
            elif kind == "reasoning":
                reasoning.append(str(part.get("text") or ""))
        tokens = msg.get("tokens") or tokens
        error = msg.get("error") or error
    return "".join(text), "\n\n".join(r for r in reasoning if r.strip()).strip(), tokens, error


def _error(err: dict[str, Any]) -> ProviderError:
    status = err.get("status") if isinstance(err.get("status"), int) else None
    reason = ERRORS.get(str(err.get("type") or ""))
    if reason is None:
        reason = {401: "auth", 403: "auth", 429: "rate_limit", 503: "overloaded", 529: "overloaded"}.get(status or 0,
                                                                                                      "provider")
    message = str(err.get("message") or err.get("type") or "")[:300]
    if reason in ("provider", "auth") and any(w in message.lower() for w in ("insufficient balance", "credit", "billing")):
        reason = "credit"  # paid Zen with no credits left (2026-11-22 real call): said as no credit, kept a day
    return ProviderError(reason, message, status)


def merged(extra: dict[str, Any] | None, signins: dict[str, Any]) -> dict[str, Any]:
    """The tests' stand-in config over the person's providers and keys (opencode_creds)."""
    out = dict(signins)
    for k, v in (extra or {}).items():
        out[k] = dict(out.get(k) or {}, **v) if k == "provider" else v
    return out


class PrivateServer:
    def __init__(self, root: Callable[[], Path], exe: Callable[[], str | None], timeout: float = 180,
                 extra_config: dict[str, Any] | None = None, signins: Signins | None = None):
        self._root, self._exe = root, exe
        self.timeout = timeout
        self.extra_config = extra_config  # tests add a local stand-in provider here
        self.signins = signins  # the person's providers and keys for paid Zen and the rest (AA1/AB1)
        self.proc: subprocess.Popen[bytes] | None = None
        self.url = ""
        self._password = ""
        self._lock = asyncio.Lock()
        self._running = ""  # fingerprint of the sign-ins the running server has
        self._busy = 0  # calls in flight; a server with old sign-ins restarts only between calls
        self.problem: ProviderError | None = None  # why it could not start; the seats then use the text endpoint
        self.signins_problem = False  # it started only without the person's providers: free Zen only
        self.refused: set[str] = set()  # providers that refused the key handed over: back on the person's server
        atexit.register(self.stop)

    def can_call(self, provider: str, free: bool) -> bool:
        if self.problem is not None:
            return False
        if provider == ZEN and free:
            return True
        return self.signins is not None and not self.signins_problem and provider not in self.refused \
            and self.signins.can_call(provider, free)

    def _wanted(self) -> dict[str, Any]:
        if self.signins is None or self.signins_problem:
            return {}
        cfg = self.signins.config()
        for pid in self.refused & set(cfg.get("provider") or {}):  # a refused key is not handed again; free Zen
            cfg["provider"][pid].get("options", {}).pop("apiKey", None)  # then goes without the login token
        return cfg

    def prepare(self) -> Path:
        root = self._root()
        for sub in ("config/opencode/plugins", "cwd", "data", "state", "cache"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PLUGIN, root / "config" / "opencode" / "plugins" / "needmorebench.js")
        return root

    async def start(self) -> tuple[str, httpx.BasicAuth]:
        async with self._lock:
            wanted = self._wanted()
            if self.proc is not None and self.proc.poll() is None:
                if fingerprint(wanted) == self._running or self._busy:
                    return self.url, httpx.BasicAuth("opencode", self._password)
                self.stop()  # a key or the login token changed: start again with the new ones
            try:
                return await self._start(wanted)
            except ProviderError:
                if not wanted:
                    raise
                self.signins_problem = True  # a provider definition it cannot read: free Zen still works
                return await self._start({})

    async def _start(self, wanted: dict[str, Any]) -> tuple[str, httpx.BasicAuth]:
        exe = self._exe()
        if not exe:
            raise ProviderError("missing", _("OpenCode is not installed"))
        root = self.prepare()
        port, self._password = _free_port(), secrets.token_urlsafe(24)
        log = open(root / "server.log", "wb")
        from .opencode import NO_WINDOW
        # through the keeper: the server ends when the app does, also when the app crashes or is killed
        self.proc = subprocess.Popen([sys.executable, "-I", str(KEEPER), exe, "serve", "--hostname", "127.0.0.1",
                                      "--port", str(port)],
                                     cwd=root / "cwd", env=environment(root, self._password,
                                                                       merged(self.extra_config, wanted)),
                                     stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.PIPE, **NO_WINDOW)
        log.close()
        self._running = fingerprint(wanted)
        self.url = f"http://127.0.0.1:{port}"
        auth = httpx.BasicAuth("opencode", self._password)
        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=5, auth=auth) as c:
            while time.monotonic() - t0 < 60:
                if self.proc.poll() is not None:
                    break
                try:
                    if (await c.get(self.url + "/api/info")).status_code == 200:
                        return self.url, auth
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.3)
        self.stop()
        raise ProviderError("off", _("OpenCode could not start inside NeedMoreBench"))

    def stop(self) -> None:
        """Closing the keeper's pipe stops the server and what it started; the keeper then ends."""
        p, self.proc = self.proc, None
        if p is None:
            return
        if p.stdin is not None:
            p.stdin.close()
        try:
            p.wait(15)
        except subprocess.TimeoutExpired:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()

    async def model_list(self) -> dict[str, Any]:
        """The server's `/api/model` answer: Zen's models and the providers it was handed."""
        url, auth = await self.start()
        try:
            async with httpx.AsyncClient(timeout=30, auth=auth) as c:
                r = await c.get(url + "/api/model")
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if r.status_code != 200:
            raise ProviderError("provider", r.text[:300], r.status_code)
        data = r.json()
        return data if isinstance(data, dict) else {}

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int,
                       info: ModelInfo | None) -> Completion:
        url, auth = await self.start()
        self._busy += 1  # no await since start returned: a restart cannot slip in between
        try:
            return await self._call(url, auth, ref, system, user, max_tokens, info)
        finally:
            self._busy -= 1

    async def _call(self, url: str, auth: httpx.BasicAuth, ref: ModelRef, system: str, user: str, max_tokens: int,
                    info: ModelInfo | None) -> Completion:
        model: dict[str, str] = {"providerID": ref.provider, "id": ref.id}
        if ref.variant:
            model["variant"] = ref.variant
        location = {"directory": str(self._root() / "cwd")}
        t = Timer()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, auth=auth) as c:
                r = await c.post(url + "/api/session", json={"title": "nmb", "agent": AGENT, "model": model,
                                                              "location": location})
                if r.status_code != 200:
                    raise ProviderError("invalid", r.text[:300], r.status_code)
                sid = (r.json().get("data") or r.json()).get("id")
                try:
                    p = await c.post(f"{url}/api/session/{sid}/prompt",
                                     json={"text": envelope(system, user, answer_limit(info, max_tokens))})
                    if p.status_code != 200:
                        raise ProviderError("invalid", p.text[:300], p.status_code)
                    await c.post(f"{url}/api/experimental/session/{sid}/wait", json={})
                    text, reasoning, tokens, err = read_answer((await c.get(f"{url}/api/session/{sid}/message")).json())
                finally:
                    await c.delete(f"{url}/api/session/{sid}")
        except httpx.TimeoutException as e:
            raise ProviderError("network", _("No answer in time")) from e
        except httpx.HTTPError as e:
            raise ProviderError("network", str(e)) from e
        if err:
            raise _error(err)
        # opencode counts the reasoning apart; the other routes count it in the output, so it is added here
        rtok = int(tokens.get("reasoning") or 0)
        tin, tout = int(tokens.get("input") or 0), int(tokens.get("output") or 0) + rtok
        return Completion(text, t.ms, tin, tout, not tokens, cost_of(info, tin, tout),
                          reasoning=reasoning, reasoning_tokens=rtok or None)
