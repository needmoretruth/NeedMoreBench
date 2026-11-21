"""Write the Flatpak module that installs the pinned Python packages from wheels (no network in the build).

    python3 packaging/flatpak/gen_pip.py   # rewrites packaging/flatpak/python-deps.json

Reads packaging/requirements-bundle.txt (pinned, with hashes), keeps the packages the Linux app needs, and for
each picks the PyPI wheel for the runtime's Python on x86_64 and aarch64 (or the pure-Python wheel), checked
against the pinned hashes.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from packaging.markers import Marker
from packaging.utils import parse_wheel_filename

HERE = Path(__file__).resolve().parent
REQ = HERE.parent / "requirements-bundle.txt"
OUT = HERE / "python-deps.json"
PY = "cp314"  # the Python of org.gnome.Platform 51
ARCHES = {"x86_64": "x86_64", "aarch64": "aarch64"}
SKIP = {"httpx2-jsfetch", "pywin32-ctypes"}  # other systems only


def pinned() -> list[tuple[str, str, set[str], str]]:
    text = REQ.read_text(encoding="utf-8").replace("\\\n", " ")
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;]+)\s*(;[^-]*)?(.*)", line)
        if not m:
            continue
        name, ver, marker, rest = m.group(1), m.group(2), (m.group(3) or "").strip("; "), m.group(4)
        hashes = set(re.findall(r"sha256:([0-9a-f]{64})", rest))
        out.append((name, ver, hashes, marker))
    return out


ENV = {"sys_platform": "linux", "platform_system": "Linux", "os_name": "posix", "platform_python_implementation": "CPython",
       "implementation_name": "cpython", "python_version": "3.14", "python_full_version": "3.14.0"}


def fits(marker: str) -> bool:
    return not marker or Marker(marker).evaluate(ENV)


def runs_on(filename: str, arch: str) -> bool:
    """A wheel the runtime's CPython 3.14 on glibc can load."""
    _n, _v, _b, tags = parse_wheel_filename(filename)
    return any(t.interpreter == PY and t.abi == PY or t.abi == "abi3" and t.interpreter.startswith("cp3")
               for t in tags) and any(t.platform == "any" or t.platform.startswith("manylinux") and t.platform.endswith(arch)
                                      for t in tags)


def pick(name: str, ver: str, hashes: set[str]) -> list[dict]:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{ver}/json", timeout=60) as r:
        files = json.load(r)["urls"]
    wheels = [f for f in files if f["filename"].endswith(".whl") and f["digests"]["sha256"] in hashes]
    pure = [f for f in wheels if all(t.platform == "any" for t in parse_wheel_filename(f["filename"])[3])]
    if pure:
        return [{"type": "file", "url": pure[0]["url"], "sha256": pure[0]["digests"]["sha256"]}]
    out = []
    for arch in ARCHES:
        ok = sorted((f for f in wheels if runs_on(f["filename"], arch)), key=lambda f: (f"{PY}-{PY}" not in f["filename"], f["filename"]))
        if not ok:
            sys.exit(f"no {PY} {arch} wheel for {name} {ver}")
        out.append({"type": "file", "url": ok[0]["url"], "sha256": ok[0]["digests"]["sha256"], "only-arches": [arch]})
    return out


def main() -> None:
    sources, names = [], []
    for name, ver, hashes, marker in pinned():
        if name in SKIP or not fits(marker):
            continue
        names.append(name)
        sources += pick(name, ver, hashes)
    module = {
        "name": "python-deps",
        "buildsystem": "simple",
        "build-commands": ["pip3 install --no-index --no-deps --find-links=. --prefix=${FLATPAK_DEST} " + " ".join(names)],
        "sources": sources,
    }
    OUT.write_text(json.dumps(module, indent=2) + "\n", encoding="utf-8")
    print(f"{len(names)} packages, {len(sources)} wheels -> {OUT.name}")


if __name__ == "__main__":
    main()
