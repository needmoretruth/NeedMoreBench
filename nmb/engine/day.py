"""The days: the first day's 소개 → 토론 (no vote), and every later day after the morning: 토론 → 귓속말
시간 → 투표 → 최후의 반론 → 찬반.

The discussion runs on a shared budget of 남은 발언 차례 that everyone sees. The first pass gives everyone a
turn in random order; after that a player who was just named gets a reply first, then the highest `hand`.
After the first day it always ends into the vote, never straight into night.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import TYPE_CHECKING, Any

from .abilities import ability_for
from .parse import clean_speech, is_skip, match_name, read_whispers
from .state import Player
from .turn import TurnRequest

if TYPE_CHECKING:
    from .game import Game

EXTEND, SHORTEN = "연장", "단축"


async def first_day(game: "Game") -> None:
    """첫 낮: everyone introduces themselves once in seat order, then the usual discussion,
    then night 1 with no vote."""
    game.day, game.phase, game.step = 1, "day", ""
    game._end_day = asyncio.Event()
    game.emit("phase", "1번째 낮", key=True, phase="day", banner="1번째 낮", sound="day", first=True)
    await introductions(game)
    await discussion(game, vote_next=False)
    game.system("첫날은 투표 없이 밤이 됩니다.", key=False)


async def introductions(game: "Game") -> None:
    game.skip = False
    game.set_step("소개")
    game.system("소개 시간입니다. 자리 순서대로 한 사람씩 자기를 소개합니다.", key=False)
    task = "소개 차례다. 모두에게 너를 소개한다. 네 직업을 사실대로 말하든, 거짓으로 말하든, 말하지 않든 자유다."
    for p in game.alive():
        if game.skip:
            break
        if not can_speak(game, p):
            continue
        obj = await game.ask(p, TurnRequest("intro", task, say=True))
        say = clean_speech(obj.get("say"))
        if say:
            game.emit("say", say, actor=p.seat, sound="say", intro=True)
        else:
            game.system(f"{p.name}님은 소개하지 않았습니다.", key=False)
        await game.pace(bool(say))


async def run_day(game: "Game") -> None:
    await discussion(game)
    await whisper_time(game)
    cand = await vote(game)
    if cand is not None:
        extra = await defense(game, cand)
        await verdict(game, cand, extra)


def can_speak(game: "Game", p: Player) -> bool:
    return p.alive and p.silenced_day != game.day


def named_in(game: "Game", text: str, speaker: Player) -> list[Player]:
    """Living players the speaker names, in the order they appear."""
    hits: list[tuple[int, Player]] = []
    for q in game.alive():
        if q is speaker:
            continue
        keys = [q.name] + ([q.name.split()[0]] if " " in q.name and len(q.name.split()[0]) >= 3 else [])
        pos = min((i for i in (text.find(k) for k in keys) if i >= 0), default=-1)
        if pos >= 0:
            hits.append((pos, q))
    return [q for _, q in sorted(hits, key=lambda h: h[0])]


def _turns_event(game: "Game", total: int) -> None:
    game.emit("turns", log=False, left=game.turns_left, total=total)


def discuss_request(game: "Game", p: Player) -> TurnRequest:
    task = "토론 중이다. 네 차례다. 할 말이 없으면 say를 비워 침묵해도 된다."
    return TurnRequest("discuss", task, say=True, hand=True, time=p.seat not in game.time_used, poll=True)


async def discussion(game: "Game", vote_next: bool = True) -> None:
    s = game.setup
    game.skip = False
    game.set_step("토론", vote_next=vote_next)  # the screen's 투표로 button reads 밤으로 on the first day
    alive = game.alive()
    game.turns_left = total = s.turns_per_player * len(alive)
    game.time_used, game.poll = set(), {}
    _turns_event(game, total)
    game.system(f"토론을 시작합니다. 남은 발언 차례는 {game.turns_left}번입니다.", key=False)
    first = list(alive)
    game.rng.shuffle(first)
    hands: dict[int, int] = {p.seat: 1 for p in alive}
    spoke: Counter[int] = Counter()
    owed: list[Player] = []
    last: Player | None = None
    silent_run, warned, would_end = 0, False, False
    end = game._end_day or asyncio.Event()

    def choose() -> Player | None:
        while owed:
            q = owed.pop(0)
            if can_speak(game, q) and q is not last:
                if q in first:
                    first.remove(q)
                return q
        while first:
            q = first.pop(0)
            if can_speak(game, q):
                return q
        if silent_run >= len(game.alive()):
            return None
        cands = [q for q in game.alive() if can_speak(game, q) and q is not last and hands.get(q.seat, 0) > 0]
        if not cands:
            return None
        return max(cands, key=lambda q: hands[q.seat] * 10 - spoke[q.seat] * 3 + game.rng.random() * 4)

    while not end.is_set() and not game.skip:
        if game.turns_left <= 0 and s.moderator != "human":
            break
        p = choose()
        if p is None:
            if s.moderator != "human":
                break
            if not would_end:
                would_end = True
                game.emit("would_end", "자동 진행이라면 지금 토론이 끝납니다.", log=False)
            await end.wait()
            break
        if game.turns_left <= 0 and not would_end:
            would_end = True
            game.emit("would_end", "자동 진행이라면 지금 토론이 끝납니다.", log=False)
        obj = await game.ask(p, discuss_request(game, p))
        game.turns_left -= 1
        spoke[p.seat] += 1
        last = p
        say = clean_speech(obj.get("say"))
        if say:
            game.emit("say", say, actor=p.seat, sound="say")
            silent_run = 0
            for q in named_in(game, say, p)[:1]:
                if q not in owed:
                    owed.append(q)
        else:
            silent_run += 1
        ask_time(game, p, obj.get("time"))
        point(game, p, obj.get("poll"))
        hands[p.seat] = read_hand(obj.get("hand"), bool(say))
        _turns_event(game, total)
        if not warned and 0 < game.turns_left <= len(game.alive()):
            warned = True
            game.system("토론 시간이 얼마 남지 않았습니다.", key=False, sound="warn")
        await game.pace(bool(say))
    game.turns_left = max(0, game.turns_left)
    _turns_event(game, total)


async def whisper_time(game: "Game") -> None:
    """귓속말 시간: one whisper or a pass each, in random order, then one reply per sender."""
    game.skip = False
    game.set_step("귓속말 시간")
    game.system("귓속말 시간입니다.", key=False, sound="whisper")
    order = [p for p in game.alive() if can_speak(game, p)]
    game.rng.shuffle(order)
    got: dict[int, list[Player]] = {}
    for p in order:
        if game.skip or not p.alive:
            break
        others = [q.name for q in game.alive() if q is not p]
        req = TurnRequest("whisper", "귓속말 시간이다. 네 차례다. 살아 있는 사람 한 명을 골라 귓속말을 한 번 보내거나, "
                          "보내지 않으려면 whispers를 빈 목록으로 둔다.", whispers=1, whisper_to=others)
        obj = await game.ask(p, req)
        for q in whisper(game, p, obj.get("whispers"), 1, others):
            got.setdefault(q.seat, []).append(p)
        await game.pace(bool(obj.get("whispers")))
    replies = [game.players[s] for s in got]
    game.rng.shuffle(replies)
    for q in replies:
        if game.skip or not q.alive or not can_speak(game, q):
            continue
        senders = [s.name for s in got[q.seat] if s.alive]
        if not senders:
            continue
        req = TurnRequest("whisper_reply", f"귓속말 답장 차례다. 너에게 귓속말을 보낸 사람({', '.join(senders)})에게 "
                          "한 번씩 답할 수 있다. 이것이 오늘 마지막 귓속말이다. 답하지 않아도 된다.",
                          whispers=len(senders), whisper_to=senders)
        obj = await game.ask(q, req)
        whisper(game, q, obj.get("whispers"), len(senders), senders)
        await game.pace(bool(obj.get("whispers")))
    game.system("투표 시간입니다.", key=False, sound="vote")


def read_hand(v: Any, said: bool) -> int:
    try:
        return max(0, min(3, int(v)))
    except (TypeError, ValueError):
        return 1 if said else 0


def whisper(game: "Game", p: Player, raw: Any, limit: int, allowed: list[str]) -> list[Player]:
    """Emit the legal whispers (at most one per receiver) and return who got one."""
    out: list[Player] = []
    for to, text in read_whispers(raw, allowed, limit):
        q = game.by_name(to)
        if q is not None and q is not p and q not in out:
            out.append(q)
            game.emit("whisper", text, actor=p.seat, target=q.seat, to=frozenset({p.seat, q.seat}), key=True, sound="whisper")
    return out


def ask_time(game: "Game", p: Player, raw: Any) -> None:
    v = str(raw or "").strip()
    if p.seat in game.time_used or v not in (EXTEND, SHORTEN):
        return
    game.time_used.add(p.seat)
    step = game.setup.extend_step
    game.turns_left = game.turns_left + step if v == EXTEND else max(0, game.turns_left - step)
    verb = "늘렸습니다" if v == EXTEND else "줄였습니다"
    game.system(f"{p.name}님이 토론 시간을 {verb}.", key=False, time=v, actor_seat=p.seat)


def point(game: "Game", p: Player, raw: Any) -> None:
    if raw is None:
        return
    if is_skip(raw) or str(raw).strip() == "":
        changed = game.poll.pop(p.seat, None) is not None
    else:
        name = match_name(str(raw), [q.name for q in game.alive()])
        changed = name is not None and game.poll.get(p.seat) != name
        if name is not None:
            game.poll[p.seat] = name
    if changed:
        game.emit("poll", log=False, counts=game.poll_counts())


def _tally_text(counts: dict[str, int], voters: dict[str, list[str]] | None, skipped: list[str], public: bool) -> str:
    parts = []
    for name, n in counts.items():
        who = f"({', '.join(voters[name])})" if public and voters else ""
        parts.append(f"{name}님 {n}표{who}")
    if skipped:
        parts.append(f"기권 {len(skipped)}" + (f"({', '.join(skipped)})" if public else ""))
    return ", ".join(parts) if parts else "아무도 투표하지 않았습니다"


async def vote(game: "Game") -> Player | None:
    game.skip = False
    game.set_step("투표")
    alive = game.alive()
    voters = [p for p in alive if p.no_vote_day != game.day]
    for p in alive:
        if p.no_vote_day == game.day:
            game.private(p, "오늘은 투표할 수 없다.")
    opts = [q.name for q in alive]

    extras: dict[int, Any] = {}

    async def one(p: Player) -> tuple[Player, str | None]:
        req = TurnRequest("vote", "투표 시간이다. 최후의 반론에 올릴 사람 한 명에게 투표한다. 자기 자신에게도 투표할 수 있고 기권도 된다. "
                          "가장 많이 받은 사람이 최후의 반론을 하고, 그다음 찬반으로 처형을 정한다. 최다 득표가 동점이면 바로 밤이 된다.",
                          field="vote", options=opts, skip_word="기권")
        with_extra(req, ability_for(p).vote_extra(game, p))
        obj = await game.ask(p, req)
        if req.extra_field:
            extras[p.seat] = obj.get(req.extra_field)
        return p, game.pick(obj, req)

    picks = await asyncio.gather(*(one(p) for p in voters))
    await game.checkpoint()
    for p, t in picks:  # 마담's seduction, 도둑's theft: private, after everyone voted
        if p.alive:
            ability_for(p).after_vote(game, p, t, extras.get(p.seat))
    counts: Counter[str] = Counter()
    by: dict[str, list[str]] = {}
    skipped: list[str] = []
    for p, t in picks:
        if t is None:
            skipped.append(p.name)
            continue
        counts[t] += ability_for(p).vote_weight(p)
        by.setdefault(t, []).append(p.name)
    ordered = dict(counts.most_common())
    public = game.setup.vote_public
    text = "투표 결과: " + _tally_text(ordered, by, skipped, public)
    game.emit("vote_result", text, key=True, counts=ordered, voters=by, skipped=skipped,
              votes={p.seat: t for p, t in picks}, public=public, sound="reveal")
    if not ordered:
        game.system("아무도 투표하지 않아 밤이 됩니다.")
        return None
    top = max(ordered.values())
    leaders = [n for n, c in ordered.items() if c == top]
    if len(leaders) > 1:
        game.system("최다 득표가 동점이라 밤이 됩니다.")
        return None
    cand = game.by_name(leaders[0])
    if cand is None:
        return None
    game.system(f"{cand.name}님이 최다 득표로 최후의 반론을 합니다.", target=cand.seat)
    return cand


def with_extra(req: TurnRequest, extra: TurnRequest | None) -> None:
    """A role's second choice (도둑's theft, 테러리스트's target) rides on the same call."""
    if extra is not None and extra.extra_field:
        req.extra_field, req.extra_options, req.extra_task = extra.extra_field, extra.extra_options, extra.extra_task


async def defense(game: "Game", cand: Player) -> Any:
    """The last word; returns the answer to the candidate's defence extra (테러리스트: whom to take along)."""
    game.set_step("최후의 반론")
    req = TurnRequest("defense", "최후의 반론이다. 너는 최다 득표로 처형 직전이다. 이번에는 2~4문장까지 말해도 된다. "
                      "찬반에서 찬성이 반대보다 적으면 살아남는다.", say=can_speak(game, cand))
    with_extra(req, ability_for(cand).defense_extra(game, cand))
    if not can_speak(game, cand):
        game.system(f"{cand.name}님은 오늘 말할 수 없습니다.")
        if not req.extra_field:
            return None
        req.task = "최후의 반론이지만 너는 오늘 말할 수 없다. 처형될 때를 대비한 선택만 한다."
        return (await game.ask(cand, req)).get(req.extra_field)
    obj = await game.ask(cand, req)
    say = clean_speech(obj.get("say"), 600)
    if say:
        game.emit("say", say, actor=cand.seat, key=True, defense=True, sound="say")
    else:
        game.system(f"{cand.name}님은 아무 말도 하지 않았습니다.", key=False)
    await game.pace(bool(say))
    return obj.get(req.extra_field) if req.extra_field else None


async def verdict(game: "Game", cand: Player, extra: Any = None) -> None:
    game.set_step("찬반")
    voters = [p for p in game.alive() if p is not cand and p.no_vote_day != game.day]
    yes_no = ["찬성", "반대"]

    async def one(p: Player) -> tuple[Player, str | None]:
        req = TurnRequest("verdict", f"찬반 투표다. {cand.name}님을 처형할지 정한다. 찬성이 반대보다 많거나 같으면 처형된다. 기권은 반대로 센다.",
                          field="verdict", options=yes_no, skip_word="기권")
        return p, game.pick(await game.ask(p, req), req)

    picks = await asyncio.gather(*(one(p) for p in voters))
    await game.checkpoint()
    yes = sum(ability_for(p).vote_weight(p) for p, t in picks if t == "찬성")
    no = sum(ability_for(p).vote_weight(p) for p, t in picks if t != "찬성")
    public = game.setup.vote_public
    ayes = [p.name for p, t in picks if t == "찬성"]
    nays = [p.name for p, t in picks if t == "반대"]
    skips = [p.name for p, t in picks if t is None]
    text = f"찬반 결과: 찬성 {yes}, 반대 {no}"
    if public:
        text += f" (찬성: {', '.join(ayes) or '없음'} / 반대: {', '.join(nays + skips) or '없음'})"
    game.emit("verdict_result", text, key=True, yes=yes, no=no, ayes=ayes, nays=nays, skipped=skips,
              votes={p.seat: t for p, t in picks}, public=public, target=cand.seat, sound="reveal")
    passed = yes >= no and yes > 0
    for j in game.alive():  # 판사: the outcome follows its own pick
        turned = ability_for(j).override_verdict(game, j, dict((p.seat, t) for p, t in picks).get(j.seat), passed)
        if turned is not None:
            passed = turned
    if not passed:
        game.system(f"{cand.name}님은 처형되지 않았습니다.")
        return
    ab = ability_for(cand)
    if not ab.executable(game, cand):
        game.system(f"{cand.name}님은 투표로 처형되지 않습니다.")
        return
    if any(ability_for(q).spare(game, q, cand) for q in game.alive()):  # 사기꾼 survives once
        return
    game.kill(cand, f"{cand.name}님이 처형되었습니다.", "execution")
    ab.on_executed(game, cand, extra)
    shot = ab.last_shot(game, cand)  # 사냥꾼: after the 찬반, one living player goes along
    if shot is not None and shot.options:
        ab.take_shot(game, cand, game.pick(await game.ask(cand, shot), shot))
