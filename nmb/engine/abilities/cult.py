"""교주 팀, the 교주팀 setting: 교주 and 광신도.

A cult is known by its leader's seat (`state["cult"]`), so several 교주 each lead their own. A convert keeps its
role and ability and wins with its cult. The leader converts on odd nights (not the mafia team, the 부활술사 or
another cult's member), learns the convert's role, and may send its cult one line a night that they cannot
answer; each conversion rings a bell everyone hears. A 광신도 finds its 교주 by checking players and takes over
the converting when that 교주 dies.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..parse import clean_speech
from ..roles import CULT, MAFIA
from ..text import Msg, T, lines
from ..turn import TurnRequest
from .base import Ability, NightContext, register, side

if TYPE_CHECKING:
    from ..game import Game
    from ..state import Player

BELL = "종소리가 울렸습니다. 누군가 교주 팀이 되었습니다."


def cult_of(game: "Game", p: "Player") -> int | None:
    """The leader seat of p's cult; an unlinked 광신도 belongs to the only 교주 when there is one."""
    cid = p.state.get("cult")
    if cid is not None:
        return int(cid)
    if p.role == "광신도":
        leaders = [q.seat for q in game.players if q.role == "교주"]
        return leaders[0] if len(leaders) == 1 else None
    return None


def members(game: "Game", cid: int, alive: bool = True) -> list["Player"]:
    return [q for q in game.players if (q.alive or not alive) and side(q) == CULT and cult_of(game, q) == cid]


def cults(game: "Game") -> dict[int, list["Player"]]:
    """Each cult with players in the game: its living members."""
    out: dict[int, list["Player"]] = {}
    for q in game.players:
        cid = cult_of(game, q) if side(q) == CULT else None
        if cid is not None:
            out.setdefault(cid, [])
            if q.alive:
                out[cid].append(q)
    return out


def leads(game: "Game", p: "Player") -> bool:
    """p converts for its cult: the 교주, or the first living 광신도 of a cult whose 교주 is dead."""
    if p.role == "교주":
        return True
    cid = cult_of(game, p)
    if p.role != "광신도" or cid is None or game.players[cid].alive:
        return False
    heirs = [q for q in game.players if q.alive and q.role == "광신도" and cult_of(game, q) == cid]
    return bool(heirs) and heirs[0] is p


def convertible(game: "Game", q: "Player") -> bool:
    return q.alive and side(q) not in (MAFIA, CULT) and q.role != "부활술사"


class Leading(Ability):
    """What a converting leader asks and does at night."""
    act_text, pass_text = "{t}님을 포교합니다", "아무도 포교하지 않았습니다"
    priority = 50  # after the kills: a player who dies tonight is not converted

    def lead_request(self, game: "Game", p: "Player") -> TurnRequest | None:
        cid = cult_of(game, p)
        flock = [q.name for q in members(game, cid) if q is not p] if cid is not None else []
        opts = [q.name for q in game.alive() if q is not p and q.name not in flock]
        odd = game.day % 2 == 1
        if not odd and not flock:
            return None
        parts = [T("밤이다.")]
        if odd:
            parts.append(T("포교할 사람 한 명을 고른다. 마피아 팀, 부활술사, 이미 교주 팀인 사람은 포교되지 않는다."))
        else:
            parts.append(T("짝수 번째 밤이라 포교할 수 없다."))
        if flock:
            parts.append(T("say에 쓴 말은 교주 팀({names})에게 간다. 그들은 답하지 못한다. 없으면 빈 문자열.", names=flock))
        task = lines(*parts, sep=" ")
        if odd:
            return TurnRequest("night", task, field="target", options=opts, skip_word="없음", say=bool(flock))
        return TurnRequest("night", task, say=True)

    async def lead(self, game: "Game", p: "Player", target: str | None, ctx: NightContext) -> None:
        cid = cult_of(game, p)
        if cid is None:
            return
        said = clean_speech((ctx.answers.get(p.seat) or {}).get("say"))
        flock = [q for q in members(game, cid) if q is not p]
        if said and flock:
            to = frozenset({p.seat} | {q.seat for q in flock} | {q.seat for q in game.players if not q.alive})
            game.emit("cult", said, actor=p.seat, to=to, key=True, sound="whisper")
        q = game.by_name(target) if target and game.day % 2 == 1 else None
        if q is None:
            return
        ctx.used_on[p.seat] = q.name
        if not convertible(game, q) or ctx.dying(q.name):
            game.private(p, T("{name}님 포교에 실패했다.", name=q.name), target=q.seat)
            return
        q.state["cult"] = cid
        game.private(p, T("{name}님을 포교했다. {name}님의 직업은 {role:이다/다}.", name=q.name, role=q.role), target=q.seat,
                     result=q.role, knows=[q.seat])
        game.private(q, T("교주 {name}님에게 포교되어 교주 팀이 되었다. 이제 교주 팀이 이기면 너도 이긴다. 원래 직업 능력은 그대로 쓴다.",
                          name=p.name), target=p.seat, knows=[p.seat])
        game.know(p, q)
        game.know(q, p)
        game.observe("convert", T("{by}님이 {name}님을 포교했습니다.", by=p.name, name=q.name), actor=p.seat, target=q.seat)
        if not any(isinstance(m, Msg) and m.key == BELL for m in ctx.morning):
            ctx.morning.append(T(BELL))


@register
class CultLeader(Leading):
    key = "cult_leader"

    def on_start(self, game, p):
        p.state["cult"] = p.seat

    def night_request(self, game, p):
        return self.lead_request(game, p)

    async def act(self, game, p, target, ctx):
        await self.lead(game, p, target, ctx)


@register
class Fanatic(Leading):
    """Checks one player a night until it finds its 교주; when that 교주 dies it converts in its place."""
    key = "fanatic"
    act_text, pass_text = "{t}님을 확인합니다", "아무도 확인하지 않았습니다"
    priority = 40

    def acting(self, p):
        return LEADING if p.state.get("leading") else self

    def priority_for(self, p):
        return Leading.priority if p.state.get("leading") else self.priority

    def nightfall(self, game, p, ctx):
        if leads(game, p) and not p.state.get("leading"):
            p.state["leading"] = True
            game.private(p, T("교주가 죽어 포교를 이어받았다. 홀수 번째 밤마다 한 명을 포교한다."))

    def night_request(self, game, p):
        if p.state.get("leading"):
            return self.lead_request(game, p)
        if p.state.get("cult") is not None:
            return None
        return TurnRequest("night", T("밤이다. 한 명을 골라 교주인지 확인한다. 교주면 교주와 이어진다."), field="target",
                           options=[q.name for q in game.alive() if q is not p])

    async def act(self, game, p, target, ctx):
        if p.state.get("leading"):
            await self.lead(game, p, target, ctx)
            return
        q = game.by_name(target) if target else None
        if q is None:
            return
        if q.role != "교주":
            game.private(p, T("{name}님은 교주가 아니다.", name=q.name), target=q.seat)
            return
        p.state["cult"] = q.seat
        game.private(p, T("{name}님이 교주다. 교주와 이어졌다.", name=q.name), target=q.seat, result=q.role, knows=[q.seat])
        game.private(q, T("광신도 {name}님이 너를 찾아 이어졌다.", name=p.name), target=p.seat, knows=[p.seat])
        game.know(p, q)
        game.know(q, p)

    def status(self, p):
        if p.state.get("leading"):
            return T("교주를 이어받아 홀수 번째 밤마다 포교한다.")
        return None


LEADING = Leading()
