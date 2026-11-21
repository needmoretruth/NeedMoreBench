"""The ability interface every role module implements, the night context, and the registry.

At night the engine asks each living player's ability what it wants, collects all answers at once, then
resolves them in priority order: 10 blocks and marks, 20 protections, 30 kills (then attacks resolve),
40 information, 50 revivals, 60 what others did. Day hooks cover vote weight, extra choices at the vote and
the last defence, execution immunity, the verdict, deaths, the morning, and roles that keep a tied game alive.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..roles import CULT, MAFIA, ROLES, TOWN
from ..text import Msg, T

if TYPE_CHECKING:
    from ..game import Game
    from ..state import Player
    from ..turn import TurnRequest


@dataclass
class Attack:
    source: str  # mafia | beast | terror | vigilante | mercenary | hitman | god
    target: str
    attacker: int | None = None  # the mafia attack: the seat whose pick set the target (복수자 shoots it)
    pierce: bool = False  # ignores the 의사 and the target's own traits (대부)


@dataclass
class NightContext:
    night: int
    protected: set[str] = field(default_factory=set)  # saved from the mafia attack (의사, 조수)
    blocked: set[str] = field(default_factory=set)  # no ability tonight (유혹자)
    attacks: list[Attack] = field(default_factory=list)
    deaths: list[tuple[str, str]] = field(default_factory=list)  # (name, cause)
    morning: "list[str | Msg]" = field(default_factory=list)  # public lines for the morning
    used_on: dict[int, str] = field(default_factory=dict)  # seat → target name (미행꾼)
    answers: dict[int, dict[str, Any]] = field(default_factory=dict)  # seat → the whole night answer
    mafia_target: str | None = None

    def dying(self, name: str) -> bool:
        return any(n == name for n, _c in self.deaths)


class Ability:
    key = "none"
    priority = 100
    blockable = True
    helper = False  # mafia helper: does not know the mafia until contact
    kills = False  # chooses the night kill in the mafia meeting
    act_text = "{t}님에게 능력을 씁니다"  # the night choice in words, and the pass
    pass_text = "아무에게도 능력을 쓰지 않습니다"

    # ---- night ---------------------------------------------------------------------------------------
    def night_request(self, game: "Game", p: "Player") -> "TurnRequest | None":
        return None

    def acting(self, p: "Player") -> "Ability":
        """The ability whose words describe tonight's choice (a 모방자 uses the stolen one)."""
        return self

    def priority_for(self, p: "Player") -> int:
        """Where this player's night action resolves (a 모방자 takes the stolen role's place)."""
        return self.priority

    def is_killer(self, game: "Game", p: "Player") -> bool:
        """Picks the night kill in the mafia meeting (a tamed 야수, a contacted 대부)."""
        return self.kills

    def pierce(self, game: "Game", p: "Player") -> bool:
        """While this player lives, the mafia attack ignores protection and traits (대부)."""
        return False

    def nightfall(self, game: "Game", p: "Player", ctx: "NightContext") -> None:
        """At the start of a night, before anyone answers (도청꾼's result, 대부's contact)."""

    async def act(self, game: "Game", p: "Player", target: str | None, ctx: NightContext) -> None:
        pass

    def on_attack(self, game: "Game", p: "Player", attack: Attack, ctx: NightContext) -> str:
        """'die', 'survive' (announced in the morning by the ability) or 'silent' (nothing shows)."""
        return "die"

    def while_dead(self, game: "Game", p: "Player", ctx: NightContext) -> None:
        """Runs for a dead player at the end of each night (불사신 comes back)."""

    def morning(self, game: "Game", p: "Player", ctx: NightContext) -> None:
        pass

    # ---- start, status and identity ------------------------------------------------------------------
    def on_start(self, game: "Game", p: "Player") -> None:
        """What the player learns when the game starts (연인: the partner)."""

    def status(self, p: "Player") -> "str | Msg | None":
        """One line of role state the player is reminded of in every prompt."""
        return None

    def looks_mafia(self, p: "Player") -> bool:
        """What the 경찰 learns."""
        return p.role == "마피아"

    # ---- day -----------------------------------------------------------------------------------------
    def vote_weight(self, p: "Player") -> int:
        return 1

    def vote_extra(self, game: "Game", p: "Player") -> "TurnRequest | None":
        """A second choice asked together with the vote (모방자: whose ability to steal)."""
        return None

    def after_vote(self, game: "Game", p: "Player", vote: str | None, extra: Any) -> None:
        """`extra` is the raw answer to vote_extra's field (names are matched by the ability)."""

    def defense_extra(self, game: "Game", p: "Player") -> "TurnRequest | None":
        """A choice asked with the last defence (폭탄마: whom to take along)."""
        return None

    def defense_choice(self, game: "Game", p: "Player", extra: Any) -> None:
        """The answer to defense_extra, as soon as it is given (shown as an action)."""

    def executable(self, game: "Game", p: "Player") -> bool:
        return True

    def spare(self, game: "Game", p: "Player", cand: "Player") -> bool:
        """Called for every living player before cand is executed; True saves cand (위장꾼 saves itself)."""
        return False

    def override_verdict(self, game: "Game", p: "Player", pick: str | None, passed: bool) -> bool | None:
        """The 배심장 decides the 찬반: a new outcome, or None to leave it."""
        return None

    def on_executed(self, game: "Game", p: "Player", extra: str | None) -> None:
        pass

    def last_shot(self, game: "Game", p: "Player") -> "TurnRequest | None":
        """A choice the executed player makes after the 찬반 (사냥꾼: whom to take along)."""
        return None

    def take_shot(self, game: "Game", p: "Player", pick: str | None) -> None:
        pass

    def on_death(self, game: "Game", p: "Player", cause: str, ctx: NightContext | None) -> None:
        pass

    def holds_game(self, game: "Game", p: "Player") -> bool:
        """A swing role that can still change a tied count keeps the game going."""
        return False

    def wins(self, game: "Game", p: "Player") -> bool:
        """This living player wins the game for its side now (기수 alive on the 4th day)."""
        return False


REGISTRY: dict[str, Ability] = {"none": Ability()}


def register(cls: type[Ability]) -> type[Ability]:
    REGISTRY[cls.key] = cls()
    return cls


def ability_of(role: str) -> Ability:
    return REGISTRY[ROLES[role].ability]


def ability_for(p: "Player") -> Ability:
    """The ability this player has now: a frog (마녀) has none until the next night."""
    return REGISTRY["none"] if p.state.get("frog") else ability_of(p.role)


def side(p: "Player") -> str:
    """The team this player wins with: converts win with the cult, helpers with the mafia."""
    return CULT if p.state.get("cult") is not None else ROLES[p.role].team


def in_mafia_team(p: "Player") -> bool:
    """Counted and seated with the mafia: the 마피아 and contacted helpers."""
    return side(p) == MAFIA and (not ability_of(p.role).helper or p.contacted)


def in_cult(p: "Player") -> bool:
    return side(p) == CULT


def target_names(game: "Game", p: "Player", include_self: bool = False) -> list[str]:
    return [q.name for q in game.alive() if include_self or q is not p]


def announce(game: "Game", p: "Player", what: "str | Msg", target: "Player | None" = None, to: frozenset[int] | None = None,
             role: str | None = None) -> None:
    """every ability use (or pass) is an `action` line: the god view reads 「의사 ERNIE님이 …」, the actor
    reads 「너는 …」 and its own prompt keeps it as its own memory. Nobody else learns it unless `to` says so."""
    role = role or p.role
    game.emit("action", T("{role} {name}님이 {what}", role=role, name=p.name, what=what), actor=p.seat,
              target=target.seat if target else None, to=to if to is not None else frozenset({p.seat}), key=False,
              role=role, what=game.t(what))


def choose_text(ab: "Ability", game: "Game", target: str | None) -> Msg:
    """What a night choice means, in words: 「Hy님을 지킵니다」 or the role's pass line."""
    return T(ab.act_text, t=target) if target else T(ab.pass_text)


def dead_names(game: "Game", rested: bool = True) -> list[str]:
    return [q.name for q in game.players if not q.alive and (rested or not q.at_rest)]


def contact(game: "Game", p: "Player") -> None:
    """A helper meets the mafia: both sides learn who the other is."""
    if p.contacted:
        return
    p.contacted = True
    mates = [q for q in game.players if q is not p and in_mafia_team(q)]
    game.private(p, T("마피아와 접선했다. 마피아 팀: {mates}. 이제 마피아 회의에 낀다.",
                      mates=[T("{name}({role})", name=q.name, role=q.role) for q in mates]), knows=[q.seat for q in mates])
    for q in mates:
        game.know(p, q)
        if q.alive:
            game.private(q, T("{who:이/가} 마피아 팀과 접선했다.", who=T("{name}({role})", name=p.name, role=p.role)),
                         knows=[p.seat])
            game.know(q, p)
    game.observe("contact", T("{who:이/가} 마피아와 접선했습니다.", who=T("{name}({role})", name=p.name, role=p.role)), actor=p.seat)


def learned(game: "Game", p: "Player", q: "Player", role: str | None = None) -> None:
    """p learned q's role; what the citizen team learns feeds the 소문꾼."""
    if side(p) == TOWN and q is not p:
        game.town_learned.append((q.name, role or q.role))


def tied(game: "Game") -> bool:
    """The mafia team and everyone else are level: the next death decides."""
    alive = game.alive()
    mafia = sum(1 for q in alive if in_mafia_team(q))
    return 0 < mafia and mafia * 2 == len(alive)


def mafia_alive(game: "Game") -> bool:
    return any(q.alive and q.role == "마피아" for q in game.players)


def rng(game: "Game") -> random.Random:
    return game.rng
