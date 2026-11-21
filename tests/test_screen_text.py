"""How the screen writes and shows things."""
from __future__ import annotations

import ast
from pathlib import Path

from nmb.engine.setup import GameSetup
from nmb.i18n import read_po
from nmb.view import LINE_STYLE, SPEECH

from .helpers import run_game, seats

ROOT = Path(__file__).resolve().parent.parent
BANNED = ("·", "—", "–")  # the user's writing rule: no middle dot and no dashes in Korean text


def test_korean_translations_have_no_middle_dot_or_dash():
    bad = {k: v for k, v in read_po(ROOT / "po/ko.po").items() if any(b in v for b in BANNED)}
    assert not bad, bad


def test_no_string_built_in_code_joins_with_a_middle_dot_or_dash():
    """Every literal in nmb/ (screen text, meta joins, prompts and records the user reads)."""
    bad = []
    for path in sorted((ROOT / "nmb").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and any(b in node.value for b in BANNED):
                bad.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.value[:60]!r}")
    assert not bad, bad


def test_every_event_kind_has_its_own_label_and_style():
    """a thought, a whisper and each night chat look like what they are, never like one another."""
    kinds: set[str] = set()
    for kind, n in (("simple", 7), ("complex", 12)):
        for seed in (1, 5):
            g, _ = run_game(GameSetup(kind=kind, seats=seats(n), seed=seed, role_pool="full" if kind == "complex" else "classic"))
            kinds |= {e.kind for e in g.events}
    missing = kinds - set(LINE_STYLE)
    assert not missing, missing  # a new kind must say how the timeline shows it
    channels = {k: LINE_STYLE[k] for k in SPEECH}
    styles = [s for _l, s in channels.values()]
    assert len(set(styles)) == len(styles), channels
    labelled = [lab for k, (lab, _s) in channels.items() if k != "say"]
    assert len(set(labelled)) == len(labelled) and all(labelled), channels
    assert LINE_STYLE["mafia"][0] == "Mafia night chat" and "{a} → {b}" in LINE_STYLE["whisper"][0]
    ko = read_po(ROOT / "po/ko.po")
    assert ko["Thought"] == "속마음" and ko["Seen by no one"] == "아무도 못 봄"
    assert ko["Mafia night chat"] == "마피아 밤 대화" and ko["Whisper {a} → {b}"] == "귓속말 {a} → {b}"


def test_whispers_and_mafia_chat_happen_only_in_their_own_time():
    g, _ = run_game(GameSetup(kind="simple", seats=seats(8), seed=4))
    step = ""
    for e in g.events:
        if e.kind == "step":
            step = e.data["step"]
        elif e.kind == "phase":
            step = ""
        elif e.kind == "whisper":
            assert e.phase == "day" and step == "귓속말 시간", (e.day, step)
        elif e.kind == "mafia":
            assert e.phase == "night", e.day
        elif e.kind == "thought":
            assert e.to == frozenset({e.actor}) and not e.log  # thinking reaches no prompt and no other player
