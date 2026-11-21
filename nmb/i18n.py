"""Interface language: gettext with English source strings and a Korean catalogue.

The catalogue lives as `po/ko.po` in the repository and is compiled in memory at start (generated
files are not committed). The interface follows the system locale unless the settings name a language.
"""
from __future__ import annotations

import ast
import gettext as _gettext
import io
import locale
import os
import struct
from pathlib import Path

DOMAIN = "needmorebench"
PO_DIR = Path(__file__).resolve().parent.parent / "po"
LANGS = {"en": "English", "ko": "한국어"}
_t: _gettext.NullTranslations = _gettext.NullTranslations()
current = "en"


def system_language() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        v = os.environ.get(var, "")
        if v:
            return "ko" if v.lower().startswith("ko") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return "ko" if loc.lower().startswith("ko") else "en"


def read_po(path: Path) -> dict[str, str]:
    """msgid → msgstr for the entries that have a translation (no plurals or contexts are used here)."""
    out: dict[str, str] = {}
    msgid = msgstr = None
    target = None
    for raw in path.read_text(encoding="utf-8").splitlines() + [""]:
        line = raw.strip()
        if line.startswith("msgid "):
            if msgid is not None and msgstr:
                out[msgid] = msgstr
            msgid, msgstr, target = ast.literal_eval(line[6:]), "", "id"
        elif line.startswith("msgstr "):
            msgstr, target = ast.literal_eval(line[7:]), "str"
        elif line.startswith('"') and target == "id" and msgid is not None:
            msgid += ast.literal_eval(line)
        elif line.startswith('"') and target == "str" and msgstr is not None:
            msgstr += ast.literal_eval(line)
        elif not line and msgid is not None:
            if msgstr:
                out[msgid] = msgstr
            msgid = msgstr = target = None
    out.pop("", None)
    return out


def mo_bytes(entries: dict[str, str]) -> bytes:
    """The GNU .mo layout: header, two offset tables, then the strings."""
    entries = {"": "Content-Type: text/plain; charset=UTF-8\n", **entries}  # the header gettext reads the charset from
    keys = sorted(entries)
    ids = b"".join(k.encode() + b"\0" for k in keys)
    strs = b"".join(entries[k].encode() + b"\0" for k in keys)
    n = len(keys)
    start = 7 * 4 + 16 * n
    koffs, voffs, pos = [], [], 0
    for k in keys:
        b = k.encode()
        koffs += [len(b), start + pos]
        pos += len(b) + 1
    pos = 0
    for k in keys:
        b = entries[k].encode()
        voffs += [len(b), start + len(ids) + pos]
        pos += len(b) + 1
    head = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    return head + struct.pack(f"{2 * n}i", *koffs) + struct.pack(f"{2 * n}i", *voffs) + ids + strs


def setup(language: str = "") -> str:
    """Install the catalogue for `language` ("" follows the system). Returns the language in use.

    The catalogue is compiled in memory from `po/<lang>.po` at each start. A compiled file kept in the user's cache
    was shared by every copy of the app on the machine, so a newer copy's strings showed in an older one and the
    other way round."""
    global _t, current
    lang = language if language in LANGS else system_language()
    current = lang
    _t = _gettext.NullTranslations()
    po = PO_DIR / f"{lang}.po"
    if lang != "en" and po.exists():
        _t = _gettext.GNUTranslations(io.BytesIO(mo_bytes(read_po(po))))
    return lang


def _(text: str) -> str:
    return _t.gettext(text)


def ngettext(one: str, many: str, n: int) -> str:
    return _t.ngettext(one, many, n)


def counted(n: int, one: str, many: str, **kw: object) -> str:
    """「1 vote」, 「2 votes」: two plain msgids (Korean has one form for both), formatted with n and kw."""
    return _(one if n == 1 else many).format(n=n, **kw)
