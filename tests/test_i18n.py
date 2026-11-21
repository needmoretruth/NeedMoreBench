"""Interface language: English source strings, a complete Korean catalogue, the system default."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nmb import i18n

ROOT = Path(__file__).resolve().parent.parent


def test_every_interface_string_has_korean() -> None:
    # -P, not -I: the packages may come from PYTHONPATH (the Flatpak runtime in CI)
    r = subprocess.run([sys.executable, "-P", str(ROOT / "tools/po.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_korean_and_english(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    try:
        assert i18n.setup("ko") == "ko"
        assert i18n._("Day {n}").format(n=2) == "2번째 낮"
        assert i18n._("Start game") == "게임 시작"
        assert i18n._("a string nobody translated") == "a string nobody translated"
        assert i18n.counted(1, "{n} vote", "{n} votes") == i18n.counted(3, "{n} vote", "{n} votes").replace("3", "1") == "1표"
        assert i18n.setup("en") == "en"
        assert i18n._("Start game") == "Start game"
        assert [i18n.counted(k, "{n} vote", "{n} votes") for k in (1, 2)] == ["1 vote", "2 votes"]  # not 「1 votes」
        monkeypatch.setenv("LC_ALL", "ko_KR.UTF-8")
        assert i18n.system_language() == "ko"
        monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
        assert i18n.system_language() == "en"
    finally:
        i18n.setup("en")
