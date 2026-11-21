"""Make the Windows .ico and the macOS .icns from the app's PNG icons (build step; needs Pillow).

    python packaging/icons.py   # writes build/icons/needmorebench.ico and needmorebench.icns
"""
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "icons" / "hicolor" / "512x512" / "apps" / "org.needmorebench.NeedMoreBench.png"
OUT = ROOT / "build" / "icons"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    img = Image.open(SRC).convert("RGBA")
    img.save(OUT / "needmorebench.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(OUT / "needmorebench.icns")
    print(f"icons in {OUT}")


if __name__ == "__main__":
    main()
