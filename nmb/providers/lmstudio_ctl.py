"""LM Studio on this machine: find the flatpak install, fix the CLI's home pointer, start the server,
read model sizes.

LM Studio is a flatpak, so its data lives under ~/.var/app/ai.lmstudio.lm-studio/.lmstudio while the `lms` CLI
reads its home from ~/.lmstudio-home-pointer. On this machine the pointer named ~/.lmstudio, which does not exist,
so `lms` could not see the running app. Loading a model that is not loaded yet happens on the first call (JIT);
a large one (the 35B models, 22 GB) took GNOME down on 2026-11-18, so a model above LOAD_LIMIT that is not already
loaded is never called by the app: the user loads it in LM Studio themselves if they want it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from ..i18n import _
from pathlib import Path

FLATPAK_HOME = Path.home() / ".var/app/ai.lmstudio.lm-studio/.lmstudio"
POINTER = Path.home() / ".lmstudio-home-pointer"
LOAD_LIMIT = 4 * 1024 ** 3


LMS = "lms.exe" if sys.platform == "win32" else "lms"
NO_WINDOW: dict[str, int] = {"creationflags": 0x08000000} if sys.platform == "win32" else {}


def home() -> Path | None:
    """LM Studio's own folder: ~/.lmstudio on Windows, macOS and a Linux AppImage, the flatpak's folder on Linux."""
    for p in (FLATPAK_HOME, Path.home() / ".lmstudio"):
        if (p / "bin" / LMS).exists():
            return p
    return None


def fix_pointer() -> tuple[str, str] | None:
    """Point the CLI at the real home. Returns (old, new) when it changed something."""
    h = home()
    if h is None:
        return None
    try:
        old = POINTER.read_text().strip()
    except OSError:
        old = ""
    if old == str(h):
        return None
    POINTER.write_text(str(h))
    return old, str(h)


def lms(*args: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    h = home()
    if h is None:
        raise FileNotFoundError(_("LM Studio is not installed"))
    fix_pointer()
    return subprocess.run([str(h / "bin" / LMS), *args], capture_output=True, text=True, timeout=timeout, **NO_WINDOW)


def start_server() -> tuple[bool, str]:
    try:
        r = lms("server", "start")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return False, str(e)
    out = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, out[-1] if out else ""


def sizes() -> dict[str, int]:
    """Model key -> bytes on disk, from `lms ls --json`. Empty when the CLI is not there."""
    try:
        r = lms("ls", "--json", timeout=30)
        return {m["modelKey"]: int(m.get("sizeBytes") or 0) for m in json.loads(r.stdout)}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError):
        return {}
