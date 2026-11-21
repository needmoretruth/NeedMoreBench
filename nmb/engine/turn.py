"""One call to one player: what is asked and which answers are legal."""
from __future__ import annotations

from dataclasses import dataclass, field as _f


@dataclass
class TurnRequest:
    kind: str  # discuss vote defense verdict mafia night
    task: str
    field: str | None = None  # the decision key: vote target verdict
    options: list[str] = _f(default_factory=list)
    skip_word: str | None = None  # 기권 / 없음 when skipping is legal
    say: bool = False
    whispers: int = 0
    whisper_to: list[str] = _f(default_factory=list)
    hand: bool = False  # how much the player wants to speak again
    time: bool = False  # may ask for 연장 / 단축, once a day
    poll: bool = False  # may point at one player in the 여론 조사
    extra_field: str | None = None  # a second choice some roles make with this call
    extra_options: list[str] = _f(default_factory=list)
    extra_task: str = ""

    def to_json(self) -> dict:
        return dict(self.__dict__)
