#!/usr/bin/env bash
# Install NeedMoreBench as an app on this GNOME desktop: a venv beside the code (system PyGObject and numpy, pip
# packages on top), the icon in the user's hicolor theme, and a launcher in the app grid. Run again after pulling a
# new version; it only refreshes what changed. Usage: tools/install-desktop.sh [repo dir, default: this repo]
set -euo pipefail
REPO="$(cd "${1:-$(dirname "$0")/..}" && pwd)"
APP_ID=org.needmorebench.NeedMoreBench
cd "$REPO"
if [ ! -x .venv/bin/python ]; then
  uv venv --system-site-packages --python /usr/bin/python3 .venv >/dev/null
fi
if [ -f requirements.txt ]; then
  uv pip install --python .venv/bin/python -q -r requirements.txt
fi
for d in data/icons/hicolor/*/apps; do
  size="$(basename "$(dirname "$d")")"
  mkdir -p "$HOME/.local/share/icons/hicolor/$size/apps"
  cp -f "$d/$APP_ID.png" "$HOME/.local/share/icons/hicolor/$size/apps/$APP_ID.png"
done
gtk-update-icon-cache -q -t -f "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/$APP_ID.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=NeedMoreBench
Comment=Language models play Mafia; watch, meddle or join
Comment[ko]=언어 모델들의 마피아 게임을 관전하고 끼어들고 함께 하기
Exec=$REPO/.venv/bin/python -m nmb
Path=$REPO
Icon=$APP_ID
Terminal=false
Categories=Game;
StartupNotify=true
StartupWMClass=$APP_ID
DESKTOP
update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "installed: $HOME/.local/share/applications/$APP_ID.desktop"
