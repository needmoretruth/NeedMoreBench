"""One night and the morning after it.

The night opens with the secret chats (연인, the dead with the 영매) while the mafia meets; then every living
player whose ability works at night answers at once, and the answers resolve in priority order: 10 blocks and
marks, 20 protections, 30 kills (then attacks resolve), 40 information, 50 revivals, 60 what others did.
The morning shows only what the source shows publicly; private results reach the player who earned them.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import TYPE_CHECKING

from .abilities import Attack, NightContext, ability_for, ability_of, in_mafia_team
from .abilities.base import announce, choose_text
from .parse import clean_speech
from .state import Player
from .text import Msg, T, lines
from .turn import TurnRequest

if TYPE_CHECKING:
    from .game import Game


async def run_night(game: "Game") -> None:
    """Night N follows day N (the game starts in the day); its morning opens day N+1."""
    game.phase, game.step = "night", ""
    game.emit("phase", T("{n}번째 밤", n=game.day), key=True, phase="night", banner=game.t(T("밤이 되었습니다")), sound="night")
    game.snapshot()
    ctx = NightContext(night=game.day)
    ctx.blocked |= game.blocked_next
    game.blocked_next = set()
    for p in game.players:
        if p.state.pop("frog", None):
            game.private(p, T("개구리에서 풀려났다. 다시 직업 능력을 쓸 수 있다."))
    for p in game.alive():
        ability_for(p).nightfall(game, p, ctx)

    async def abilities() -> list[tuple[Player, str | None]]:
        await asyncio.gather(lover_chat(game), dead_chat(game))
        jobs = []
        for p in game.alive():
            ab = ability_for(p)
            if ab.blockable and p.name in ctx.blocked:
                if ab.night_request(game, p) is not None:
                    game.private(p, T("유혹당해 오늘 밤 능력을 쓰지 못한다."))
                continue
            req = ab.night_request(game, p)
            if req is not None:
                jobs.append(one(p, req))
        return list(await asyncio.gather(*jobs))

    async def one(p: Player, req: TurnRequest) -> tuple[Player, str | None]:
        obj = await game.ask(p, req)
        ctx.answers[p.seat] = obj
        t = game.pick(obj, req)
        announce(game, p, choose_text(ability_for(p).acting(p), game, t), game.by_name(t))  #
        return p, t

    (target, picks), chosen = await asyncio.gather(mafia_meeting(game), abilities())
    await game.checkpoint()
    ctx.mafia_target = target
    for seat, t in picks.items():
        if t == target:
            ctx.used_on[seat] = t
    order = sorted(chosen, key=lambda pt: ability_for(pt[0]).priority_for(pt[0]))
    prio = {p.seat: ability_for(p).priority_for(p) for p, _t in order}
    for p, t in [a for a in order if prio[a[0].seat] < 30]:
        await night_act(game, p, t, ctx)
    if target:
        pierce = any(ability_for(q).pierce(game, q) for q in game.alive())
        executor = next((seat for seat, t in picks.items() if t == target), None)  # picks are in speaking order
        ctx.attacks.append(Attack("mafia", target, attacker=executor, pierce=pierce))
    for p, t in [a for a in order if prio[a[0].seat] == 30]:
        await night_act(game, p, t, ctx)
    resolve_attacks(game, ctx)
    for p, t in [a for a in order if prio[a[0].seat] > 30]:
        await night_act(game, p, t, ctx)
    for p in game.players:
        if not p.alive:
            ability_of(p.role).while_dead(game, p, ctx)
    game.god_protect.clear()
    morning(game, ctx)


async def night_act(game: "Game", p: Player, target: str | None, ctx: NightContext) -> None:
    ab = ability_for(p)
    if ab.blockable and p.name in ctx.blocked:
        game.private(p, T("유혹당해 오늘 밤 능력을 쓰지 못했다."))
        return
    await ab.act(game, p, target, ctx)
    if target and p.seat not in ctx.used_on and game.by_name(target) is not None:  # what a 미행꾼 sees (기록관 names a role)
        ctx.used_on[p.seat] = target


def resolve_attacks(game: "Game", ctx: NightContext) -> None:
    dead: set[str] = set()
    for a in ctx.attacks:
        q = game.by_name(a.target)
        if q is None or not q.alive or q.name in dead:
            continue
        if q.name in game.god_protect:
            game.observe("saved", T("신의 보호로 {name}님이 살았습니다.", name=q.name), target=q.seat, source=a.source)
            continue
        if a.source == "mafia" and q.name in ctx.protected and not a.pierce:
            ctx.morning.append(T("의사의 치료로 {name}님이 살아났습니다.", name=q.name))
            game.observe("saved", T("의사가 {name}님을 살렸습니다.", name=q.name), target=q.seat, source=a.source)
            continue
        outcome = "die" if a.pierce else ability_for(q).on_attack(game, q, a, ctx)
        if outcome == "die":
            dead.add(q.name)
            ctx.deaths.append((q.name, a.source))


def morning(game: "Game", ctx: NightContext) -> None:
    game.day += 1
    game.phase, game.step = "day", ""
    game._end_day = asyncio.Event()
    today = T("{n}번째 낮", n=game.day)
    game.emit("phase", today, key=True, phase="day", banner=game.t(today), sound="day")
    game.set_step("아침")
    for p, ab in [(p, ability_for(p)) for p in game.alive()]:  # a frog made tonight (마녀) still has its morning
        ab.morning(game, p, ctx)
    for line in ctx.morning:
        game.system(line, sound="save")
    for name, cause in ctx.deaths:
        q = game.by_name(name)
        if q and q.alive:
            game.kill(q, T("밤사이 {name}님이 죽었습니다.", name=q.name), cause, ctx)
    if not ctx.deaths and not ctx.morning:
        game.system(T("조용하게 밤이 지나갔습니다."))


async def mafia_meeting(game: "Game") -> tuple[str | None, dict[int, str | None]]:
    """(the night's kill or None, each killer's pick)."""
    members = [p for p in game.alive() if in_mafia_team(p)]
    killers = [p for p in members if ability_for(p).is_killer(game, p) or ability_of(p.role).kills]
    if not killers:
        return None, {}
    game.rng.shuffle(members)
    team = frozenset(p.seat for p in members) | frozenset(p.seat for p in game.players if not p.alive)
    opts = [q.name for q in game.alive()]  # a teammate or oneself too
    picks: dict[int, str] = {}
    game.meeting = team  # a person on the team may also type into the meeting
    game.emit("meeting", to=team, log=False, on=True)
    try:
        for rnd in range(1, MEETING_ROUNDS + 1):
            for p in members:
                if not p.alive:
                    continue
                killer = p in killers
                req = TurnRequest("mafia", meeting_task(rnd, killer, picks.get(p.seat)), say=True,
                                  **({"field": "target", "options": opts} if killer else {}))
                obj = await game.ask(p, req)
                pick = game.pick(obj, req) if killer else None
                if pick:
                    picks[p.seat] = pick  # no answer keeps the earlier pick
                say = clean_speech(obj.get("say"))
                game.emit("mafia", say, actor=p.seat, to=team, key=True, pick=picks.get(p.seat) if killer else None,
                          round=rnd, sound="mafia")
                await game.pace(bool(say))
            final = {picks.get(k.seat) for k in killers if k.alive}
            if len(members) == 1 or (None not in final and len(final) == 1):
                break  # everyone who kills agrees (a lone mafia states its pick once)
    finally:
        game.meeting = None
        game.emit("meeting", to=team, log=False, on=False)
    ordered = [(p, picks[p.seat]) for p in members if p.seat in picks]
    counts = Counter(t for _, t in ordered)
    if not counts:
        announce(game, killers[0], T("아무도 노리지 않았습니다"), to=team, role="마피아")
        return None, {}
    top = max(counts.values())
    tied = {t for t, c in counts.items() if c == top}
    who, choice = next((p, t) for p, t in ordered if t in tied)
    game.emit("mafia", T("오늘 밤 죽일 사람: {name}", name=choice), to=team, key=True, decided=choice)
    announce(game, who, T("{t}님을 노립니다", t=choice), game.by_name(choice), to=team, role="마피아")
    return choice, dict((p.seat, t) for p, t in ordered)


MEETING_ROUNDS, CHAT_ROUNDS = 3, 2


def meeting_task(rnd: int, killer: bool, mine: str | None) -> Msg:
    """The rules of the meeting as rules: rounds, agreement, the fallback."""
    parts = [T("마피아 회의다. 마피아 팀에게만 들린다. say는 마피아 팀에게만 하는 말이다.")]
    if rnd > 1:
        parts.append(T("회의 {n}번째 바퀴다. 위의 회의 내용을 보고 말한다.", n=rnd))
    if not killer:
        parts.append(T("죽일 사람은 마피아가 정한다."))
    else:
        if mine:
            parts.append(T("지금 네 선택: {name}. 바꾸거나 그대로 둔다.", name=mine))
        parts.append(T("오늘 밤 죽일 사람을 target에 적는다. 살아 있는 누구든 된다(같은 마피아 팀이나 너 자신도). "
                       "회의는 차례대로 최대 {n}바퀴 돈다. 한 바퀴가 끝났을 때 죽일 사람을 고르는 모두의 선택이 같으면 회의가 끝나고, "
                       "{n}바퀴가 지나도 갈리면 가장 많이 나온 사람, 같으면 먼저 말한 쪽의 선택으로 정해진다.", n=MEETING_ROUNDS))
    return lines(*parts)


async def lover_chat(game: "Game") -> None:
    """연인 night chat: while both live, each says one line to the other; the dead may read it."""
    pair = [p for p in game.alive() if p.role == "연인"]
    if len(pair) != 2:
        return
    game.rng.shuffle(pair)
    to = frozenset(p.seat for p in pair) | frozenset(p.seat for p in game.players if not p.alive)
    for rnd in range(1, CHAT_ROUNDS + 1):  # two rounds, so each can answer the other
        for p in pair:
            other = next(q for q in pair if q is not p)
            req = TurnRequest("lover", T("연인 대화다({rnd}/{n}번째 바퀴). 연인 {name}님과 너만 듣는다. "
                                         "하고 싶은 말이 없으면 say를 비운다.", rnd=rnd, n=CHAT_ROUNDS, name=other.name), say=True)
            say = clean_speech((await game.ask(p, req)).get("say"))
            if say:
                game.emit("lover", say, actor=p.seat, to=to, key=True, sound="whisper", round=rnd)
            await game.pace(bool(say))


async def dead_chat(game: "Game") -> None:
    """The dead's chat with the 영매: the 영매 speaks, then every dead player not laid to rest answers once.
    Without a living 영매 nobody alive would hear it, so it is not held."""
    medium = [p for p in game.alive() if p.role == "영매"]
    dead = [p for p in game.players if not p.alive and not p.at_rest]
    if not medium or not dead:
        return
    to = frozenset(p.seat for p in medium) | frozenset(p.seat for p in game.players if not p.alive)
    names = [p.name for p in dead]
    speakers = medium + dead
    for rnd in range(1, CHAT_ROUNDS + 1):
        for p in speakers:
            if p.alive:
                task = T("죽은 사람 대화다({rnd}/{n}번째 바퀴). 영매인 너와 죽은 사람들({names})만 듣는다. 하고 싶은 말이 없으면 say를 비운다.",
                         rnd=rnd, n=CHAT_ROUNDS, names=names)
            else:
                task = T("죽은 사람 대화다({rnd}/{n}번째 바퀴). 죽은 사람들과 영매만 듣는다. 산 사람에게는 들리지 않는다. "
                         "하고 싶은 말이 없으면 say를 비운다.", rnd=rnd, n=CHAT_ROUNDS)
            say = clean_speech((await game.ask(p, TurnRequest("dead", task, say=True))).get("say"))
            if say:
                game.emit("dead", say, actor=p.seat, to=to, key=True, sound="whisper", round=rnd)
            await game.pace(bool(say))
