"""Every message key the engine can send, found the way the catalog test and the translator need it:
the literal first argument of each T() call in the engine and the harness, and the texts that are keys by
role (role descriptions, ability choice lines, expert sections)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(ROOT.glob("engine/**/*.py")) + [ROOT / "harness.py"]


def literal_keys() -> dict[str, str]:
    """key → where it is written (file:line)."""
    out: dict[str, str] = {}
    for f in SOURCES:
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "T" and node.args:
                a = node.args[0]
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    out.setdefault(a.value, f"{f.relative_to(ROOT)}:{node.lineno}")
    return out


def data_keys() -> dict[str, str]:
    from . import abilities  # noqa: F401  (registers every ability)
    from .abilities.base import REGISTRY
    from .expert import COMMON, CULT_TEXT, MAFIA_TEXT, ROLE_TEXT, TOWN_TEXT
    from .roles import ROLES
    out = {r.text: f"role {r.name}" for r in ROLES.values()}
    for key, ab in REGISTRY.items():
        out.setdefault(ab.act_text, f"ability {key}")
        out.setdefault(ab.pass_text, f"ability {key}")
    for name, text in [("COMMON", COMMON), ("TOWN", TOWN_TEXT), ("MAFIA", MAFIA_TEXT), ("CULT", CULT_TEXT)]:
        out[text] = f"expert {name}"
    for role, text in ROLE_TEXT.items():
        out[text] = f"expert {role}"
    return out


def all_keys() -> dict[str, str]:
    return {**data_keys(), **literal_keys()}
