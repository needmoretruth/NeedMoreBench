"""App settings in <user config dir>/needmorebench/settings.json (no keys here; keys live in the keyring)."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def user_dir(kind: str) -> Path:
    """GLib's per-user folder of this system ("config" or "data"): ~/.config and ~/.local/share on Linux and
    macOS, %LOCALAPPDATA% on Windows, the app's own folders inside a Flatpak."""
    from gi.repository import GLib
    base = {"config": GLib.get_user_config_dir, "data": GLib.get_user_data_dir}[kind]()
    return Path(base) / "needmorebench"


REAL_CONFIG = user_dir("config")
REAL_HOME = user_dir("data")
_real = False


class RealFolder(RuntimeError):
    """Something other than the app tried to use the user's settings or records."""


def use_real_folders() -> None:
    """Only the app and the command line call this; tests, tools and scratch scripts run with NMB_CONFIG and
    NMB_HOME in a scratch folder, and without them they stop instead of writing the user's folders (:
    a screenshot run once rewrote their saved lobby)."""
    global _real
    _real = True


def folder(var: str, real: Path) -> Path:
    base = os.environ.get(var)
    if base:
        p = Path(base)
        if not _real and p.resolve() == real.resolve():
            raise RealFolder(f"{var} points at the app's real folder")
        return p
    if not _real:
        raise RealFolder(f"{var} is not set; only the app itself uses its real folder")
    return real


def config_dir() -> Path:
    d = folder("NMB_CONFIG", REAL_CONFIG)
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    scheme: str = "light"  # 화면: light (밝게, default) | dark (어둡게) | system (시스템 따라)
    language: str = ""  # interface language: "" follows the system locale, or en | ko
    allow_training: bool = False  # 학습 모델 허용, default off
    sound: bool = True
    volume: float = 0.6
    delay: float = 1.2  # seconds between public lines while watching
    lmstudio_url: str = "http://127.0.0.1:1234/v1"
    lobby: dict[str, Any] = field(default_factory=dict)  # the last lobby, reopened next time
    pools: dict[str, dict[str, Any]] = field(default_factory=dict)  # user pools
    presets: dict[str, dict[str, Any]] = field(default_factory=dict)  # saved lineups by name
    first_run_done: bool = False
    first_run: list[dict[str, Any]] = field(default_factory=list)  # what the first run found: route, where, reason (no keys)
    bench: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def load() -> "Settings":
        p = config_dir() / "settings.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Settings()
        known = Settings.__dataclass_fields__
        return Settings(**{k: v for k, v in d.items() if k in known})

    def save(self) -> None:
        p = config_dir() / "settings.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(p)
