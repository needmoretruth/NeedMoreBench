"""Keys on every system (keyring package) and their reads during a game: many threads and async calls at once,
a store that fails now and then, and never "no key" when the store did not answer."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

from nmb import keys
from nmb.providers import opencode
from nmb.providers.base import ProviderError
from nmb.providers.health import classify, words
from nmb.providers.openai_compat import OpenRouterRoute


class FlakyStore:
    """A keyring backend that fails the first `fail` reads of each route and counts concurrent use."""

    def __init__(self, data: dict[str, str], fail: int = 0, always: bool = False, empty: int = 0):
        self.data = dict(data)
        self.empty = empty
        self.fail = {r: fail for r in keys.ROUTES}
        self.always = always
        self.reads = 0
        self.inside = 0
        self.most_inside = 0
        self._count = threading.Lock()

    def get_password(self, service: str, route: str) -> str | None:
        assert service == keys.SERVICE
        with self._count:
            self.inside += 1
            self.most_inside = max(self.most_inside, self.inside)
            self.reads += 1
        try:
            if self.always or self.fail.get(route, 0) > 0:
                self.fail[route] = self.fail.get(route, 0) - 1
                raise RuntimeError("org.freedesktop.DBus.Error.NoReply")
            if self.empty > 0:
                self.empty -= 1
                return None
            return self.data.get(route)
        finally:
            with self._count:
                self.inside -= 1

    def set_password(self, service: str, route: str, key: str) -> None:
        self.data[route] = key

    def delete_password(self, service: str, route: str) -> None:
        self.data.pop(route, None)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch):
    def use(s: FlakyStore) -> FlakyStore:
        monkeypatch.setattr(keys, "_backend", s)
        monkeypatch.setattr(keys.time, "sleep", lambda _s: None)
        keys.reload()
        return s
    yield use
    keys.reload()


KEY = "test-" + "x" * 20


def test_concurrent_reads_with_a_flaky_store_all_get_the_key(store) -> None:
    s = store(FlakyStore({"openrouter": KEY, "anthropic": KEY + "a"}, fail=1))
    got: list[str | None] = []
    errors: list[BaseException] = []

    def reader() -> None:
        for _ in range(50):
            try:
                got.append(keys.get("openrouter"))
                got.append(keys.get("anthropic"))
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=reader) for _ in range(16)]
    for t in threads:
        t.start()

    async def many() -> list[str | None]:
        return await asyncio.gather(*(asyncio.to_thread(keys.get, "openrouter") for _ in range(64)))

    got.extend(asyncio.run(many()))
    for t in threads:
        t.join()
    assert not errors
    assert len(got) == 16 * 100 + 64
    assert all(k in (KEY, KEY + "a") for k in got)
    assert s.most_inside == 1  # one access to the store at a time
    assert s.reads == 4  # each route: one failed read, one retry; then memory


def test_a_store_that_does_not_answer_is_not_no_key(store) -> None:
    store(FlakyStore({"openrouter": KEY}, always=True))
    with pytest.raises(keys.KeyringError) as caught:
        keys.get("openrouter")
    assert caught.value.reason == "keyring"
    assert not keys.has("openrouter")  # Settings shows the entry as empty, nothing is overwritten
    route = OpenRouterRoute(lambda: keys.get("openrouter"), lambda: False)
    with pytest.raises(ProviderError) as e:
        route.headers()
    assert e.value.reason == "keyring" and e.value.retryable
    said = words("Seat", classify(e.value), "openrouter")
    assert "keyring" in said and "there is no" not in said


def test_an_empty_answer_for_a_stored_key_is_asked_again(store) -> None:
    store(FlakyStore({"openrouter": KEY}, empty=1))
    assert keys.get("openrouter") == KEY


def test_a_failed_read_is_asked_again_later(store) -> None:
    s = store(FlakyStore({"venice": KEY}, always=True))
    with pytest.raises(keys.KeyringError):
        keys.get("venice")
    s.always = False
    assert keys.get("venice") == KEY  # a failure is not kept in memory


def test_put_and_forget_change_what_is_read(store) -> None:
    s = store(FlakyStore({}))
    assert keys.get("anthropic") is None
    assert keys.put("anthropic", f"  {KEY}  ")
    assert keys.get("anthropic") == KEY and s.data["anthropic"] == KEY
    keys.forget("anthropic")
    assert keys.get("anthropic") is None and "anthropic" not in s.data


def test_without_a_key_store_a_key_lasts_for_the_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(keys, "_keyring", lambda: None)
    keys._cache.clear()
    assert not keys.available() and keys.get("openrouter") is None
    assert keys.put("openrouter", KEY)
    keys.reload()
    assert keys.get("openrouter") == KEY
    keys.forget("openrouter")
    assert keys.get("openrouter") is None
    keys._cache.clear()


def test_korean_is_compiled_from_the_catalogue_each_start() -> None:
    from nmb import i18n
    try:
        i18n.setup("ko")
        assert i18n._("Connect a model") == "모델 연결"  # no compiled file left from another copy of the app
    finally:
        i18n.setup("en")


def test_found_on_machine_reads_the_standard_variables_and_opencode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FLATPAK_ID", raising=False)  # the tests also run inside the Flatpak in CI
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VENICE_API_KEY", "  ")
    auth = tmp_path / "opencode" / "auth.json"
    auth.parent.mkdir()
    auth.write_text(json.dumps({"openrouter": {"key": KEY}, "anthropic": {"type": "oauth"}, "venice": {"key": KEY + "v"}}))
    found = keys.found_on_machine()
    assert found["openrouter"] == [("OPENROUTER_API_KEY", KEY)]  # the same key from two places is tested once
    assert found["anthropic"] == []
    assert found["venice"] == [("opencode", KEY + "v")]


def test_inside_the_flatpak_opencode_files_are_under_the_host_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FLATPAK_ID", "org.needmorebench.NeedMoreBench")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "sandbox"))  # the sandbox points XDG folders into the app's own
    monkeypatch.setattr(opencode.Path, "home", staticmethod(lambda: tmp_path))
    assert keys.opencode_auth_file() == tmp_path / ".local" / "share" / "opencode" / "auth.json"


def _no_opencode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(opencode.shutil, "which", lambda _n: None)
    monkeypatch.setattr(opencode.Path, "home", staticmethod(lambda: tmp_path))


def test_opencode_not_installed_is_its_own_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_opencode(monkeypatch, tmp_path)
    assert opencode.executable() is None
    reason, _text = asyncio.run(opencode.OpenCodeRoute().status())
    assert reason == "missing"


def test_opencode_server_left_its_address_behind(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_opencode(monkeypatch, tmp_path)
    state = tmp_path / "state" / "opencode" / "service.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"url": "http://127.0.0.1:9", "password": "p"}))
    reason, _text = asyncio.run(opencode.OpenCodeRoute().status())
    assert reason == "missing"  # nothing answers there and no program to start: not installed
    exe = tmp_path / ".opencode" / "bin" / ("opencode.exe" if sys.platform == "win32" else "opencode")
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert opencode.executable() == str(exe)
    reason, _text = asyncio.run(opencode.OpenCodeRoute().status())
    assert reason == "off"  # installed, not running: Settings offers Start
