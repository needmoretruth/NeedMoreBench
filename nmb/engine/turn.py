"""One call to one player: what is asked and which answers are legal."""
from __future__ import annotations

from dataclasses import dataclass, field as _f

from .text import Msg, say


@dataclass
class TurnRequest:
    kind: str  # discuss vote defense verdict mafia night
    task: "str | Msg"  # rendered in the game's language when the prompt is built
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
    extra_task: "str | Msg" = ""
    limit: float = 0.0  # a person's seconds to answer (a time bar on the card); 0 waits for them
    named_by: str = ""  # a person's reply turn: who named them (shown on the card, never in a prompt)

    def to_json(self, lang: str = "ko") -> dict:
        d = dict(self.__dict__)
        d["task"], d["extra_task"] = say(lang, self.task), say(lang, self.extra_task)
        return d
