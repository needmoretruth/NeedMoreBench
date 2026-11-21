"""What a game is started with, and turning that into seated players."""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from .abilities import REGISTRY
from .lineups import CUSTOM, Judge, by_counts, counts_problem, lineup, mode_of, named_problem
from .roles import EN, COMPLEX, canon_tree, DEFAULT_PLAYERS, GAME_ROLES, PLAYER_RANGE, ROLES, SIMPLE, MAFIA
from ..i18n import _
from .names import LINES, call_names
from .state import Identity, LedgerRow, Player

KO_NAMES = ["민지", "준호", "서연", "지훈", "하은", "도윤", "수아", "현우", "지우", "예준", "채원", "시우", "유나", "건우",
            "다은", "태윤", "소율", "은호", "나연", "재민"]
EN_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Ethan", "Mia", "Lucas", "Chloe", "Owen", "Grace", "Jack",
            "Ella", "Ryan", "Nora", "Leo", "Ruby", "Sam", "Ivy", "Max"]


@dataclass
class SeatSpec:
    kind: str = "ai"  # ai | human
    model_key: str | None = None  # route:provider/id
    model_name: str | None = None
    maker: str | None = None
    country: str | None = None
    variant: str | None = None  # reasoning effort when the route offers one
    variant_random: bool = False  # 랜덤: drawn at game start from the model's levels
    expert: bool | None = None  # 전문가 모드 for this seat; None follows the game switch
    compact_at: int | None = None  # a lower compaction point for this seat
    role: str | None = None  # a chosen role, None for 랜덤
    pool: str | None = None  # 랜덤 seat: the pool its model is drawn from at game start
    # human only
    human_name: str = ""
    disguise_key: str | None = None  # AI인 척: the model the human pretends to be
    disguise_name: str | None = None
    disguise_maker: str | None = None
    disguise_country: str | None = None


@dataclass
class GameSetup:
    kind: str = SIMPLE
    seats: list[SeatSpec] = field(default_factory=list)
    turns_per_player: int = 2  # 남은 발언 차례 at the start of a discussion, per living player
    extend_step: int = 2  # turns added or removed by 연장 / 단축
    vote_public: bool = False  # 투표 공개: 익명 shows counts only
    moderator: str = "auto"  # auto | human
    reveal_roles: bool | None = None  # None: on in 단순, off in 복잡
    role_pool: str = "classic"  # 랜덤's pool: classic | full
    cult: bool = False  # 교주팀: in 랜덤 at 9 players or more 교주 takes a 특수 seat, at 12 광신도 one more
    role_mode: str = "random"  # 직업 구성: random | named (정해진 구성) | custom (직접)
    enabled_roles: list[str] = field(default_factory=list)  # 직접: the roles a slot may draw
    slots: list[int] = field(default_factory=list)  # older 직접: seats per kind (마피아, 보조, 경찰 계열, 의사, 특수, 시민)
    counts: dict[str, int] = field(default_factory=dict)  # 직접: seats per role, 시민 fill the rest
    named: bool = True  # 기본 (True) or 블라인드
    blind_scope: str = "ai"  # ai: AI끼리만, me: 나에게도
    language: str = "ko"
    delay: float = 0.0  # seconds between public lines
    god_powers: bool = True  # 관전 with 신의 권능
    cheats: bool = False  # 참가 with 치트
    max_nights: int = 10  # after this night the mafia team wins
    seed: int | None = None
    expert: bool = False  # 전문가 모드 for every seat unless a seat says otherwise
    compact_at: int = 256_000  # prompt tokens at which a player's oldest history is compacted
    call_timeout: float = 90.0  # seconds per call; after that the safe default applies

    @property
    def reveal(self) -> bool:
        return self.reveal_roles if self.reveal_roles is not None else self.kind == SIMPLE

    def problem(self) -> str | None:
        n = len(self.seats)
        lo, hi = PLAYER_RANGE[self.kind]
        if not lo <= n <= hi:
            return _("This game takes {lo} to {hi} players").format(lo=lo, hi=hi)
        if sum(1 for s in self.seats if s.kind == "human") > 1:
            return _("Only one seat can be a person")
        if any(s.kind == "ai" and not s.model_key and not s.pool for s in self.seats):
            return _("A seat has no model")
        fixed = [s.role for s in self.seats if s.role]
        if any(r not in GAME_ROLES[self.kind] or not playable(r) for r in fixed):
            return _("A seat has a role this game does not have")
        if by_counts(self):
            return count_problem_text(counts_problem(self, playable))
        if self.kind == SIMPLE:
            from .roles import simple_lineup
            lineup = simple_lineup(n)
            for r in set(fixed):
                if fixed.count(r) > lineup.get(r, 0):
                    return _("More {role} seats than this game has ({n})").format(role=_(EN.get(r, r)), n=lineup.get(r, 0))
        else:
            mafia = sum(1 for r in fixed if ROLES[r].team == MAFIA)
            if mafia * 2 >= n:
                return _("Too many mafia team seats")
            off = named_problem(self)
            if off:
                return _("The set lineup has no more {role} seats").format(role=_(EN.get(off, off)))
            if mode_of(self) == CUSTOM and self.slots and (sum(self.slots) != n or self.slots[0] * 2 >= n or self.slots[0] < 1):
                return _("The role counts do not add up to the players") if sum(self.slots) != n else _("Too many mafia team seats")
        return None

    @property
    def human_seat(self) -> int | None:
        for i, s in enumerate(self.seats):
            if s.kind == "human":
                return i
        return None

    @property
    def owner_sees_models(self) -> bool:
        """The user's screen shows models during play unless the game is blind to the user too."""
        return self.named or self.blind_scope == "ai"

    @property
    def god_view(self) -> bool:
        return self.human_seat is None or self.cheats

    @property
    def powers(self) -> bool:
        return self.god_powers if self.human_seat is None else self.cheats

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    def again(self) -> "GameSetup":
        """같은 설정으로 다시: the same table, with 랜덤 seats drawn again, 랜덤 effort drawn again and a new seed."""
        new = GameSetup.from_json(self.to_json())
        new.seed = None
        for s in new.seats:
            if s.kind == "ai" and s.pool:
                s.model_key = s.model_name = s.maker = s.country = None
                s.variant = None  # the drawn model's level may not exist on the next draw
            elif s.variant_random:
                s.variant = None
        return new

    @staticmethod
    def from_json(d: dict[str, Any]) -> "GameSetup":
        d = dict(d)
        d = canon_tree(d)  # saved before: old role names
        d["seats"] = [SeatSpec(**s) for s in d.get("seats", [])]
        known = GameSetup.__dataclass_fields__
        return GameSetup(**{k: v for k, v in d.items() if k in known})


def short_model_name(name: str) -> str:
    """'DeepSeek V4.1 Flash 1017' → 'DeepSeek V4.1 Flash', 'Hy4 flash Free' → 'Hy4 flash'."""
    words = [w for w in name.replace("Meta: ", "").split() if w.lower() != "free" and not (w.isdigit() and len(w) == 4)]
    return " ".join(words) or name


def key_name(key: str | None) -> str:
    """A readable name from a model key when no catalog name is known:
    'opencode:opencode-go/deepseek-v4.1-flash#low' → 'DeepSeek V4.1 Flash'."""
    if not key:
        return ""
    ident = key.split("#")[0].split(":", 1)[-1].rsplit("/", 1)[-1].split(":")[0]  # 'gpt-oss:free' → 'gpt-oss'
    parts: list[str] = []
    for w in re.split(r"[-_\s]+", ident):
        if not w or (w.isdigit() and len(w) >= 6):  # a date stamp
            continue
        if w.isdigit() and len(w) <= 2 and parts and re.fullmatch(r"\d+(\.\d+)*", parts[-1]):
            parts[-1] += "." + w  # 'haiku-5-5' → 'Haiku 5.5'
        else:
            parts.append(w)
    known = dict(LINES)  # 'deepseek' → 'DeepSeek', so a key reads the way the maker writes it
    return " ".join(known.get(w.lower(), w[:1].upper() + w[1:]) for w in parts)


def display_name(model_name: str | None, key: str | None) -> str:
    return short_model_name(model_name) if model_name else key_name(key)


def count_problem_text(key: str | None) -> str | None:
    """The start button's words for a 직접 lineup that cannot be played."""
    return {"unknown": _("A role in the lineup is not in this game"),
            "too_many": _("More roles than players"),
            "pairs": _("Lovers come in pairs"),
            "no_mafia": _("No one is on the mafia team"),
            "no_town": _("No one is outside the mafia team")}.get(key or "")


def playable(role: str) -> bool:
    """The role's ability is built (builds the classic pool first; the rest of the full pool waits)."""
    return ROLES[role].ability in REGISTRY


def seat_players(setup: GameSetup, rng: random.Random, judge: Judge | None = None) -> list[Player]:
    """Deal roles, give names and identities. One call name per seat: the model line's short name in 실명,
    a random given name in 블라인드; the full model name stays on the identity for the screen's second line."""
    fixed = [s.role for s in setup.seats if s.role]
    free = lineup(setup, rng, playable, judge)
    for r in fixed:
        free.remove(r)
    rng.shuffle(free)
    roles = [spec.role or free.pop() for spec in setup.seats]
    pool = list(EN_NAMES if setup.language == "en" else KO_NAMES)
    rng.shuffle(pool)
    shown: list[Identity] = []
    full: list[str | None] = []
    fixed: dict[int, str] = {}
    for i, spec in enumerate(setup.seats):
        if spec.kind == "human" and not spec.disguise_key:  # 실명: Human or the name the person typed
            shown.append(Identity(None))
            full.append(None)
            fixed[i] = spec.human_name.strip() or "Human"
            continue
        if spec.kind == "human":
            model = display_name(spec.disguise_name, spec.disguise_key)
            maker, country = spec.disguise_maker, spec.disguise_country
        else:
            model = display_name(spec.model_name, spec.model_key)
            maker, country = spec.maker, spec.country
        shown.append(Identity(model or None, maker, country))
        full.append(model or None)
    names = call_names(full, fixed) if setup.named else [pool.pop() for _ in setup.seats]
    players = [Player(seat=i, name=names[i], role=roles[i], kind=spec.kind, model_key=spec.model_key,
                      model_name=spec.model_name, shown=shown[i], start_role=roles[i])
               for i, spec in enumerate(setup.seats)]
    for p in players:
        p.ledger = {q.name: LedgerRow() for q in players if q is not p}
    return players


def default_setup(kind: str = SIMPLE) -> GameSetup:
    return GameSetup(kind=kind, seats=[SeatSpec() for _ in range(DEFAULT_PLAYERS[kind])])


__all__ = ["GameSetup", "SeatSpec", "seat_players", "default_setup", "short_model_name", "key_name", "display_name", "COMPLEX", "SIMPLE"]
