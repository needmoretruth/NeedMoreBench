"""Audit AA1/AB1,: paid Zen models and the person's other opencode providers record their reasoning
too. NMB's own opencode server gets the person's provider definitions and stored API keys (never a refreshing
login, never their instructions, plugins or MCP servers) and the active OpenCode login's access token for Zen.
The last test runs the real opencode program: a provider defined only in the person's settings, with its key only
in their auth file, and paid Zen with the login token, both answer a recording stand-in with exactly our prompt and
the handed-over key."""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from nmb.providers.base import ModelInfo, ModelRef
from nmb.providers.opencode import OpenCodeRoute, executable
from nmb.providers.opencode_creds import Signins, jsonc
from nmb.providers.opencode_private import PrivateServer

from .test_opencode_private import SYSTEM, USER, Echo

SETTINGS = """{
  // the person's own opencode settings
  "$schema": "https://opencode.ai/config.json",
  "instructions": ["~/AGENTS.md"],
  "plugin": ["their-plugin"],
  "mcp": {"files": {"type": "local", "command": ["x"]}},
  "provider": {
    "phala": {"npm": "@ai-sdk/openai-compatible", "options": {"baseURL": "BASE/v1"},
              "models": {"deep": {"name": "Deep"},}},
    "opencode": {"options": {"baseURL": "BASE/v1"}, "models": {"glm-paid": {"name": "GLM paid"}}},
    /* Go goes through Go's own API */
    "opencode-go": {"models": {}},
  },
}"""
AUTH = {"phala": {"type": "api", "key": "phala-test-key"}, "opencode-go": {"type": "api", "key": "go-test-key"},
        "copilot": {"type": "oauth", "refresh": "r", "access": "a", "expires": 0}}


def signins(tmp_path: Path, base: str = "http://127.0.0.1:1", login: str | None = "login-test-token") -> Signins:
    (tmp_path / "cfg").mkdir(exist_ok=True)
    (tmp_path / "cfg" / "opencode.jsonc").write_text(SETTINGS.replace("BASE", base), encoding="utf-8")
    (tmp_path / "auth.json").write_text(json.dumps(AUTH), encoding="utf-8")
    return Signins(lambda: tmp_path / "cfg", lambda: tmp_path / "auth.json", lambda: login)


def test_only_providers_and_their_keys_are_handed_over(tmp_path: Path) -> None:
    assert jsonc('{"a": "// not a comment", /* x */ "b": [1,],}') == {"a": "// not a comment", "b": [1]}
    s = signins(tmp_path)
    cfg = s.config()
    assert set(cfg) == {"provider"}  # no instructions, plugins or MCP servers of theirs
    p = cfg["provider"]
    assert p["phala"]["options"] == {"baseURL": "http://127.0.0.1:1/v1", "apiKey": "phala-test-key"}
    assert p["opencode"]["options"]["apiKey"] == "login-test-token"
    assert "opencode-go" not in p and "copilot" not in p  # Go has its own API; a refreshing login is never used
    assert s.can_call("phala", False) and s.can_call("opencode", False) and not s.can_call("copilot", False)
    assert s.refused("copilot") and not s.refused("phala")
    assert not signins(tmp_path, login=None).can_call("opencode", False)


def route(tmp_path: Path, private: PrivateServer) -> OpenCodeRoute:
    r = OpenCodeRoute(url="http://127.0.0.1:1", password="x", private=private)
    for pid, mid, free in (("opencode", "big-pickle", True), ("opencode", "glm-paid", False),
                           ("phala", "deep", False), ("copilot", "gpt", False), ("venice", "v", False)):
        r._info[f"opencode:{pid}/{mid}"] = ModelInfo(ModelRef("opencode", pid, mid), mid, free=free,
                                                     price_out=0.0 if free else 2.0)
    return r


def test_paid_zen_and_other_providers_go_to_nmbs_server_and_the_rest_say_why_in_plain_words(tmp_path: Path) -> None:
    r = route(tmp_path, PrivateServer(lambda: tmp_path / "srv", executable, signins=signins(tmp_path)))
    for pid, mid in (("opencode", "big-pickle"), ("opencode", "glm-paid"), ("phala", "deep")):
        assert r.why_no_reasoning(ModelRef("opencode", pid, mid)) == "", pid
    left = {pid: r.why_no_reasoning(ModelRef("opencode", pid, mid)) for pid, mid in (("copilot", "gpt"), ("venice", "v"))}
    assert left["copilot"] == "No reasoning: this provider's sign-in works only inside OpenCode"
    assert left["venice"] == "No reasoning: no key for this provider"
    for words in left.values():
        assert "server" not in words and "endpoint" not in words and "opencode" not in words
    r.private.refused.add("phala")  # its key was refused mid-game: back on the person's server, said plainly
    assert r.why_no_reasoning(ModelRef("opencode", "phala", "deep")) == "No reasoning: this provider did not take the key"
    zen = PrivateServer(lambda: tmp_path / "srv", executable, signins=signins(tmp_path))
    zen.refused.add("opencode")  # Zen refused the login token: not handed again, free Zen still goes there
    assert "apiKey" not in zen._wanted()["provider"]["opencode"].get("options", {})
    assert zen.can_call("opencode", True) and not zen.can_call("opencode", False)
    s = signins(tmp_path, login=None)
    r = route(tmp_path, PrivateServer(lambda: tmp_path / "srv", executable, signins=s))
    assert r.why_no_reasoning(ModelRef("opencode", "opencode", "glm-paid")) == "No reasoning: no OpenCode login"


class Keyed(Echo):
    keys: list[str] = []

    def do_POST(self) -> None:  # noqa: N802
        Keyed.keys.append(self.headers.get("authorization") or "")
        super().do_POST()


@pytest.mark.skipif(executable() is None, reason="opencode is not installed")
def test_the_real_opencode_calls_their_providers_with_exactly_our_prompt_and_their_key(tmp_path: Path) -> None:
    Echo.bodies, Keyed.keys = [], []
    http = ThreadingHTTPServer(("127.0.0.1", 0), Keyed)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    s = signins(tmp_path, base=f"http://127.0.0.1:{http.server_address[1]}")
    srv = PrivateServer(lambda: tmp_path / "srv", executable, signins=s)
    try:
        got = {}
        for pid, mid in (("phala", "deep"), ("opencode", "glm-paid")):
            ref = ModelRef("opencode", pid, mid)
            got[pid] = asyncio.run(srv.complete(ref, SYSTEM, USER, 1200, ModelInfo(ref, mid, price_out=2.0)))
    finally:
        srv.stop()
        http.shutdown()
    assert srv.signins_problem is False
    assert all(c.text == "{}" and c.reasoning == "조용히 본다." for c in got.values())
    assert Keyed.keys == ["Bearer phala-test-key", "Bearer login-test-token"]
    for body in Echo.bodies:
        assert body["messages"] == [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
        assert "tools" not in body and body["max_completion_tokens"] == 1200  # paid, no effort level: the bare limit
    assert (tmp_path / "srv").is_dir() and not any("test-key" in p.read_text(errors="ignore")
                                                   for p in (tmp_path / "srv").rglob("*") if p.is_file()
                                                   and p.stat().st_size < 5_000_000)  # keys never written to a file
