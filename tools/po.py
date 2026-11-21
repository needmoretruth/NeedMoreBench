"""Keep po/ko.po in step with the source: every _("...") string in nmb/ becomes an entry, translations are kept.

    .venv/bin/python -I tools/po.py          # rewrite po/ko.po, print the strings still without Korean
    .venv/bin/python -I tools/po.py --check  # exit 1 if a string has no Korean (tests run this)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nmb.i18n import read_po  # noqa: E402

PO = ROOT / "po" / "ko.po"
HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: ko\\n"\n'


def source_strings() -> dict[str, list[str]]:
    """msgid → where it is used. Reads calls to _() with one literal argument, and the English tables that the
    interface passes through _() (role, step, effort, country names)."""
    out: dict[str, list[str]] = {}
    for path in sorted((ROOT / "nmb").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = str(path.relative_to(ROOT))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    out.setdefault(arg.value, []).append(f"{rel}:{node.lineno}")
    from nmb.engine.roles import EN, TEAM_EN
    from nmb.view import COUNTRY, EFFORT, LINE_STYLE, STEP_EN
    from nmb.providers.base import STATUS_TEXT
    from nmb.ui import bench, bench_view, end, game_page, god, human, picker, records, settings, standings
    tables = [EN.values(), TEAM_EN.values(), COUNTRY.values(), EFFORT.values(), STEP_EN.values(),
              (t for _n, t in picker.FILTERS), (t for _n, t in picker.POOLS), (t for _n, t in game_page.FILTERS),
              (t for t, _s in game_page.SPEEDS), records.TEAM_EN.values(), records.GAME_EN.values(), ["Draw"],
              STATUS_TEXT.values(), (t for _n, t in settings.SCHEMES), settings.WHERE.values(), settings.STORES.values(),
              (s for _n, s, _b, _u in settings.GUIDE), (b for _n, _s, b, _u in settings.GUIDE),
              standings.HEAD, (t for _s, t in standings.SIDES), human.TITLE.values(), human.HINT.values(), human.EXTRA.values(), human.SAY_HINT.values(), (t for _n, t in human.TIME),
              (t for _p, t in god.ON_LIVING), end.TEAM_WON.values(),
              bench.KIND_EN.values(), bench.KIND_SUB.values(), bench_view.STATUS_EN.values(), bench_view.TABLE_HEAD,
              (v[0] for v in LINE_STYLE.values() if v and v[0])]
    for table in tables:
        for s in table:
            out.setdefault(s, []).append("table")
    return out


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def main() -> int:
    have = read_po(PO) if PO.exists() else {}
    strings = source_strings()
    missing = [s for s in strings if not have.get(s)]
    if "--check" in sys.argv:
        for s in missing:
            print(f"no Korean: {s!r} ({strings[s][0]})")
        return 1 if missing else 0
    lines = [HEADER]
    for s in sorted(strings, key=str.lower):
        lines.append(f"#: {strings[s][0]}\nmsgid {quote(s)}\nmsgstr {quote(have.get(s, ''))}\n")
    PO.parent.mkdir(exist_ok=True)
    PO.write_text("\n".join(lines), encoding="utf-8")
    for s in missing:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
