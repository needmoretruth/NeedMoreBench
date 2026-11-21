"""Tools and tests never touch the user's settings and records."""
from __future__ import annotations

import importlib.util
import os
import re
from pathlib import Path

import pytest

from nmb import config, store

ROOT = Path(__file__).resolve().parent.parent


def test_tests_run_on_scratch_folders():
    assert config.config_dir().resolve() != config.REAL_CONFIG.resolve()
    assert store.home().resolve() != config.REAL_HOME.resolve()


@pytest.mark.parametrize("var, fn", [("NMB_CONFIG", config.config_dir), ("NMB_HOME", store.home)])
def test_without_a_scratch_folder_nothing_reaches_the_owner(monkeypatch, var, fn):
    monkeypatch.delenv(var)
    with pytest.raises(config.RealFolder):
        fn()


@pytest.mark.parametrize("var, real, fn", [("NMB_CONFIG", config.REAL_CONFIG, config.config_dir),
                                           ("NMB_HOME", config.REAL_HOME, store.home)])
def test_pointing_at_the_owner_folder_is_refused(monkeypatch, var, real, fn):
    monkeypatch.setenv(var, str(real))
    with pytest.raises(config.RealFolder):
        fn()


def test_only_the_app_and_the_cli_open_the_owner_folders():
    calls = [p.relative_to(ROOT).as_posix() for p in (ROOT / "nmb").rglob("*.py")
             if "use_real_folders()" in p.read_text(encoding="utf-8") and p.name != "config.py"]
    assert sorted(calls) == ["nmb/__main__.py", "nmb/cli.py"]
    cli = (ROOT / "nmb/cli.py").read_text(encoding="utf-8")
    assert cli.index("use_real_folders()") > cli.index('if __name__ == "__main__":')  # not when a test calls main()


@pytest.mark.parametrize("tool", ["shots.py", "clickthrough.py"])
def test_screen_tools_set_scratch_folders_before_nmb(tool):
    path = ROOT / "tools" / tool
    if not path.exists():
        pytest.skip("the screen tools stay in the development repository")
    text = path.read_text(encoding="utf-8")
    first_nmb = re.search(r"^from nmb|^import nmb", text, re.M)
    assert first_nmb and text.index("scratch.use(") < first_nmb.start()


def test_scratch_helper_points_inside_the_repo(monkeypatch):
    monkeypatch.delenv("NMB_CONFIG")
    monkeypatch.delenv("NMB_HOME")
    spec = importlib.util.spec_from_file_location("scratch_tool", ROOT / "tools/scratch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg, home = mod.use("unit")
    try:
        assert cfg == ROOT / ".scratch/unit-config" and home == ROOT / ".scratch/unit-home"
        assert os.environ["NMB_CONFIG"] == str(cfg)
    finally:
        cfg.rmdir()
        home.rmdir()
