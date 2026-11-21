"""What the game screen shows, built from the event stream alone (no GTK).

The live game and a replay feed the same events into a ViewState, so the screen, the scrubber and the end
screen agree with the saved record. `viewer` is the seat of a playing human without cheats; the
state then keeps only what that seat may see.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine.roles import EN as ROLE_EN, ROLES, TEAM_EN
from .engine.setup import display_name
from .engine.state import Event
from .i18n import _

TEAM_CLASS = {"마피아": "mafia", "시민": "town", "교주": "cult"}
STEP_EN = {"소개": "Introductions", "아침": "Morning", "토론": "Discussion", "귓속말 시간": "Whispers", "투표": "Vote", "최후의 반론": "Last defense",
           "찬반": "Verdict"}


# How the timeline shows each event kind: (channel label msgid, style class), None for a kind that only
# changes state. Each line kind has its own style; the private channels (thought, whisper, the night chats) each
# have their own label so none reads as another (the user read thoughts as models talking to each other).
LINE_STYLE: dict[str, tuple[str, str] | None] = {
    "say": ("", "say"),
    "whisper": ("Whisper {a} → {b}", "whisper"),
    "mafia": ("Mafia night chat", "mafia"),
    "lover": ("Lovers", "lover"),
    "dead": ("The dead", "dead"),
    "thought": ("Thought", "thought"),
    "reasoning": ("Reasoning", "reasoning"),  # the model's own reasoning, its own view, not in 전체
    "phase": ("", "phase-line"),
    "vote_result": ("Vote result", "result-card"),
    "verdict_result": ("Verdict result", "result-card"),
    "end": ("", "end-card"),
    "compaction": ("", "compaction"),
    "system": ("", "system-line"),
    "death": ("", "death"),
    "god": ("God", "god"),
    "moderator": ("Moderator", "moderator"),
    "private": ("Only you know", "private"),
    "saved": ("", "saved"),
    "contact": ("", "contact"),
    "would_end": ("", "would-end"),
    "error": ("", "error"),
    "route": ("", "route"),
    "role": ("", "role-change"),
    "seduce": ("", "seduce"),
    **{k: None for k in ("start", "step", "turns", "poll", "ledger", "note", "call", "thinking", "pause", "human_turn",
                         "contact_hidden", "revive")},
}
SPEECH = ("say", "whisper", "mafia", "lover", "dead", "thought")


def role_label(role: str | None) -> str:
    """A role in the interface language (roles are Korean identifiers inside the engine)."""
    return _(ROLE_EN[role]) if role in ROLE_EN else (role or "")


def step_label(step: str) -> str:
    return _(STEP_EN[step]) if step in STEP_EN else step


def phase_name(day: int, phase: str) -> str:
    return _("Night {n}").format(n=day) if phase == "night" else _("Day {n}").format(n=day)


def team_class(role: str | None) -> str:
    if not role or role not in ROLES:
        return "plain"
    return TEAM_CLASS.get(ROLES[role].team, "plain")


@dataclass
class Row:
    suspicion: int = 50
    guess: str = "모름"
    note: str = ""
    changed: int = -1  # id of the event that last changed it (for the flash)


@dataclass
class SeatView:
    seat: int
    name: str
    role: str
    kind: str = "ai"
    model_line: str = ""  # model, maker, country as the user may see it
    model_name: str = ""
    alive: bool = True
    thinking: bool = False
    ledger: dict[str, Row] = field(default_factory=dict)
    notes: dict[int, str] = field(default_factory=dict)
    thoughts: list[tuple[str, str]] = field(default_factory=list)  # (when, text)
    reasonings: list[tuple[str, str, bool]] = field(default_factory=list)  # (when, text, summarized)
    polls: int = 0
    voters: list[str] = field(default_factory=list)  # who voted for this seat in the last public vote
    votes: int | None = None  # count shown on the card after a vote
    calls: int = 0
    cost: float = 0.0
    failed: int = 0


@dataclass
class ViewState:
    seats: list[SeatView]
    title: str = ""
    viewer: int | None = None  # None: the god view
    owner_sees_models: bool = True
    reveal_dead: bool = True
    day: int = 0
    phase: str = "night"
    step: str = ""
    turns_left: int = 0
    turns_total: int = 0
    result: dict[str, Any] | None = None
    paused: bool = False
    would_end: bool = False
    vote_next: bool = True  # False in the first day's discussion: it ends into night
    lines: list[Event] = field(default_factory=list)  # whispers the viewer may read, for the pair view
    last: Event | None = None

    # ---- building ------------------------------------------------------------------------------------
    @staticmethod
    def from_header(header: dict[str, Any], viewer: int | None = None, reveal_models: bool | None = None) -> "ViewState":
        settings = header.get("settings", {})
        named = settings.get("named", True)
        sees = reveal_models if reveal_models is not None else (named or settings.get("blind_scope", "ai") == "ai")
        seats = []
        for s in header.get("seats", []):
            seats.append(SeatView(s["seat"], s["name"], s.get("role") or "", s.get("kind", "ai"),
                                  model_line=_real_line(s, named) if sees else "", model_name=s.get("model_name") or ""))
        reveal = settings.get("reveal_roles")
        st = ViewState(seats, title=header.get("title", ""), viewer=viewer, owner_sees_models=sees,
                       reveal_dead=reveal if reveal is not None else header.get("game") == "simple")
        st.reset_ledgers()
        return st

    def reset_ledgers(self) -> None:
        for v in self.seats:
            v.ledger = {o.name: Row() for o in self.seats if o is not v}

    def name_of(self, seat: int | None) -> str:
        return self.seats[seat].name if seat is not None and 0 <= seat < len(self.seats) else "?"

    def by_name(self, name: str) -> SeatView | None:
        return next((v for v in self.seats if v.name == name), None)

    def sees(self, e: Event) -> bool:
        return self.viewer is None or e.to is None or self.viewer in e.to

    def role_visible(self, v: SeatView) -> bool:
        """Roles show in the god view, for the viewer's own seat, its known mafia mates, and at the end."""
        if self.viewer is None or self.result is not None or v.seat == self.viewer:
            return True
        if not v.alive and self.reveal_dead:
            return True
        return self.seats[self.viewer].role == "마피아" and v.role == "마피아"  # mafia know each other

    # ---- events --------------------------------------------------------------------------------------
    def apply(self, e: Event) -> bool:
        """Apply one event; True when it is a timeline line the viewer sees."""
        if not self.sees(e):
            return False
        self.last = e
        k, d = e.kind, e.data
        if k == "whisper":
            self.lines.append(e)
        actor = self.seats[e.actor] if e.actor is not None and 0 <= e.actor < len(self.seats) else None
        target = self.seats[e.target] if e.target is not None and 0 <= e.target < len(self.seats) else None
        if k == "phase":
            self.day, self.phase, self.step = e.day, d.get("phase", e.phase), ""
            self.would_end = False
            for v in self.seats:
                v.polls, v.votes, v.voters = 0, None, []
        elif k == "step":
            self.step = d.get("step", e.text)
            self.vote_next = d.get("vote_next", True)
            if self.step == "투표":
                for v in self.seats:
                    v.votes, v.voters = None, []
        elif k == "turns":
            self.turns_left, self.turns_total = d.get("left", 0), d.get("total", 0)
        elif k == "thinking" and actor:
            actor.thinking = bool(d.get("on"))
            return False
        elif k == "poll":
            counts = d.get("counts", {})
            for v in self.seats:
                v.polls = counts.get(v.name, 0)
            return False
        elif k == "ledger" and actor:
            row = actor.ledger.setdefault(d.get("name", e.text), Row())
            new = d.get("new", {})
            row.suspicion, row.guess, row.note = new.get("suspicion", row.suspicion), new.get("guess", row.guess), new.get("note", row.note)
            row.changed = e.id
            return False
        elif k == "note" and actor:
            if d.get("op") == "delete":
                actor.notes.pop(d.get("id"), None)
            else:
                actor.notes[d.get("id")] = e.text
            return False
        elif k == "thought" and actor:
            actor.thoughts.append((self.when(e), e.text))
            return True
        elif k == "reasoning" and actor:
            actor.reasonings.append((self.when(e), e.text, bool(d.get("summarized"))))
            return True
        elif k == "call" and actor:
            actor.calls += 1
            actor.cost += d.get("cost") or 0.0
            if d.get("problem"):
                actor.failed += 1
            return False
        elif k == "error" and actor:
            actor.failed += 1
        elif k == "death" and target:
            target.alive = False
            target.thinking = False
        elif (k == "god" and d.get("power") == "부활" or k == "revive") and target:
            target.alive = True
        elif k == "role" and target and d.get("role") in ROLES:
            target.role = d["role"]
        elif k == "god" and d.get("power") == "역할 바꾸기" and target:
            if d.get("role") in ROLES:
                target.role = d["role"]
        elif k == "vote_result":
            counts = d.get("counts", {})
            voters = d.get("voters", {}) if (d.get("public") or self.viewer is None) else {}
            for v in self.seats:
                v.votes = counts.get(v.name)
                v.voters = list(voters.get(v.name, []))
        elif k == "pause":
            self.paused = bool(d.get("paused"))
            return False
        elif k == "would_end":
            self.would_end = True
        elif k == "end":
            self.result = d.get("result")
            self.phase = "end"
            for v in self.seats:
                v.thinking = False
            roles = d.get("roles") or {}
            for s, r in roles.items():
                if 0 <= int(s) < len(self.seats):
                    self.seats[int(s)].role = r
        elif k == "start":
            for info in d.get("roster", []):
                v = self.seats[info["seat"]]
                v.role = info.get("role") or v.role
            return False
        elif k in ("human_turn", "contact_hidden"):
            return False
        return e.kind not in ("turns", "step")

    def when(self, e: Event) -> str:
        return phase_name(e.day, e.phase)

    # ---- read helpers --------------------------------------------------------------------------------
    def phase_title(self) -> str:
        if self.phase == "end":
            return _("Game over")
        if self.day == 0:
            return _("Setting up")
        return phase_name(self.day, self.phase)

    def thinking_names(self) -> list[str]:
        return [v.name for v in self.seats if v.thinking]

    def team_label(self, role: str) -> str:
        return _(TEAM_EN[ROLES[role].team]) if role in ROLES else ""

    def cost(self) -> float:
        return sum(v.cost for v in self.seats)

    def whisper_pairs(self) -> list[tuple[int, int, int]]:
        """(seat a, seat b, lines) for each pair that whispered, most lines first (pair view)."""
        pairs: dict[tuple[int, int], int] = {}
        for e in self.lines:
            if e.kind == "whisper" and e.actor is not None and e.target is not None:
                k = (min(e.actor, e.target), max(e.actor, e.target))
                pairs[k] = pairs.get(k, 0) + 1
        return sorted(((a, b, n) for (a, b), n in pairs.items()), key=lambda t: -t[2])


EFFORT = {"none": "No reasoning", "minimal": "Minimal reasoning", "low": "Low reasoning", "medium": "Medium reasoning",
          "high": "High reasoning", "xhigh": "Extra high reasoning", "max": "Max reasoning"}


COUNTRY = {"미국": "USA", "중국": "China", "프랑스": "France", "캐나다": "Canada", "한국": "Korea", "일본": "Japan",
           "영국": "UK", "독일": "Germany", "알 수 없음": "Unknown"}


def country_label(c: str | None) -> str:
    return _(COUNTRY.get(c or "", c or "Unknown"))


def effort_label(variant: str | None) -> str:
    return _(EFFORT[variant]) if variant in EFFORT else (variant or _("Default"))


def _real_line(s: dict[str, Any], named: bool) -> str:
    """The line under a seat's name: the full model name (the call name is short), maker, country, effort."""
    if s.get("kind") == "human":
        return _("Person") + (", " + _("as {model}").format(model=s["shown"]) if s.get("disguise") else "")
    bits = [display_name(s.get("model_name"), s.get("model"))]
    if s.get("maker"):
        bits.append(s["maker"])
    if s.get("country"):
        bits.append(country_label(s["country"]))
    if s.get("variant"):
        bits.append(effort_label(s["variant"]))
    if s.get("expert"):
        bits.append(_("Expert"))
    return ", ".join(b for b in bits if b)
