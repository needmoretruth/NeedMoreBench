"""OpenCode Go's own API for applications: `https://opencode.ai/inference/go`, OpenAI-compatible, with
the model list at `/v1/models`. Go and Zen seats are called here directly, so each request carries only our prompt
and the model's reasoning comes back (`reasoning_content`), as with the other routes.

The credential is the Go key stored in the keyring (route `opencode-go`, a field in Settings). Without one, the
access token of the user's own OpenCode login is used while it is valid: read from opencode's database opened
read-only, never refreshed and never written, so opencode keeps its login as it was. Neither is ever printed.
When there is neither, or Go refuses it, the seat goes through the opencode server's text endpoint, which returns
no reasoning; `why_no_reasoning` says so for the seat row.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

import httpx

from .base import REASONING_ROOM, Completion, ModelInfo, ModelRef, ProviderError, cost_of
from .openai_compat import ChatRoute, _error
from ..i18n import _

GO = "https://opencode.ai/inference/go"
KEY_ROUTE = "opencode-go"  # the keyring name of the Go key
PROVIDERS = ("opencode-go", "opencode")  # Go models and Zen's free models are both served here


def opencode_db() -> Path:
    from .opencode import host_xdg  # the folder opencode itself uses, also from inside a Flatpak
    return host_xdg("XDG_DATA_HOME", ".local", "share") / "opencode" / "opencode.db"


def login_token(path: Path | None = None, now: float | None = None) -> str | None:
    """The access token of the active OpenCode login, if it is still valid for at least a minute. Read-only."""
    path = path or opencode_db()
    if not path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
        try:
            row = con.execute("select value from credential where integration_id = 'opencode' and active = 1").fetchone()
        finally:
            con.close()
        cred = json.loads(row[0]) if row else {}
    except (sqlite3.Error, ValueError, TypeError):
        return None
    access, expires = cred.get("access"), cred.get("expires")
    if not isinstance(access, str) or not access or not isinstance(expires, (int, float)):
        return None
    return access if expires / 1000 > (now or time.time()) + 60 else None


class GoDirect(ChatRoute):
    """Called by the OpenCode route for the models Go serves; not a route of its own in the lists."""

    name = "opencode"
    label = "OpenCode Go"

    def __init__(self, key: Callable[[], str | None], info: Callable[[ModelRef], ModelInfo | None] | None = None,
                 token: Callable[[], str | None] = login_token, timeout: float = 180):
        super().__init__(timeout)
        self._key, self._token, self._info_of = key, token, info
        self.session = "ses_nmb" + secrets.token_hex(8)  # one per app start, never anything about the user
        self.ids: set[str] = set()  # models Go serves, from its list
        self.source = ""  # key | login | "" (none)
        self._cred: str | None = None
        self.problem: ProviderError | None = None  # why the direct calls are off, when they are

    def credentials(self) -> list[tuple[str, str]]:
        """(source, secret) in the order tried: the stored Go key, then the login's access token."""
        out = []
        try:
            key = self._key()
        except ProviderError:
            key = None
        if key:
            out.append(("key", key))
        token = self._token()
        if token:
            out.append(("login", token))
        return out

    def base(self) -> str:
        return GO + "/openai/v1"

    def headers(self) -> dict[str, str]:
        if not self._cred:
            found = self.credentials()
            if not found:
                raise ProviderError("nokey", _("No OpenCode Go key"))
            self.source, self._cred = found[0]
        return {"Authorization": f"Bearer {self._cred}", "x-opencode-session": self.session}

    def extra_body(self, ref: ModelRef) -> dict[str, Any]:
        return {"reasoning_effort": ref.variant} if ref.variant else {}

    def info(self, ref: ModelRef) -> ModelInfo | None:
        return self._info_of(ref) if self._info_of is not None else None

    def limit(self, ref: ModelRef, max_tokens: int) -> int:
        # Every Go model reasons; the text endpoint sent no limit, so they reasoned freely, and with the answer's
        # limit alone most answers were cut off inside the reasoning (2026-11-21 game: 14 of 37 calls).
        return max_tokens + REASONING_ROOM

    async def complete(self, ref: ModelRef, system: str, user: str, max_tokens: int = 1200) -> Completion:
        """Go answers `usage.cost` 0 for plan models (the plan is paid monthly); the record keeps the list price,
        as the text endpoint did, so costs compare across routes and games."""
        c = await super().complete(ref, system, user, max_tokens)
        c.cost = cost_of(self.info(ref), c.tokens_in, c.tokens_out)
        return c

    def serves(self, ref: ModelRef) -> bool:
        return self.problem is None and ref.provider in PROVIDERS and ref.id in self.ids

    async def load(self) -> None:
        """Go's model list, asked with each credential in turn (a wrong key answers 401 here, before a game); the
        first one Go accepts is used for the calls."""
        self.ids, self._cred, self.source = set(), None, ""
        found = self.credentials()
        self.problem = None if found else ProviderError("nokey", _("No OpenCode Go key"))
        for source, cred in found:
            try:
                async with self.client(30) as c:
                    r = await c.get(f"{GO}/v1/models", headers={"Authorization": f"Bearer {cred}"})
            except httpx.HTTPError as e:
                self.problem = ProviderError("network", str(e))
                return
            if r.status_code != 200:
                self.problem = _error(r, self.label)
                continue
            data = r.json()
            self.ids = {m.get("id", "") for m in (data.get("data") or []) if isinstance(m, dict)} - {""}
            self.problem, self.source, self._cred = None, source, cred
            return

    async def status(self) -> tuple[str, str]:
        await self.load()
        if self.problem is not None:
            return self.problem.reason, str(self.problem)
        if self.source == "login":
            return "ok", _("Using your OpenCode login. Models: {n}").format(n=len(self.ids))
        return "ok", _("Models: {n}").format(n=len(self.ids))

    def why_no_reasoning(self) -> str:
        """Plain words for a seat that goes through the text endpoint."""
        p = self.problem
        if p is None or p.reason == "nokey":
            return _("No reasoning: no OpenCode Go key and no OpenCode login")
        if p.reason == "auth":
            return _("No reasoning: OpenCode Go refused the key")
        return _("No reasoning: OpenCode Go did not answer")
