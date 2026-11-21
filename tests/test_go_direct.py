"""Go and Zen seats go to Go's own API with only our prompt and their reasoning is recorded; the login token
is read without touching opencode's database; a seat that cannot have reasoning says why."""
from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

import httpx

from nmb.providers.base import ModelInfo, ModelRef
from nmb.providers.opencode import OpenCodeRoute
from nmb.providers.base import REASONING_ROOM
from nmb.providers.opencode_direct import GO, GoDirect, login_token
from nmb.providers.registry import Routes

LIST = {"object": "list", "data": [{"id": "glm-5.3"}, {"id": "hy4-flash-free"}]}
ANSWER = {"choices": [{"message": {"role": "assistant", "content": "{\"say\": \"안녕하세요\"}",
                                   "reasoning_content": "The player should greet briefly."}, "finish_reason": "stop"}],
          "usage": {"prompt_tokens": 120, "completion_tokens": 30, "cost": 0,  # Go: plan models report 0
                    "completion_tokens_details": {"reasoning_tokens": 12}}}


def fake_go(good: set[str], seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if req.headers.get("authorization", "").removeprefix("Bearer ") not in good:
            return httpx.Response(401, json={"error": {"type": "authentication_error", "message": "Invalid credential"}})
        if req.url.path.endswith("/v1/models"):
            return httpx.Response(200, json=LIST)
        return httpx.Response(200, json=ANSWER)
    return httpx.MockTransport(handler)


def direct(key: str | None, token: str | None, good: set[str], seen: list[httpx.Request]) -> GoDirect:
    d = GoDirect(lambda: key, token=lambda: token)
    d.transport = fake_go(good, seen)
    return d


def test_a_refused_key_falls_back_to_the_login_and_the_call_carries_only_our_prompt() -> None:
    seen: list[httpx.Request] = []
    d = direct("old-go-key", "login-token", {"login-token"}, seen)
    asyncio.run(d.load())
    assert d.problem is None and d.source == "login" and d.ids == {"glm-5.3", "hy4-flash-free"}
    route = OpenCodeRoute(url="http://127.0.0.1:1", password="x", direct=d)
    route._info["opencode:opencode-go/glm-5.3"] = ModelInfo(ModelRef("opencode", "opencode-go", "glm-5.3"), "GLM-5.3",
                                                            price_in=1.0, price_out=2.0)
    comp = asyncio.run(route.complete(ModelRef("opencode", "opencode-go", "glm-5.3", "high"), "규칙", "상황"))
    assert comp.reasoning == "The player should greet briefly." and comp.reasoning_tokens == 12
    assert (comp.tokens_in, comp.tokens_out, comp.estimated) == (120, 30, False)
    assert abs(comp.cost - (120 * 1.0 + 30 * 2.0) / 1e6) < 1e-12  # the list price, not Go's 0
    call = seen[-1]
    assert str(call.url) == GO + "/openai/v1/chat/completions"
    body = json.loads(call.content)
    assert body == {"model": "glm-5.3", "max_tokens": 1200 + REASONING_ROOM, "reasoning_effort": "high",
                    "messages": [{"role": "system", "content": "규칙"}, {"role": "user", "content": "상황"}]}
    assert not {"tools", "tool_choice"} & set(body)


def test_zen_free_models_go_direct_too_and_others_say_why_not() -> None:
    seen: list[httpx.Request] = []
    d = direct(None, "login-token", {"login-token"}, seen)
    route = OpenCodeRoute(url="http://127.0.0.1:1", password="x", direct=d)
    asyncio.run(d.load())
    for pid, mid, free in (("opencode", "hy4-flash-free", True), ("opencode", "glm-5.3", False),
                           ("opencode", "flint-40b-free", True)):
        route._info[f"opencode:{pid}/{mid}"] = ModelInfo(ModelRef("opencode", pid, mid), mid, free=free)
    assert route.why_no_reasoning(ModelRef("opencode", "opencode", "hy4-flash-free")) == ""
    # a paid Zen model never goes to Go's API: billed to Zen as chosen, never to the Go plan (NMB's own server
    # takes it, tests/test_opencode_signins.py; this route has none, so it says so in plain words)
    assert not route._direct(ModelRef("opencode", "opencode", "glm-5.3"))
    assert route.why_no_reasoning(ModelRef("opencode", "opencode-go", "glm-5.3")) == ""
    for ref in (ModelRef("opencode", "opencode", "glm-5.3"), ModelRef("opencode", "opencode", "flint-40b-free"),
                ModelRef("opencode", "phala", "some-model")):
        assert route.why_no_reasoning(ref) == "No reasoning: OpenCode could not start inside NeedMoreBench"
    assert "does not serve" in route.why_no_reasoning(ModelRef("opencode", "opencode-go", "retired-model"))
    none = direct(None, None, set(), [])
    asyncio.run(none.load())
    assert none.problem is not None and none.problem.reason == "nokey"
    assert "no OpenCode Go key" in OpenCodeRoute(direct=none).why_no_reasoning(ModelRef("opencode", "opencode-go", "glm-5.3"))
    bad = direct("wrong", None, set(), [])
    asyncio.run(bad.load())
    assert "refused" in OpenCodeRoute(direct=bad).why_no_reasoning(ModelRef("opencode", "opencode-go", "glm-5.3"))


def test_routes_report_go_as_its_own_connection() -> None:
    d = direct("go-key", None, {"go-key"}, [])
    r = Routes({"opencode": OpenCodeRoute(url="http://127.0.0.1:1", password="x", direct=d)})
    r.routes["opencode"].status = lambda: _ok()  # the local server is not part of this test
    out = asyncio.run(r.statuses())
    assert out["opencode-go"] == ("ok", "Models: 2")
    assert r.no_reasoning("opencode:opencode-go/glm-5.3") == ""


async def _ok() -> tuple[str, str]:
    return "ok", ""


def make_db(path: Path, expires_ms: float) -> None:
    con = sqlite3.connect(path)
    con.execute("create table credential (integration_id text, active integer, value text)")
    con.execute("insert into credential values ('opencode', 1, ?)",
                (json.dumps({"type": "oauth", "access": "tok-123", "refresh": "never-used", "expires": expires_ms}),))
    con.commit()
    con.close()


def test_the_login_token_is_read_only_and_only_while_valid(tmp_path: Path) -> None:
    db = tmp_path / "opencode.db"
    make_db(db, (time.time() + 3600) * 1000)
    before = (db.stat().st_mtime_ns, db.read_bytes())
    assert login_token(db) == "tok-123"
    assert (db.stat().st_mtime_ns, db.read_bytes()) == before
    assert not list(tmp_path.glob("opencode.db-*"))  # no journal or WAL file left behind
    late = tmp_path / "late.db"
    make_db(late, (time.time() + 30) * 1000)
    assert login_token(late) is None  # about to expire: never refreshed here, the text endpoint is used instead
    assert login_token(tmp_path / "missing.db") is None
