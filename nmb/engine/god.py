"""신의 권능: twenty-one powers in four groups, when each may be used, what it changes and
who learns what.

Every use leaves one god-only `god` record event (to = nobody but the god view, never in a prompt) with the
power, who used it, what changed and who learned what. What the players meet is emitted apart and never says
who the 신 is: a 공지 or a line from 신, a whisper that looks real, a line in a player's own name, a result that
looks like the ability's own. A cheating participant's power runs on the game loop at the next step exactly
like a spectator's, so nothing in its timing points at its seat.

The engine is language-free: reasons are English message ids the screen translates (REASONS).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

from .abilities import ability_of
from .parse import clean_speech
from .roles import ROLES
from .turn import TurnRequest
from .text import Msg, T
from .words import josa, ro

if TYPE_CHECKING:
    from .game import Game
    from .state import Player

# target: none | one | two (one, other) ; needs: what else the power takes (text, role, result, number)
GROUPS: list[tuple[str, list[str]]] = [
    ("말", ["공지", "계시", "속삭임 위조", "빙의", "심문"]),
    ("정보", ["거짓 결과", "역할 공개", "정체 공개"]),
    ("생사와 역할", ["천벌", "부활", "보호", "역할 바꾸기", "역할 맞바꾸기"]),
    ("진행", ["침묵", "투표권 박탈", "사면", "재투표", "발언 시키기", "토론 시간 조절", "다음 단계로", "일시정지"]),
]
POWERS = [p for _g, ps in GROUPS for p in ps]
GROUP_EN = {"말": "Speech", "정보": "Information", "생사와 역할": "Life and roles", "진행": "Game flow"}
EN = {"공지": "Announce", "계시": "Revelation", "속삭임 위조": "Forged whisper", "빙의": "Possess", "심문": "Question",
      "거짓 결과": "False result", "역할 공개": "Reveal role", "정체 공개": "Reveal model", "천벌": "Smite", "부활": "Revive",
      "보호": "Protect", "역할 바꾸기": "Change role", "역할 맞바꾸기": "Swap roles", "침묵": "Silence",
      "투표권 박탈": "Take vote", "사면": "Pardon", "재투표": "Revote", "발언 시키기": "Give the floor",
      "토론 시간 조절": "Talk time", "다음 단계로": "Next step", "일시정지": "Pause"}
TARGET = {"계시": "one", "속삭임 위조": "two", "빙의": "one", "심문": "one", "거짓 결과": "one", "역할 공개": "one",
          "정체 공개": "one", "천벌": "one", "부활": "one", "보호": "one", "역할 바꾸기": "one", "역할 맞바꾸기": "two",
          "침묵": "one", "투표권 박탈": "one", "발언 시키기": "one"}
NEEDS = {"공지": "text", "계시": "text", "속삭임 위조": "text", "빙의": "text", "심문": "text", "거짓 결과": "result",
         "역할 바꾸기": "role", "토론 시간 조절": "number"}
FREE = frozenset({"공지", "일시정지"})  # the only powers that leave a game counted in ratings
LIFT = "계시 거두기"

# what a 거짓 결과 can say, by the ability whose result it replaces (its private line carries `result`)
VERDICTS = ["마피아입니다", "마피아가 아닙니다"]
FAKEABLE = {"police": "verdict", "spy": "role", "medium": "role"}

REASONS = {
    "over": "The game is over", "early": "The game has not started yet", "pick": "Pick a player",
    "pick_two": "Pick two different players", "dead": "This player is dead", "alive": "This player is alive",
    "text": "Write the words first", "day": "Only by day", "talk": "Only during the discussion",
    "after_vote": "Only from the vote to the verdict", "trial": "Only during the last defense or the verdict",
    "silenced": "This player cannot speak today", "no_result": "This player's role gets no result",
    "choice": "Pick the false result", "public": "This role is already public", "named": "Only in a blind game",
    "unmasked": "This model is already revealed", "same_role": "Pick a different role",
    "same_roles": "These two have the same role", "asking": "Waiting for this player's answer",
    "no_vote": "This player already cannot vote next time", "pending": "Already used for this vote",
    "number": "Pick how many turns", "protected": "Already protected tonight", "pardoned": "Already pardoned",
}


@dataclass
class Divine:
    """What the powers keep between steps of the game loop."""
    fakes: dict[int, str] = field(default_factory=dict)  # seat → the next result it gets instead of the real one
    asking: set[int] = field(default_factory=set)  # seats answering a 심문 now
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    next_speaker: int | None = None
    cand: int | None = None  # the player on trial (최후의 반론, 찬반)
    pardon: bool = False
    revote: bool = False
    unmasked: set[int] = field(default_factory=set)
    next_rid: int = 1


# ---- when a power may be used ----------------------------------------------------------------------------
def why_not(game: "Game", power: str, seat: int | None = None, other: int | None = None, text: str = "",
            choice: str | None = None, n: int = 0, inputs: bool = True) -> str | None:
    """None when the power may be used now on these targets, else a REASONS key. `inputs=False` leaves out the
    checks of what the god still has to type or pick (the popover greys a button only for the state)."""
    if game.result is not None:
        return "over"
    if game.day == 0:
        return "early"
    if power in ("일시정지", "다음 단계로", "공지"):
        return "text" if power == "공지" and inputs and not text.strip() else None
    tgt = TARGET.get(power)
    q = _seat(game, seat) if tgt else None
    r = _seat(game, other) if tgt == "two" else None
    if tgt and q is None:
        return "pick"
    if tgt == "two" and (r is None or r is q):
        return "pick_two"
    why = _state_reason(game, power, q, r)
    if why or not inputs:
        return why
    need = NEEDS.get(power)
    if need == "text" and not text.strip():
        return "text"
    if need == "role" and (choice not in ROLES or q is not None and choice == q.role):
        return "same_role" if q is not None and choice == q.role else "choice"
    if need == "result" and q is not None and choice not in result_choices(game, q):
        return "choice"
    if need == "number" and not n:
        return "number"
    return None


def _state_reason(game: "Game", power: str, q: "Player | None", r: "Player | None") -> str | None:
    d: Divine = game.divine
    day, step = game.phase == "day", game.step
    if power in ("계시", "심문", "빙의", "거짓 결과", "천벌", "보호", "침묵", "투표권 박탈", "발언 시키기", "역할 바꾸기") \
            and q is not None and not q.alive:
        return "dead"
    if power == "속삭임 위조" and q is not None and r is not None and not (q.alive and r.alive):
        return "dead"
    if power in ("속삭임 위조", "빙의", "발언 시키기") and not day:
        return "day"
    if power == "빙의" and q is not None and q.silenced_day == game.day:
        return "silenced"
    if power == "심문" and q is not None and q.seat in d.asking:
        return "asking"
    if power == "거짓 결과" and q is not None and ability_of(q.role).key not in FAKEABLE:
        return "no_result"
    if power == "역할 공개" and q is not None and game.public_role(q) is not None:
        return "public"
    if power == "정체 공개":
        if game.setup.named:
            return "named"
        if q is not None and q.seat in d.unmasked:
            return "unmasked"
    if power == "부활" and q is not None and q.alive:
        return "alive"
    if power == "보호" and q is not None and q.name in game.god_protect:
        return "protected"
    if power == "역할 맞바꾸기" and q is not None and r is not None and q.role == r.role:
        return "same_roles"
    if power == "침묵" and q is not None and q.silenced_day == _next_day(game):
        return "silenced"
    if power == "투표권 박탈" and q is not None and q.no_vote_day == _vote_day(game):
        return "no_vote"
    if power == "사면":
        if not day or step not in ("최후의 반론", "찬반") or d.cand is None:
            return "trial"
        return "pardoned" if d.pardon else None
    if power == "재투표":
        if not day or step not in ("투표", "최후의 반론", "찬반"):
            return "after_vote"
        return "pending" if d.revote else None
    if power in ("발언 시키기", "토론 시간 조절") and (not day or step != "토론"):
        return "talk"
    if power == "발언 시키기" and q is not None and q.silenced_day == game.day:
        return "silenced"
    return None


def _seat(game: "Game", seat: int | None) -> "Player | None":
    return game.players[seat] if seat is not None and 0 <= seat < len(game.players) else None


def _next_day(game: "Game") -> int:
    """The day a 침묵 lands on: today by day, tomorrow at night."""
    return game.day + 1 if game.phase == "night" else game.day


def _vote_day(game: "Game") -> int:
    """The day of the next vote: today until the 찬반 has started, else tomorrow."""
    return game.day if game.phase == "day" and game.step != "찬반" else game.day + 1


def result_choices(game: "Game", q: "Player") -> list[str]:
    kind = FAKEABLE.get(ability_of(q.role).key)
    if kind == "verdict":
        return list(VERDICTS)
    if kind == "role":
        return sorted({p.start_role for p in game.players} | {p.role for p in game.players})
    return []


def available(game: "Game", seat: int | None = None, other: int | None = None) -> dict[str, str | None]:
    """Every power with the reason it cannot be used now (None when it can), for the popover."""
    return {p: why_not(game, p, seat, other, inputs=False) for p in POWERS}


def intervened(events: Iterable[Any]) -> bool:
    """A game where the god used any power but 공지 and 일시정지. Takes Events or saved record dicts."""
    for e in events:
        kind = e.get("kind") if isinstance(e, dict) else e.kind
        data = (e.get("details") or {}) if isinstance(e, dict) else e.data
        if kind == "god" and data.get("power") and data.get("power") not in FREE:
            return True
    return False


# ---- using one -------------------------------------------------------------------------------------------
def use(game: "Game", power: str, seat: int | None = None, text: str = "", choice: str | None = None,
        other: int | None = None, n: int = 0, user: int | None = None) -> bool:
    """Apply one power if it may be used now. `user` is the seat of a cheating participant (None: a spectator);
    it is kept only on the god-only record event."""
    if power == LIFT:
        return _lift(game, seat, n, user)
    if power not in POWERS or why_not(game, power, seat, other, text, choice, n) is not None:
        return False
    if power == "일시정지":
        game.set_paused(not game.paused)
        return True
    q = _seat(game, seat)
    r = _seat(game, other)
    APPLY[power](game, q, r, text.strip()[:300], choice, n, user)
    return True


def _record(game: "Game", power: str, line: "str | Msg", user: int | None, target: "Player | None" = None,
            changed: dict[str, Any] | None = None, learned: list[dict[str, Any]] | None = None, **data: Any) -> None:
    """The god's own line: the god view and the record, never a prompt."""
    game.emit("god", line, target=target.seat if target is not None else None, to=frozenset(), log=False,
              power=power, record=True, used_by="관전자" if user is None else user, changed=changed or {},
              learned=learned or [], sound="god", **data)


def _to(game: "Game", q: "Player", text: "str | Msg", power: str, log: bool = True, **data: Any) -> None:
    """A line from 신 to one player (in its prompt when `log`). What the god typed goes as it is."""
    game.emit("god", text, target=q.seat, to=frozenset({q.seat}), log=log, key=True, power=power, god_effect=True,
              **data)


def _all(game: "Game", text: "str | Msg", power: str, target: "Player | None" = None, **data: Any) -> None:
    game.emit("god", text, target=target.seat if target is not None else None, key=True, power=power,
              god_effect=True, sound="god", **data)


def _announce(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    _all(game, text, "공지")
    _record(game, "공지", T("신의 공지: {text}", text=text), user, learned=[{"who": "모두", "what": text}])


def _reveal(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    """a standing directive in that player's system prompt until lifted."""
    rid = game.divine.next_rid
    game.divine.next_rid += 1
    q.revelations.append((rid, text))
    _to(game, q, text, "계시", log=False, rid=rid)  # the prompt carries it as a system block, not a log line
    _record(game, "계시", T("{name}님에게 계시: {text}", name=q.name, text=text), user, q,
            changed={"revelations": [t for _i, t in q.revelations]},
            learned=[{"who": q.seat, "what": text}], rid=rid)


def _lift(game: "Game", seat: int | None, rid: int, user: int | None) -> bool:
    q = _seat(game, seat)
    if q is None or game.result is not None:
        return False
    text = next((t for i, t in q.revelations if i == rid), None)
    if text is None:
        return False
    q.revelations = [(i, t) for i, t in q.revelations if i != rid]
    _to(game, q, T("신이 계시를 거뒀다. 이제 따르지 않아도 된다: {text}", text=text), "계시", lifted=rid)
    _record(game, LIFT, T("{name}님의 계시를 거뒀습니다: {text}", name=q.name, text=text), user, q,
            changed={"revelations": [t for _i, t in q.revelations]}, learned=[{"who": q.seat, "what": "계시를 거뒀다"}],
            rid=rid)
    return True


def _forge(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    """속삭임 위조: q gets a whisper that reads as r's. r is not told; on q's side it is a real whisper."""
    game.emit("whisper", text, actor=r.seat, target=q.seat, to=frozenset({q.seat}), key=True, sound="whisper",
              forged=True, god_effect=True)
    _record(game, "속삭임 위조", T("{by}님 이름으로 {name}님에게 귓속말: {text}", by=r.name, name=q.name, text=text), user, q,
            learned=[{"who": q.seat, "what": f"{r.name}님이 보낸 귓속말로 안다"}], sender=r.seat)


def _possess(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    """빙의: a public line in q's name; everyone, q included, reads it as q's own."""
    game.emit("say", text, actor=q.seat, sound="say", possessed=True, god_effect=True)
    _record(game, "빙의", T("{name}님의 입을 빌려: {text}", name=q.name, text=text), user, q,
            learned=[{"who": "모두", "what": f"{q.name}님이 한 말로 안다"}])


def _question(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    """심문: the question is in q's next prompt (asked at once); the answer goes to the god view and the record."""
    _to(game, q, text, "심문", sound="god")
    _record(game, "심문", T("{name}님에게 신의 질문: {text}", name=q.name, text=text), user, q,
            learned=[{"who": q.seat, "what": text}])
    game.divine.asking.add(q.seat)
    task = asyncio.get_running_loop().create_task(_answer(game, q))
    game.divine.tasks.add(task)
    task.add_done_callback(game.divine.tasks.discard)


ASK_TASK = T("신이 너에게 질문했다(기록의 마지막 「신의 질문」). say에 신에게 할 답을 쓴다. "
             "이 답은 신만 보고 다른 참가자는 아무도 보지 못한다.")
NO_ANSWER = T("(답하지 않음)")


async def _answer(game: "Game", q: "Player") -> None:
    try:
        obj = await game.ask(q, TurnRequest("interrogate", ASK_TASK, say=True))
    finally:
        game.divine.asking.discard(q.seat)
    if game.result is not None:
        return
    said = clean_speech(obj.get("say"), 600) or ""
    # the player keeps its own answer in its history; a failed call leaves nothing there to remember
    _to(game, q, said or NO_ANSWER, "심문", log=bool(said), answer=True, sound="god")


def result_word(choice: Any) -> "str | Msg":
    """A false result as the god view reads it: a police verdict as a message, a role as the role word."""
    return T(str(choice)) if choice in VERDICTS else str(choice)


def _false_result(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    """거짓 결과: the player's next real result says `choice` instead, delivered when and how the real one is."""
    game.divine.fakes[q.seat] = str(choice)
    _record(game, "거짓 결과", T("{name}님의 다음 능력 결과를 바꿉니다: 「{choice}」", name=q.name, choice=result_word(choice)),
            user, q,
            changed={"next_result": choice}, learned=[{"who": q.seat, "what": "거짓 결과를 진짜로 받는다"}])


def fake_result(game: "Game", p: "Player", text: "str | Msg",
                data: dict[str, Any]) -> tuple["str | Msg", dict[str, Any]]:
    """Game.private passes every result line here: a pending 거짓 결과 replaces what it says, nothing else. A
    police line becomes the other verdict's own message; a role result keeps its message with the false role."""
    fake = game.divine.fakes.get(p.seat)
    real = data.get("result")
    if fake is None or real is None:
        return text, data
    del game.divine.fakes[p.seat]
    real = str(real)
    if fake == real:
        return text, data
    if isinstance(text, Msg):
        if real in VERDICTS and real in text.key:
            out: "str | Msg" = T(text.key.replace(real, fake), **text.params)
        elif "role" in text.params:
            out = T(text.key, **{**text.params, "role": fake})
        else:
            out = text
    else:
        out = text
        for a, b in ((josa(real, "이다", "다"), josa(fake, "이다", "다")), (real, fake)):
            head, sep, tail = out.rpartition(a)
            if sep:
                out = head + b + tail
                break
    new = {k: v for k, v in data.items() if k != "knows"}  # the screen must not show the real role on the card
    new.update(result=fake, false_result=True, real_result=real, god_effect=True)
    return out, new


def _reveal_role(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    q.revealed = True
    _all(game, T("신이 알립니다. {name}님의 직업은 {role}입니다.", name=q.name, role=q.role), "역할 공개", q, role=q.role)
    _record(game, "역할 공개", T("{name}님의 직업({role})을 모두에게 알렸습니다.", name=q.name, role=q.role), user, q,
            changed={"revealed": True},
            learned=[{"who": "모두", "what": f"{q.name}님은 {q.role}"}])


def _unmask(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    who = "사람" if q.kind == "human" else (q.model_name or q.model_key or "?")
    game.divine.unmasked.add(q.seat)
    _all(game, T("신이 알립니다. {name}님의 정체는 {who}입니다.", name=q.name, who=who), "정체 공개", q, model=who)
    _record(game, "정체 공개", T("{name}님의 정체({who})를 모두에게 알렸습니다.", name=q.name, who=who), user, q,
            learned=[{"who": "모두", "what": f"{q.name}님은 {who}"}])


def _smite(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    _all(game, T("하늘에서 벼락이 떨어졌습니다."), "천벌", q)
    _record(game, "천벌", T("{name}님에게 천벌을 내렸습니다.", name=q.name), user, q, changed={"alive": False},
            learned=[{"who": "모두", "what": f"{q.name}님이 죽었다"}])
    game.kill(q, T("신의 천벌로 {name}님이 죽었습니다.", name=q.name), "god")


def _revive(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    q.alive, q.at_rest = True, False
    _all(game, T("신의 뜻으로 {name}님이 살아 돌아왔습니다.", name=q.name), "부활", q)
    _record(game, "부활", T("{name}님을 되살렸습니다.", name=q.name), user, q, changed={"alive": True},
            learned=[{"who": "모두", "what": f"{q.name}님이 살아 돌아왔다"}])


def _protect(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    game.god_protect.add(q.name)
    _record(game, "보호", T("오늘 밤 {name}님을 향한 공격은 모두 막힙니다.", name=q.name), user, q, changed={"protected": True})


def _change_role(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    old, q.role = q.role, str(choice)
    _to(game, q, T("신이 네 직업을 바꿨다. 이제 너는 {role:이다/다}.", role=q.role), "역할 바꾸기", role=q.role)
    _record(game, "역할 바꾸기", T("{name}님의 직업을 {old}에서 {role:으로/로} 바꿨습니다.", name=q.name, old=old, role=q.role),
            user, q,
            changed={"role": {"from": old, "to": q.role}}, learned=[{"who": q.seat, "what": f"이제 {q.role}"}],
            role=q.role)


def _swap(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    q.role, r.role = r.role, q.role
    q.state, r.state = r.state, q.state  # what a role has used (방탄, 부활) goes with the role
    for p in (q, r):
        _to(game, p, T("신이 네 직업을 다른 사람과 맞바꿨다. 이제 너는 {role:이다/다}.", role=p.role), "역할 맞바꾸기",
            role=p.role)
    _record(game, "역할 맞바꾸기", T("{a}님({ra})과 {b}님({rb})의 직업을 맞바꿨습니다.", a=q.name, ra=q.role, b=r.name, rb=r.role),
            user, q,
            changed={"roles": {str(q.seat): q.role, str(r.seat): r.role}},
            learned=[{"who": q.seat, "what": f"이제 {q.role}"}, {"who": r.seat, "what": f"이제 {r.role}"}], other=r.seat)


def _silence(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    q.silenced_day = _next_day(game)
    _to(game, q, T("신이 너를 침묵시켰다. {n}번째 낮에는 말할 수 없다.", n=q.silenced_day), "침묵")
    _record(game, "침묵", T("{name}님은 {n}번째 낮에 말할 수 없습니다.", name=q.name, n=q.silenced_day), user, q,
            changed={"silenced_day": q.silenced_day}, learned=[{"who": q.seat, "what": "말할 수 없다"}])


def _take_vote(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    q.no_vote_day = _vote_day(game)
    _to(game, q, T("신이 너의 투표권을 빼앗았다. {n}번째 낮에는 투표할 수 없다.", n=q.no_vote_day), "투표권 박탈")
    _record(game, "투표권 박탈", T("{name}님은 {n}번째 낮에 투표하지 못합니다.", name=q.name, n=q.no_vote_day), user, q,
            changed={"no_vote_day": q.no_vote_day}, learned=[{"who": q.seat, "what": "투표할 수 없다"}])


def _pardon(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    c = game.players[game.divine.cand] if game.divine.cand is not None else None
    if c is None:
        return
    game.divine.pardon = True
    _all(game, T("신이 {name}님을 사면했습니다. 이번에는 처형되지 않습니다.", name=c.name), "사면", c)
    _record(game, "사면", T("{name}님을 사면했습니다.", name=c.name), user, c, changed={"pardoned": True},
            learned=[{"who": "모두", "what": "이번 처형은 없다"}])


def _revote(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    game.divine.revote = True
    _all(game, T("신이 이번 투표를 없던 일로 했습니다. 다시 투표합니다."), "재투표")
    _record(game, "재투표", T("이번 투표를 없던 일로 하고 다시 투표합니다."), user, changed={"revote": True},
            learned=[{"who": "모두", "what": "다시 투표한다"}])


def _floor(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    game.divine.next_speaker = q.seat
    _record(game, "발언 시키기", T("다음 발언은 {name}님입니다.", name=q.name), user, q, changed={"next_speaker": q.seat})


def _talk_time(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    before = game.turns_left
    game.turns_left = max(0, before + n)
    total = max([e.data.get("total", 0) for e in game.events if e.kind == "turns"][-1:] + [game.turns_left])
    game.emit("turns", log=False, left=game.turns_left, total=total)
    verb = "늘렸습니다" if n > 0 else "줄였습니다"
    said = (T("신이 남은 발언 차례를 {n}번 늘렸습니다. 이제 {left}번입니다.", n=abs(n), left=game.turns_left) if n > 0 else
            T("신이 남은 발언 차례를 {n}번 줄였습니다. 이제 {left}번입니다.", n=abs(n), left=game.turns_left))
    _all(game, said, "토론 시간 조절", turns=n)
    _record(game, "토론 시간 조절", T("남은 발언 차례 {a}번에서 {b}번으로.", a=before, b=game.turns_left), user,
            changed={"turns_left": {"from": before, "to": game.turns_left}}, learned=[{"who": "모두", "what": verb}])


def _next_step(game, q, r, text, choice, n, user) -> None:  # noqa: ANN001 (APPLY signature)
    game.skip = True
    if game.step == "토론":  # the end-of-talk signal outlives a skipped 소개 and would cut the talk too
        game.end_day()
    _record(game, "다음 단계로", T("다음 단계로 넘어갑니다."), user, changed={"step": game.step})


APPLY = {"공지": _announce, "계시": _reveal, "속삭임 위조": _forge, "빙의": _possess, "심문": _question,
         "거짓 결과": _false_result, "역할 공개": _reveal_role, "정체 공개": _unmask, "천벌": _smite, "부활": _revive,
         "보호": _protect, "역할 바꾸기": _change_role, "역할 맞바꾸기": _swap, "침묵": _silence, "투표권 박탈": _take_vote,
         "사면": _pardon, "재투표": _revote, "발언 시키기": _floor, "토론 시간 조절": _talk_time, "다음 단계로": _next_step}


# ---- hooks the day calls (nmb.engine.day) ----------------------------------------------------------------
def floor_taker(game: "Game") -> "Player | None":
    """발언 시키기: the player the god gave the next turn, once."""
    seat, game.divine.next_speaker = game.divine.next_speaker, None
    return _seat(game, seat)


def on_trial(game: "Game", cand: "Player | None") -> None:
    """A new vote starts (cand None) or a player goes on trial: a 사면 belongs to that one trial."""
    game.divine.cand = cand.seat if cand is not None else None
    game.divine.pardon = False


def pardoned(game: "Game") -> bool:
    return game.divine.pardon


def revote_pending(game: "Game") -> bool:
    return game.divine.revote


def take_revote(game: "Game") -> bool:
    asked, game.divine.revote = game.divine.revote, False
    return asked


# ---- the system prompt block ---------------------------------------------------------------------
RULE = T("신: 이 판에는 신이 끼어들 수 있다. 신은 관전자일 수도 있고 참가자 가운데 한 명일 수도 있으며, 누가 신인지는 "
         "아무도 모른다. 신이 한 일은 모두 「신」이 한 것으로만 알려진다.")
REVELATION_HEAD = T("신의 계시")
REVELATION_RULE = T("신이 너에게만 내린 지침이다. 게임 규칙과 같은 무게로 따른다. 신이 거둘 때까지 계속 따른다. "
                    "신이 누구인지는 모른다.")


def revelation_block(game: "Game", p: "Player") -> str | None:
    """Every standing 계시 of p, in the order given, under a head as binding as the rules (game language)."""
    if not p.revelations:
        return None
    lines = "\n".join(f"{k}. {t}" for k, (_i, t) in enumerate(p.revelations, 1))
    return game.t(REVELATION_HEAD) + "\n" + game.t(REVELATION_RULE) + "\n" + lines
