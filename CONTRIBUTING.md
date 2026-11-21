# Contributing

## Run from source

NeedMoreBench is Python 3.12 or later with GTK 4, libadwaita 1.7 or later and PyGObject (Fedora 42, Ubuntu 25.04 or later).

**Linux.** Install the system packages, then make a virtual environment that can see them:

```sh
# Fedora
sudo dnf install python3-gobject gtk4 libadwaita
# Debian, Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1

python3 -m venv --system-site-packages .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m nmb
```

`tools/install-desktop.sh` does the same with [uv](https://docs.astral.sh/uv/) and adds NeedMoreBench to the GNOME app grid.

**macOS.** `brew install gtk4 libadwaita pygobject3 adwaita-icon-theme`, then make the virtual environment with Homebrew's Python (`$(brew --prefix pygobject3)/libexec/bin/python3` or the `python3` that `brew info pygobject3` names) and `--system-site-packages` as above.

**Windows.** The simplest way is the GTK build from [gvsbuild](https://github.com/wingtk/gvsbuild): unpack its release zip, add its `bin` folder to `PATH`, and install the PyGObject and pycairo wheels it carries into a Python of the same version. `packaging/windows/build.ps1` shows every step.

## Tests

```sh
.venv/bin/python -m pytest -q
```

The tests use scratch folders for settings and games, never your own, and make no network calls.

Without a window: `.venv/bin/python -m nmb.cli --help` plays and lists games from the command line.

## Packages

- Linux: `flatpak-builder --user --install build packaging/flatpak/org.needmorebench.NeedMoreBench.yml` (GNOME 51 runtime from Flathub).
- macOS: `packaging/macos/build.sh <version> <arch>` makes a .dmg.
- Windows: `packaging/windows/build.ps1 -Version <version> -Gtk <gvsbuild folder>` makes an installer and a zip.

Every push runs the tests and starts the packaged app once on Linux (`.github/workflows/linux.yml`). Changes to the packaging also build and start the Windows and macOS apps (`desktop.yml`). A `v*` tag builds all three downloads into a draft release (`release.yml`).

## Translations

English is in the code. Korean is in `po/ko.po`. After changing a user-facing string, run `.venv/bin/python tools/po.py` to update the catalogue and list the entries still without Korean, then translate them. The tests fail while one is missing.

## Pull requests

Before your first pull request is merged, you agree to the [Contributor License Agreement](CLA.md) ([한국어](CLA.ko.md)). The pull request template has the line to tick.
