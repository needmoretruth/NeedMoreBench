"""Engine text in the game's dialogue language.

Every line the engine writes (announcements, tasks, rules, labels) is a message: a Korean template used as its
key, with parameters. `Msg.render(lang)` gives the text in Korean or English; prompts render it in the game's
dialogue language, the screen in the interface language, and the record keeps the key, the parameters and the
dialogue-language text. Korean templates mark particles in the format spec: `{role:이었습니다/였습니다}` picks
the form that fits the word's last syllable. Words the engine uses as ids (roles, teams, steps, 찬성, 기권) are
translated when they are parameters, and an English answer is read back to the id (`from_word`).
"""
from __future__ import annotations

import string
from typing import Any

from .words import josa, ro

LANGS = ("ko", "en")


class _Format(string.Formatter):
    def __init__(self, lang: str):
        self.lang = lang

    def format_field(self, value: Any, spec: str) -> str:
        if spec == "으로/로":  # a final ㄹ takes 로 too (경찰로, not 경찰으로)
            return ro(str(value))
        if "/" in spec:  # a Korean particle choice; English templates carry none
            with_b, without_b = spec.split("/", 1)
            return josa(str(value), with_b, without_b)
        return super().format_field(value, spec)

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        return show(self.lang, super().get_value(key, args, kwargs))


class Msg:
    """A message key (the Korean template) and its parameters. Rendered only where the language is known."""
    __slots__ = ("key", "params")

    def __init__(self, key: str, **params: Any):
        self.key, self.params = key, params

    def render(self, lang: str) -> str:
        template = self.key if lang == "ko" else catalog().get(self.key, self.key)
        if not self.params:  # a fixed line (a role's text may hold braces of its own)
            return template
        try:
            return _Format(lang).format(template, **self.params)
        except (KeyError, IndexError, ValueError):
            return _Format("ko").format(self.key, **self.params)

    def record(self) -> dict[str, Any]:
        return {"k": self.key, "p": {k: _rec(v) for k, v in self.params.items()}}

    @staticmethod
    def load(d: Any) -> "Msg | None":
        if isinstance(d, dict) and isinstance(d.get("j"), list):
            return Join([_load(p) for p in d["j"]], str(d.get("s", " ")))
        if not isinstance(d, dict) or not isinstance(d.get("k"), str):
            return None
        return Msg(d["k"], **{k: _load(v) for k, v in (d.get("p") or {}).items()})

    def __str__(self) -> str:
        return self.render("ko")

    def __repr__(self) -> str:
        return f"Msg({self.key!r}, {self.params!r})"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Msg) and (self.key, self.params) == (other.key, other.params)

    def __hash__(self) -> int:
        return hash(self.key)


def T(key: str, **params: Any) -> Msg:
    return Msg(key, **params)


def _rec(v: Any) -> Any:
    """A parameter as JSON: messages as records, lists (a tally's parts, a list of names) element by element."""
    if isinstance(v, Msg):
        return v.record()
    if isinstance(v, (list, tuple)):
        return [_rec(x) for x in v]
    return v


def _load(v: Any) -> Any:
    if isinstance(v, dict):
        return Msg.load(v) or v
    if isinstance(v, list):
        return [_load(x) for x in v]
    return v


class Join(Msg):
    """Several messages (or plain strings) in a row, rendered each in the same language and joined by `sep`."""
    __slots__ = ("parts", "sep")

    def __init__(self, parts: "list[str | Msg]", sep: str = " "):
        super().__init__("")
        self.parts, self.sep = list(parts), sep

    def render(self, lang: str) -> str:
        return self.sep.join(s for s in (say(lang, p) for p in self.parts) if s)

    def record(self) -> dict[str, Any]:
        return {"j": [_rec(p) for p in self.parts], "s": self.sep}

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Join) and (self.parts, self.sep) == (other.parts, other.sep)

    def __hash__(self) -> int:
        return hash(tuple(map(str, self.parts)))

    def __repr__(self) -> str:
        return f"Join({self.parts!r})"


def lines(*parts: "str | Msg", sep: str = " ") -> Join:
    return Join(list(parts), sep)


def show(lang: str, x: Any) -> Any:
    """A message rendered, an id word translated (role, team, step, 찬성...), lists joined; anything else as is."""
    if isinstance(x, Msg):
        return x.render(lang)
    if isinstance(x, (list, tuple)):
        return ", ".join(str(show(lang, v)) for v in x)
    if lang != "ko" and isinstance(x, str):
        return words().get(x, x)
    return x


def say(lang: str, x: "str | Msg | None") -> str:
    """Text for a prompt or a screen in `lang`."""
    if x is None:
        return ""
    return str(show(lang, x))


def from_word(lang: str, value: Any) -> Any:
    """An answer written in the game's language, as the engine's own word ('Yes' → 찬성); names stay names."""
    if lang == "ko" or not isinstance(value, str):
        return value
    return back().get(value.strip().lower(), value)


_CATALOG: dict[str, str] | None = None
_WORDS: dict[str, str] | None = None
_BACK: dict[str, str] | None = None


def catalog() -> dict[str, str]:
    global _CATALOG
    if _CATALOG is None:
        from .en import EN_TEXT
        _CATALOG = EN_TEXT
    return _CATALOG


def words() -> dict[str, str]:
    global _WORDS
    if _WORDS is None:
        from .en import EN_WORDS
        _WORDS = EN_WORDS
    return _WORDS


def back() -> dict[str, str]:
    global _BACK
    if _BACK is None:
        _BACK = {v.lower(): k for k, v in words().items()}
        from .en import EN_ANSWERS
        _BACK.update(EN_ANSWERS)
    return _BACK
