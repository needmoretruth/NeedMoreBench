"""A function that translates with _ never binds _ too (a parameter, loop or unpacked name): inside it _ is then the
argument, and its first translation throws (2026-11-22: a filter's empty view never changed its words)."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "nmb"
FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
SCOPES = FUNCS + (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)  # a comprehension's _ stays inside it


def own_nodes(fn: ast.AST):  # noqa: ANN201
    """The nodes of one function's own scope, without the functions and comprehensions inside it."""
    todo = list(ast.iter_child_nodes(fn))
    while todo:
        n = todo.pop()
        yield n
        if not isinstance(n, SCOPES):
            todo += ast.iter_child_nodes(n)


def binds_and_calls(fn: ast.AST) -> bool:
    a = fn.args  # type: ignore[attr-defined]
    params = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
    nodes = list(own_nodes(fn))
    bound = "_" in params or any(isinstance(n, ast.Name) and n.id == "_" and isinstance(n.ctx, ast.Store) for n in nodes)
    called = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_" for n in nodes)
    return bound and called


def test_no_function_hides_its_translator() -> None:
    bad = []
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad += [f"{path.relative_to(ROOT)}:{n.lineno}" for n in ast.walk(tree) if isinstance(n, FUNCS) and binds_and_calls(n)]
    assert not bad, bad


def test_the_check_sees_the_fault() -> None:
    tree = ast.parse("def f(*_):\n    return _('x')\n\ndef g(*_a):\n    return _('x')\n")
    assert [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and binds_and_calls(n)] == ["f"]
