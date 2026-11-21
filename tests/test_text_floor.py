"""The desktop text floor: no text in the app is drawn under 13 px. The stylesheet sets no smaller size (px, pt, em
or a relative keyword), no code shrinks text through Pango markup or attributes, and libadwaita's small classes
(caption, row subtitles) are lifted to the floor. tools/text_floor.py measures the drawn sizes on real screens."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "nmb" / "ui" / "style.css").read_text(encoding="utf-8")
FLOOR_PX = 13.0
BASE_PX = 14.67  # GNOME's 11 pt interface font at 96 dpi: what an em or a percentage is taken of


def css_sizes(css: str) -> list[tuple[str, float]]:
    """(declaration, px) for every font-size and font shorthand size in the stylesheet."""
    out: list[tuple[str, float]] = []
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"font(?:-size)?\s*:\s*([^;}]+)", body):
        decl = m.group(0)
        for num, unit in re.findall(r"(\d*\.?\d+)\s*(px|pt|em|rem|%)", m.group(1)):
            v = float(num)
            px = {"px": v, "pt": v * 96 / 72, "em": v * BASE_PX, "rem": v * BASE_PX, "%": v / 100 * BASE_PX}[unit]
            out.append((decl, px))
        if re.search(r"\b(smaller|x-small|xx-small|small)\b", m.group(1)):
            out.append((decl, 0.0))
    return out


def test_no_font_size_under_the_floor_in_the_stylesheet() -> None:
    sizes = css_sizes(CSS)
    assert sizes, "the stylesheet sets sizes; the reader found none"
    low = [(d, round(px, 1)) for d, px in sizes if px < FLOOR_PX]
    assert not low, low


def test_the_reader_catches_small_sizes() -> None:  # the control: the check above can fail
    assert css_sizes(".a { font-size: 12px; }")[0][1] == 12
    assert css_sizes(".a { font-size: 0.8em; }")[0][1] < FLOOR_PX
    assert css_sizes(".a { font-size: smaller; }")[0][1] == 0
    assert css_sizes(".a { font-size: 9pt; }")[0][1] == 12


def test_no_small_text_through_pango_in_code() -> None:
    bad = re.compile(r"<small>|<span[^>]*\b(size|font_size|font)=|font_desc|attr_size_new|attr_scale_new|"
                     r"attr_size_new_absolute|set_size\(\s*\d|FontDescription\.from_string")
    hits = []
    for path in sorted((ROOT / "nmb").rglob("*.py")):
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if bad.search(line):
                hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not hits, hits


def test_libadwaita_small_classes_are_lifted() -> None:
    """caption, caption-heading and row subtitles are drawn at about 12 px by libadwaita; the app lifts them."""
    for sel in (".caption", ".caption-heading", ".subtitle"):
        rule = re.search(re.escape(sel) + r"[^{]*\{[^}]*font-size:\s*(\d+)px", CSS)
        assert rule and float(rule.group(1)) >= FLOOR_PX, sel
