"""Download the pinned opencode release for one platform, check its checksum and unpack it.

    python packaging/fetch_opencode.py windows-x64 build/opencode
    python packaging/fetch_opencode.py darwin-arm64 build/opencode

Writes <out>/opencode(.exe) and <out>/LICENSE; packaging/needmorebench.spec puts that folder next to the app as
`opencode/`, where nmb.providers.opencode.bundled() finds it. Standard library only.
"""
from __future__ import annotations

import hashlib
import io
import json
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

PINS = Path(__file__).resolve().parent / "opencode.json"
BASE = "https://github.com/anomalyco/opencode/releases/download/v{version}/{file}"
LICENSE = "https://raw.githubusercontent.com/anomalyco/opencode/v{version}/LICENSE"


def fetch(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=300) as r:  # noqa: S310  a fixed https address
        data = r.read()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        raise SystemExit(f"checksum mismatch for {url}: {got}")
    return data


def main() -> None:
    platform, out = sys.argv[1], Path(sys.argv[2])
    pins = json.loads(PINS.read_text(encoding="utf-8"))
    asset = pins["assets"][platform]
    data = fetch(BASE.format(version=pins["version"], file=asset["file"]), asset["sha256"])
    name = "opencode.exe" if platform.startswith("windows") else "opencode"
    if asset["file"].endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            body = z.read(next(n for n in z.namelist() if n.rsplit("/", 1)[-1] == name))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            member = next(m for m in t.getmembers() if m.name.rsplit("/", 1)[-1] == name)
            f = t.extractfile(member)
            assert f is not None
            body = f.read()
    out.mkdir(parents=True, exist_ok=True)
    exe = out / name
    exe.write_bytes(body)
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    (out / "LICENSE").write_bytes(fetch(LICENSE.format(version=pins["version"]), pins["license"]["sha256"]))
    print(f"opencode {pins['version']} for {platform} in {out}")


if __name__ == "__main__":
    main()
