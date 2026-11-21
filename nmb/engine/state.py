"""Players, their ledgers and notebooks, and the event stream."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

NOTE_LIMIT = 20
NOTE_CHARS = 400
LEDGER_NOTE_CHARS = 80


@dataclass
class Identity:
    """How a seat looks to others in 기본 mode. A disguised human carries the model it pretends to be."""
    model: str | None = None  # model display name, None for a seat shown as 사람
    maker: str | None = None
    country: str | None = None

    def line(self) -> str:
        if self.model is None:
            return "사람"
        return ", ".join(x for x in (self.model, self.maker or "알 수 없음", self.country or "알 수 없음"))  # no middle dot


@dataclass
class LedgerRow:
    suspicion: int = 50
    guess: str = "모름"
    note: str = ""


@dataclass
class Note:
    id: int
    text: str


@dataclass
class Notebook:
    notes: list[Note] = field(default_factory=list)
    next_id: int = 1

    def add(self, text: str) -> Note | None:
        if len(self.notes) >= NOTE_LIMIT:
            return None
        n = Note(self.next_id, text[:NOTE_CHARS])
        self.next_id += 1
        self.notes.append(n)
        return n

    def edit(self, nid: int, text: str) -> Note | None:
        for n in self.notes:
            if n.id == nid:
                n.text = text[:NOTE_CHARS]
                return n
        return None

    def delete(self, nid: int) -> Note | None:
        for i, n in enumerate(self.notes):
            if n.id == nid:
                return self.notes.pop(i)
        return None


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
    revealed: bool = False  # role made public (군인 armour, 정치인, 기자 article)
    silenced_day: int = 0  # cannot speak on this day (마담, 침묵)
    no_vote_day: int = 0  # cannot vote on this day (건달)
    at_rest: bool = False  # laid to rest by the 영매: silent in the dead chat
    died_day: int = 0
    memory: str = ""  # the player's own summary of its oldest history after compaction
    memory_upto: int = -1  # events with id up to this are in the memory, not in the log
    state: dict[str, Any] = field(default_factory=dict)  # ability-owned state (marks, uses, stolen role)

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
