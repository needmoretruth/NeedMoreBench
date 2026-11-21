"""free Zen seats go through NMB's own opencode server, whose plugin leaves exactly our prompt, and their
reasoning is recorded. The last test runs the real opencode program against a local recording stand-in, so the
exact request body is compared with our prompt; it is skipped where opencode is not installed."""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from nmb.providers.base import REASONING_ROOM, ModelInfo, ModelRef, ProviderError
from nmb.providers.opencode import OpenCodeRoute, executable
from nmb.providers.opencode_private import ENVELOPE, PrivateServer, _error, environment, envelope, read_answer

SYSTEM = "너는 마피아 게임의 플레이어다.\nJSON 하나로만 답한다. \"따옴표\"와 줄바꿈."
USER = "1일 낮이다. JSON {\"say\": \"한마디\"} 하나로만 답한다."


def test_the_server_reads_nothing_of_the_persons_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_CONFIG", str(tmp_path / "persons-opencode.jsonc"))
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "the-persons")
    env = environment(tmp_path, "ours")
    assert env["OPENCODE_SERVER_PASSWORD"] == "ours" and "OPENCODE_CONFIG" not in env
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "OPENCODE_CONFIG_DIR",
                "OPENCODE_DB"):
        assert Path(env[var]).is_relative_to(tmp_path), var
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1" and env["OPENCODE_DISABLE_CLAUDE_CODE"] == "1"
    agent = json.loads(env["OPENCODE_CONFIG_CONTENT"])["agents"]["nmb"]
    assert agent["permissions"] == [{"action": "*", "resource": "*", "effect": "deny"}]
    call = json.loads(envelope(SYSTEM, USER, 9200).removeprefix(ENVELOPE))
    assert call == {"system": SYSTEM, "user": USER, "max_tokens": 9200}


def test_the_answer_its_reasoning_and_errors_are_read() -> None:
    msgs = {"data": [{"type": "user", "content": [{"type": "text", "text": "x"}]},
                     {"type": "assistant", "content": [{"type": "reasoning", "text": "먼저 본다."},
                                                       {"type": "text", "text": "{\"say\": \"안녕\"}"}],
                      "tokens": {"input": 100, "output": 20, "reasoning": 40}}]}
    assert read_answer(msgs) == ("{\"say\": \"안녕\"}", "먼저 본다.", {"input": 100, "output": 20, "reasoning": 40}, None)
    e = _error({"type": "provider.free-limit", "message": "Free usage limit reached.", "status": 429})
    assert e.reason == "rate_limit"
    assert _error({"type": "provider.unknown", "status": 401}).reason == "auth"
    # the words Zen answered a paid call with on an account with no credits: no credit, not a wrong key
    zen = ("Insufficient balance. This request is pay-as-you-go, billed to OpenCode Models credits. Top up at "
           "https://opencode.ai/console/billing. OpenCode Go covers only requests to the OpenCode Go provider.")
    assert _error({"type": "provider.unknown", "message": zen}).reason == "credit"
    assert _error({"type": "provider.unknown", "message": zen, "status": 401}).reason == "credit"


class FakePrivate(PrivateServer):
    def __init__(self, start_error: ProviderError | None = None):
        super().__init__(lambda: Path("/nonexistent"), lambda: "opencode")
        self.calls: list[tuple[str, str, str, int]] = []
        self.start_error = start_error

    async def complete(self, ref, system, user, max_tokens, info):  # noqa: ANN001, ANN201
        if self.start_error is not None:
            raise self.start_error
        self.calls.append((ref.id, system, user, max_tokens))
        from nmb.providers.base import Completion
        return Completion("{}", 5, 10, 2, False, 0.0, reasoning="생각")


def route_with(private: PrivateServer) -> OpenCodeRoute:
    route = OpenCodeRoute(url="http://127.0.0.1:1", password="x", private=private)
    for mid, free in (("big-pickle", True), ("glm-5.3", False)):
        route._info[f"opencode:opencode/{mid}"] = ModelInfo(ModelRef("opencode", "opencode", mid), mid, free=free,
                                                            price_out=0.0 if free else 2.0)
    return route


def test_free_zen_seats_use_nmbs_server_and_paid_ones_stay_on_the_persons() -> None:
    p = FakePrivate()
    route = route_with(p)
    free, paid = ModelRef("opencode", "opencode", "big-pickle"), ModelRef("opencode", "opencode", "glm-5.3")
    assert route.why_no_reasoning(free) == ""
    assert route.why_no_reasoning(paid) != ""  # paid Zen stays on the person's server, without reasoning
    c = asyncio.run(route.complete(free, SYSTEM, USER, 1200))
    assert c.reasoning == "생각" and p.calls == [("big-pickle", SYSTEM, USER, 1200)]


def test_a_server_that_cannot_start_leaves_the_seat_on_the_text_endpoint_and_says_why() -> None:
    p = FakePrivate(ProviderError("off", "did not start"))
    route = route_with(p)
    free = ModelRef("opencode", "opencode", "big-pickle")
    with pytest.raises(ProviderError) as e:  # the text endpoint at port 1 does not answer either
        asyncio.run(route.complete(free, SYSTEM, USER, 1200))
    assert e.value.reason == "network" and p.problem is not None
    assert route.why_no_reasoning(free) == "No reasoning: OpenCode could not start inside NeedMoreBench"


class Echo(BaseHTTPRequestHandler):
    bodies: list[dict] = []

    def log_message(self, *a) -> None:  # noqa: ANN002
        pass

    def do_POST(self) -> None:  # noqa: N802
        Echo.bodies.append(json.loads(self.rfile.read(int(self.headers.get("content-length") or 0))))
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        deltas = [{"role": "assistant", "reasoning_content": "조용히 본다."}, {"content": "{}"}]
        for d in deltas:
            chunk = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "echo",
                     "choices": [{"index": 0, "delta": d, "finish_reason": None}]}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
        end = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "echo",
               "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
        self.wfile.write(f"data: {json.dumps(end)}\n\ndata: [DONE]\n\n".encode())


@pytest.mark.skipif(executable() is None, reason="opencode is not installed")
def test_the_real_opencode_sends_exactly_our_prompt_and_returns_the_reasoning(tmp_path: Path) -> None:
    Echo.bodies = []
    http = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    extra = {"provider": {"echo": {"npm": "@ai-sdk/openai-compatible", "name": "Echo",
                                   "options": {"baseURL": f"http://127.0.0.1:{http.server_address[1]}/v1"},
                                   "models": {"echo": {"name": "Echo"}}}}}
    srv = PrivateServer(lambda: tmp_path, executable, extra_config=extra)
    ref = ModelRef("opencode", "echo", "echo")
    try:
        c = asyncio.run(srv.complete(ref, SYSTEM, USER, 1200, ModelInfo(ref, "Echo", free=True)))
    finally:
        srv.stop()
        http.shutdown()
    assert c.text == "{}" and c.reasoning == "조용히 본다."
    assert len(Echo.bodies) == 1
    body = Echo.bodies[0]
    # nothing but our two messages: no identity, environment or instruction text, no tools, no earlier turns
    assert body["messages"] == [{"role": "system", "content": SYSTEM}, {"role": "user", "content": USER}]
    assert "tools" not in body and body["max_completion_tokens"] == 1200 + REASONING_ROOM
