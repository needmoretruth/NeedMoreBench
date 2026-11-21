"""Gather the release downloads from the CI artifacts and write the release notes (run by the release workflow).

    python3 packaging/release_notes.py --tag v0.1.0 --repo owner/NeedMoreBench --artifacts artifacts --out release

Writes <out>/files/ (the downloads, named with the version) and <out>/NOTES.md (how to open each download,
and the exact source archives of the app and of the LGPL libraries the Windows and macOS apps carry).
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

NOTES = """\
## Download

| Your computer | File |
|---|---|
| Windows 10 or 11 | {win_setup} (installer) or {win_zip} (no install) |
| Mac with Apple chip (M1 and later) | {mac_arm} |
| Mac with Intel chip | {mac_intel} |
| Linux | {linux} |

These downloads are not signed yet, so your computer asks once before the first start:

- **Windows**: if "Windows protected your PC" appears, click **More info**, then **Run anyway**.
- **Mac**: open the .dmg and drag NeedMoreBench to Applications, then open it. When the Mac says it cannot check the
  app, click **Done**, open System Settings, Privacy & Security, and click **Open Anyway** next to NeedMoreBench.
  On macOS 14 or older you can instead Control-click the app and choose **Open**.
- **Linux**: double-click the .flatpak file to install it in your software center, or run
  `flatpak install --user {linux}`.

## Source code

- NeedMoreBench {tag}: https://github.com/{repo}/archive/refs/tags/{tag}.tar.gz (Apache License 2.0)
- The Linux download runs on the GNOME runtime from Flathub, which carries its own sources.

### Windows

{win_sources}

### macOS

{mac_sources}

Each app also carries these licenses in its `licenses` folder, with THIRD-PARTY.md listing every package.
"""

# (kind, file in the CI artifacts, name in the release). The release names carry no version, so the README links
# .../releases/latest/download/<name> always reach the newest download.
DOWNLOADS = [("win_setup", "*-windows-x64-setup.exe", "NeedMoreBench-Windows-Setup.exe"),
             ("win_zip", "*-windows-x64.zip", "NeedMoreBench-Windows.zip"),
             ("mac_arm", "*-macos-arm64.dmg", "NeedMoreBench-Mac-Apple-chip.dmg"),
             ("mac_intel", "*-macos-x86_64.dmg", "NeedMoreBench-Mac-Intel-chip.dmg"),
             ("linux", "NeedMoreBench-linux-x86_64.flatpak", "NeedMoreBench-Linux.flatpak")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--artifacts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    files = a.out / "files"
    files.mkdir(parents=True, exist_ok=True)
    names: dict[str, str] = {}
    for kind, pattern, name in DOWNLOADS:
        found = sorted(p for p in a.artifacts.rglob(pattern) if p.is_file())  # artifact folders share the names
        if not found:
            raise SystemExit(f"missing download: {pattern}")
        shutil.copyfile(found[0], files / name)
        names[kind] = name

    def sources(folder: str) -> str:
        found = sorted((a.artifacts / folder).rglob("SOURCES.md")) if (a.artifacts / folder).is_dir() else []
        if not found:
            raise SystemExit(f"missing SOURCES.md in {folder}")
        return found[0].read_text(encoding="utf-8").strip()

    (a.out / "NOTES.md").write_text(NOTES.format(tag=a.tag, repo=a.repo, win_sources=sources("package-windows"),
                                                 mac_sources=sources("package-macos-15"), **names), encoding="utf-8")
    print("\n".join(sorted(names.values())))


if __name__ == "__main__":
    main()
