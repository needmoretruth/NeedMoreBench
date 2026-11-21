#!/bin/bash
# Build NeedMoreBench.app and its .dmg on macOS from Homebrew's GTK (run from the repository root).
#   packaging/macos/build.sh <version> <arch>     -> dist/NeedMoreBench-<version>-macos-<arch>.dmg
# Steps: Homebrew GTK and PyGObject, a venv on Homebrew's Python, tests, licenses, icons, PyInstaller, smoke, dmg.
set -euo pipefail
VERSION="${1:-dev}"
ARCH="${2:-$(uname -m)}"

export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_ANALYTICS=1
brew install --quiet gtk4 libadwaita pygobject3 adwaita-icon-theme

# the newest Python that Homebrew's PyGObject is built for
PYDEP="$(brew deps --direct pygobject3 | grep '^python@' | sort -V | tail -1)"
PY="$(brew --prefix "$PYDEP")/bin/python3"
"$PY" -m venv --system-site-packages build/venv
VPY=build/venv/bin/python
"$VPY" -m pip install --quiet --upgrade pip
"$VPY" -m pip install --quiet --require-hashes -r packaging/requirements-bundle.txt
"$VPY" -m pip install --quiet -r packaging/requirements-build.txt

"$VPY" -m pytest -q -p no:cacheprovider

"$VPY" packaging/licenses.py --brew --out build/licenses
"$VPY" packaging/icons.py
"$VPY" -m PyInstaller --noconfirm --log-level WARN --distpath dist --workpath build/pyinstaller packaging/needmorebench.spec

# smoke: the built app opens its screens, saves a picture of each and exits with 0
mkdir -p smoke
dist/NeedMoreBench.app/Contents/MacOS/NeedMoreBench --smoke "$PWD/smoke" --record tests/data/smoke.nmb.jsonl

STAGE=build/dmg
rm -rf "$STAGE" && mkdir -p "$STAGE"
cp -R dist/NeedMoreBench.app "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname NeedMoreBench -srcfolder "$STAGE" -ov -format UDZO \
  "dist/NeedMoreBench-$VERSION-macos-$ARCH.dmg"
echo "built dist/NeedMoreBench-$VERSION-macos-$ARCH.dmg"
