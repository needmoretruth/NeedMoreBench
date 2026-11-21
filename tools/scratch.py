"""Every tool runs on scratch folders, never on the user's settings and records.

Import this before anything from nmb: it points NMB_CONFIG and NMB_HOME at `.scratch/<name>-config` and
`.scratch/<name>-home` unless the caller already set them to some other scratch folder. `owner_lobby()` copies
their settings in read-only (a shot that needs their lobby reads a copy; nothing is ever written back).
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER_SETTINGS = Path.home() / ".config/needmorebench/settings.json"


def use(name: str) -> tuple[Path, Path]:
    out = []
    for var, part in (("NMB_CONFIG", "config"), ("NMB_HOME", "home")):
        d = Path(os.environ.get(var) or ROOT / ".scratch" / f"{name}-{part}")
        d.mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(d)
        out.append(d)
    return out[0], out[1]


def owner_lobby() -> bool:
    """Copy the user's settings into the scratch config once (keys are not in it; they live in the keyring)."""
    dest = Path(os.environ["NMB_CONFIG"]) / "settings.json"
    if dest.exists() or not OWNER_SETTINGS.exists():
        return False
    shutil.copyfile(OWNER_SETTINGS, dest)
    return True
