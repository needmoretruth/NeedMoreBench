"""Routes against fake servers: status lines, the data-collection guard, effort, no key in errors."""
from __future__ import annotations

import asyncio
import json

import httpx
import httpx2
import pytest

from nmb.providers.anthropic_api import AnthropicRoute
from nmb.providers.base import ModelRef, ProviderError
from nmb.providers.openai_compat import LMStudioRoute, OpenRouterRoute

KEY = "sk-or-v1-" + "x" * 40


@pytest.fixture(autouse=True)
def korean(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """Status lines are checked as a Korean user reads them."""
    from nmb import i18n
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    i18n.setup("ko")
    yield
    i18n.setup("en")


def run(c):  # type: ignore[no-untyped-def]
    return asyncio.run(c)


def openrouter(handler, allow=False, key=KEY):  # type: ignore[no-untyped-def]
    r = OpenRouterRoute(lambda: key, lambda: allow)
    r.transport = httpx.MockTransport(handler)
    return r


def chat_ok(seen: list[dict]):  # type: ignore[no-untyped-def]
    def h(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"say\": \"안녕하세요\"}"}}],
                                         "usage": {"prompt_tokens": 120, "completion_tokens": 9, "cost": 0.00002}})
    return h


@pytest.mark.parametrize("allow", [False, True])
def test_openrouter_data_collection_follows_the_switch(allow: bool) -> None:
    seen: list[dict] = []
    c = run(openrouter(chat_ok(seen), allow).complete(ModelRef("openrouter", "openrouter", "a/b:free"), "s", "u"))
    assert c.text and c.cost == 0.00002 and not c.estimated
    if allow:
        assert "provider" not in seen[0]
    else:
        assert seen[0]["provider"] == {"data_collection": "deny"}


def test_openrouter_effort_goes_as_reasoning() -> None:
    seen: list[dict] = []
    run(openrouter(chat_ok(seen)).complete(ModelRef("openrouter", "openrouter", "a/b", "high"), "s", "u"))
    assert seen[0]["reasoning"] == {"effort": "high"}


def test_openrouter_status_lines() -> None:
    def bad(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "User not found.", "code": 401}})
    reason, text = run(openrouter(bad).status())
    assert reason == "auth" and text.endswith("키가 맞지 않습니다") and KEY not in text

    def empty(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"total_credits": 5, "total_usage": 5}})
    assert run(openrouter(empty).status())[0] == "credit"

    def poor(req: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": "Insufficient credits"}})
    with pytest.raises(ProviderError) as e:
        run(openrouter(poor).complete(ModelRef("openrouter", "openrouter", "a/b"), "s", "u"))
    assert e.value.reason == "credit" and str(e.value).endswith("크레딧이 없습니다")

    assert run(OpenRouterRoute(lambda: None, lambda: False).status())[0] == "nokey"


def test_openrouter_models_marks_free_and_effort() -> None:
    def models(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [
            {"id": "z-ai/glm-5:free", "name": "Z.ai: GLM 5 (free)", "pricing": {"prompt": "0", "completion": "0"},
             "context_length": 128000, "supported_parameters": ["reasoning"]},
            {"id": "openrouter/auto", "name": "Auto", "pricing": {"prompt": "-1", "completion": "-1"}},
        ]})
    got = run(openrouter(models).models())
    assert [m.ref.id for m in got] == ["z-ai/glm-5:free"]
    assert got[0].free and got[0].variants and got[0].name == "GLM 5 (free)"


def test_lmstudio_off_and_on() -> None:
    off = LMStudioRoute(lambda: "http://127.0.0.1:9/v1")

    def refuse(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")
    off.transport = httpx.MockTransport(refuse)
    assert run(off.status())[0] == "off"

    on = LMStudioRoute(lambda: "http://127.0.0.1:1234/v1",
                       sizes=lambda: {"lfm3-1.7b": 1_600_000_000, "qwen3.6-35b": 22_000_000_000})
    on.transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [
        {"id": "lfm3-1.7b", "type": "llm", "state": "not-loaded"},
        {"id": "qwen3.6-35b", "type": "vlm", "state": "not-loaded"},
        {"id": "text-embedding-nomic", "type": "embeddings", "state": "not-loaded"}]}))
    assert run(on.status()) == ("ok", "모델 1개")
    with pytest.raises(ProviderError) as e:  # a 22 GB model is never loaded by the app (2026-11-18 incident)
        run(on.complete(ModelRef("lmstudio", "lmstudio", "qwen3.6-35b"), "s", "u"))
    assert e.value.reason == "refused"


def anthropic_route(handler, key: str | None = "sk-ant-test"):  # type: ignore[no-untyped-def]
    r = AnthropicRoute(lambda: key)
    r.base_url = "http://fake.anthropic"
    r.http_client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return r


def test_anthropic_status_lines() -> None:
    def bad(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error",
                                                                     "message": "invalid x-api-key"}})
    assert run(anthropic_route(bad).status()) == ("auth", "Anthropic: 키가 맞지 않습니다")

    def poor(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(400, json={"type": "error", "error": {"type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Anthropic API."}})
    assert run(anthropic_route(poor).status()) == ("credit", "Anthropic: 크레딧이 없습니다")
    assert run(anthropic_route(poor, key=None).status())[0] == "nokey"


def test_anthropic_effort_and_cost() -> None:
    seen: list[dict] = []

    def ok(req: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(req.content))
        return httpx2.Response(200, json={"id": "m", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
                                         "content": [{"type": "text", "text": "{\"say\": \"네\"}"}],
                                         "stop_reason": "end_turn", "stop_sequence": None,
                                         "usage": {"input_tokens": 1000, "output_tokens": 100}})
    c = run(anthropic_route(ok).complete(ModelRef("anthropic", "anthropic", "claude-haiku-5-5", "low"), "s", "u"))
    assert seen[0]["output_config"] == {"effort": "low"} and seen[0]["system"] == "s"
    assert c.text == "{\"say\": \"네\"}" and abs(c.cost - (1000 * 0.10 + 100 * 0.50) / 1e6) < 1e-12
