"""Players, their ledgers and notebooks, and the event stream."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

NOTE_PAGE = 1200  # the notebook is one page the player rewrites whole
LEDGER_NOTE_CHARS = 80


@dataclass
class Identity:
    """How a seat looks to others in 기본 mode. A disguised human carries the model it pretends to be."""
    model: str | None = None  # model display name, None for a seat shown as 사람
    maker: str | None = None
    country: str | None = None

    def line(self, lang: str = "ko") -> str:
        """In `lang`: 사람 and the country words are translated, a model's and a maker's names are names."""
        from .text import say
        if self.model is None:
            return say(lang, "사람")
        parts = (self.model, self.maker or "알 수 없음", self.country or "알 수 없음")
        return ", ".join(say(lang, x) for x in parts)  # no middle dot


@dataclass
class LedgerRow:
    suspicion: int = 50  # how likely this player is on another team than the ledger's owner
    guess: str = "모름"
    note: str = ""
    known: bool = False  # 확인됨: the game told the user this player's team and role (a teammate, a lover)


@dataclass
class Notebook:
    """One page the player rewrites whole when it wants; every version stays in the record."""
    page: str = ""
    version: int = 0

    def write(self, text: str) -> bool:
        if len(text) > NOTE_PAGE or text == self.page:
            return False
        self.page, self.version = text, self.version + 1
        return True


@dataclass
class Player:
    seat: int
    name: str
    role: str
    kind: str  # "ai" | "human"
    model_key: str | None = None  # the real model (route:provider/id), None for a human
    model_name: str | None = None  # real model display name
    shown: Identity = field(default_factory=Identity)
    alive: bool = True
    ledger: dict[str, LedgerRow] = field(default_factory=dict)
    notebook: Notebook = field(default_factory=Notebook)
    start_role: str = ""
    contacted: bool = False  # a mafia helper that has met the mafia (접선)
    revealed: bool = False  # role made public (방패병 armour, 시장, 폭로자 article)
    silenced_day: int = 0  # cannot speak on this day (유혹자, 침묵)
    no_vote_day: int = 0  # cannot vote on this day (협박꾼)
    at_rest: bool = False  # laid to rest by the 영매: silent in the dead chat
    died_day: int = 0
    memory: str = ""  # the player's own summary of its oldest history after compaction
    memory_upto: int = -1  # events with id up to this are in the memory, not in the log
    state: dict[str, Any] = field(default_factory=dict)  # ability-owned state (marks, uses, stolen role)
    revelations: list[tuple[int, str]] = field(default_factory=list)  # standing 신의 계시 (id, text),

    @property
    def is_human(self) -> bool:
        return self.kind == "human"


@dataclass
class Event:
    """One thing that happened. `to` None means public; otherwise the seats that may see it.

    `log` events enter players' prompts (if visible to them). Non-log events (thoughts, ledger and note
    edits, thinking indicators) are for the observer only. `key` events survive the engine's fallback collapse.
    """
    id: int
    kind: str
    day: int
    phase: str
    text: str = ""
    actor: int | None = None
    target: int | None = None
    to: frozenset[int] | None = None
    log: bool = True
    key: bool = False
    data: dict[str, Any] = field(default_factory=dict)

    def visible_to(self, seat: int) -> bool:
        return self.to is None or seat in self.to

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        d["to"] = sorted(self.to) if self.to is not None else None
        return d

    @staticmethod
    def from_json(d: dict[str, Any]) -> "Event":
        d = dict(d)
        d["to"] = frozenset(d["to"]) if d.get("to") is not None else None
        return Event(**d)
