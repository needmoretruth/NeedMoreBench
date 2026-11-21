"""Y1: the Flatpak (and the Windows and macOS bundles) ship opencode, so free Zen models work out of the box. The
shipped copy runs only NMB's own server; it never counts as the person's install (it cannot see or start their
server). Without the person's server the model list comes from NMB's own server, and the packaging pins the same
release with the same checksums everywhere."""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

from nmb.providers import opencode
from nmb.providers.base import Completion, ModelRef, ProviderError
from nmb.providers.opencode import OpenCodeRoute
from nmb.providers.opencode_private import PrivateServer

ROOT = Path(__file__).resolve().parent.parent


def test_the_shipped_copy_runs_nmbs_server_and_is_not_the_persons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_bin = tmp_path / "opencode"
    app_bin.write_text("")
    monkeypatch.setattr(opencode, "bundled", lambda: str(app_bin))
    monkeypatch.setattr(opencode.shutil, "which", lambda _n: str(app_bin))  # /app/bin is on PATH in the Flatpak
    monkeypatch.setattr(opencode.Path, "home", lambda: tmp_path / "home")
    assert opencode.executable() is None  # so the lobby never tries to start "their" server with it
    assert opencode.server_executable() == str(app_bin)
    monkeypatch.setattr(opencode.shutil, "which", lambda _n: "/usr/bin/opencode")
    assert opencode.executable() == "/usr/bin/opencode" and opencode.server_executable() == str(app_bin)


def test_where_the_bundles_put_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert opencode.bundled() is None
    (tmp_path / "opencode").mkdir()
    (tmp_path / "opencode" / opencode._name()).write_text("")
    assert opencode.bundled() == str(tmp_path / "opencode" / opencode._name())


class Listing(PrivateServer):
    def __init__(self) -> None:
        super().__init__(lambda: Path("/nonexistent"), lambda: "opencode")
        self.calls: list[str] = []

    async def model_list(self) -> dict:
        return {"data": [{"providerID": "opencode", "id": "big-pickle", "name": "Big Pickle",
                          "cost": [{"input": 0, "output": 0}]}]}

    async def complete(self, ref, system, user, max_tokens, info):  # noqa: ANN001, ANN201
        self.calls.append(ref.id)
        return Completion("{}", 5, 10, 2, False, 0.0, reasoning="생각")


def test_without_the_persons_server_free_zen_still_lists_and_plays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(opencode, "state_file", lambda: tmp_path / "none.json")
    monkeypatch.setattr(opencode, "executable", lambda: None)  # the Flatpak: the person's opencode is out of reach
    p = Listing()
    route = OpenCodeRoute(private=p)
    models = asyncio.run(route.models())
    assert [m.ref.id for m in models] == ["big-pickle"] and models[0].free
    ref = ModelRef("opencode", "opencode", "big-pickle")
    assert route.why_no_reasoning(ref) == ""
    assert asyncio.run(route.complete(ref, "규칙", "상황")).reasoning == "생각" and p.calls == ["big-pickle"]
    assert asyncio.run(route.status())[0] == "ok"
    with pytest.raises(ProviderError) as e:  # no server of NMB's either: the person hears that OpenCode is missing
        asyncio.run(OpenCodeRoute().models())
    assert e.value.reason == "missing"


def test_every_bundle_pins_the_same_release_and_checksums() -> None:
    pins = json.loads((ROOT / "packaging" / "opencode.json").read_text(encoding="utf-8"))
    yml = (ROOT / "packaging" / "flatpak" / "org.needmorebench.NeedMoreBench.yml").read_text(encoding="utf-8")
    for arch, key in (("x86_64", "linux-x64"), ("aarch64", "linux-arm64")):
        asset = pins["assets"][key]
        url = f"https://github.com/anomalyco/opencode/releases/download/v{pins['version']}/{asset['file']}"
        block = re.search(rf"url: {re.escape(url)}\s+sha256: ([0-9a-f]{{64}})", yml)
        assert block and block.group(1) == asset["sha256"], arch
    assert "strip: false" in yml and "no-debuginfo: true" in yml  # stripping cuts off the program's payload
    for script in ("packaging/windows/build.ps1", "packaging/macos/build.sh"):
        assert "fetch_opencode.py" in (ROOT / script).read_text(encoding="utf-8"), script
    assert "opencode" in (ROOT / "packaging" / "needmorebench.spec").read_text(encoding="utf-8")
    assert "opencode" in (ROOT / "NOTICE").read_text(encoding="utf-8")
