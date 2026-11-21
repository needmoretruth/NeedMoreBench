"""The days: the first day's 소개 → 토론 → 귓속말 시간 (no vote), and every later day after the morning: 토론 → 귓속말
시간 → 투표 → 최후의 반론 → 찬반.

The discussion runs on a shared budget of 남은 발언 차례 that everyone sees. The first pass gives everyone a
turn in random order; after that a player who was just named gets a reply first, then the highest `hand`.
After the first day it always ends into the vote, never straight into night.
"""
from __future__ import annotations

import asyncio
from collections import Counter
from typing import TYPE_CHECKING, Any

from . import god as divine
from .abilities import ability_for
from .parse import clean_speech, is_skip, match_name, read_whispers
from .state import Player
from .text import Msg, T, from_word
from .turn import TurnRequest

if TYPE_CHECKING:
    from .game import Game

EXTEND, SHORTEN = "연장", "단축"


async def first_day(game: "Game") -> None:
    """첫 낮: everyone introduces themselves once in seat order, then the usual discussion,
    then night 1 with no vote."""
    game.day, game.phase, game.step = 1, "day", ""
    game._end_day = asyncio.Event()
    day1 = T("{n}번째 낮", n=1)
    game.emit("phase", day1, key=True, phase="day", banner=game.t(day1), sound="day", first=True)
    await introductions(game)
    await discussion(game, vote_next=False)
    await whisper_time(game, vote_next=False)  # whispers from the first day
    game.system(T("첫날은 투표 없이 밤이 됩니다."), key=False)


async def introductions(game: "Game") -> None:
    game.skip = False
    game.set_step("소개")
    game.system(T("소개 시간입니다. 자리 순서대로 한 사람씩 자기를 소개합니다."), key=False)
    task = T("소개 차례다. 모두에게 너를 소개한다. 네 직업을 사실대로 말하든, 거짓으로 말하든, 말하지 않든 자유다.")
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
            game.system(T("{name}님은 소개하지 않았습니다.", name=p.name), key=False)
        await game.pace(bool(say))


async def run_day(game: "Game") -> None:
    await discussion(game)
    await whisper_time(game)
    while True:  # 재투표 throws the vote away and runs it again
        cand = await vote(game)
        if cand is not None and not divine.revote_pending(game):
            extra = await defense(game, cand)
            if not divine.revote_pending(game):
                await verdict(game, cand, extra)
        if not divine.take_revote(game):
            break


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


HUMAN_REPLY = 60.0  # seconds a person has for a discussion turn the engine gives them; then the turn passes


def discuss_request(game: "Game", p: Player, named_by: str = "") -> TurnRequest:
    task = T("토론 중이다. 네 차례다. 할 말이 없으면 say를 비워 침묵해도 된다.")
    req = TurnRequest("discuss", task, say=True, hand=True, time=time_open(game, p), poll=True)
    if p.kind == "human":
        req.limit, req.named_by = HUMAN_REPLY, named_by
    return req


async def _first_of(*events: asyncio.Event) -> None:
    waits = [asyncio.ensure_future(e.wait()) for e in events]
    try:
        await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for w in waits:
            w.cancel()


async def discussion(game: "Game", vote_next: bool = True) -> None:
    s = game.setup
    game.skip = False
    game.set_step("토론", vote_next=vote_next)  # the screen's 투표로 button reads 밤으로 on the first day
    alive = game.alive()
    per = s.turns_per_player if vote_next else 1  # the first day after the intros: one turn each
    game.turns_left = game.turns_total = total = per * len(alive)
    game.time_used, game.cut_votes, game.poll = set(), set(), {}
    _turns_event(game, total)
    game.system(T("토론을 시작합니다. 남은 발언 차례는 {n}번입니다.", n=game.turns_left), key=False)
    first = list(alive)
    game.rng.shuffle(first)
    hands: dict[int, int] = {p.seat: 1 for p in alive}
    spoke: Counter[int] = Counter()
    owed: list[Player] = []
    named_by: dict[int, str] = {}
    last: Player | None = None
    silent_run, warned, would_end = 0, False, False
    end = game._end_day or asyncio.Event()
    game.queued, game.talk = {}, asyncio.Event()
    # a round is everyone who can speak having had a turn or passed; then lowered hands go up again, so
    # one 「hand 0」 never drops a player for the rest of the talk. A round with nothing said ends the talk.
    rnd: dict[str, Any] = {"done": set(), "said": False}
    replied: set[int] = set()  # seats whose latest turn was a reply turn
    failed: dict[int, str] = {}  # seats whose latest call failed, with the reason
    reply_turn = False

    def talk_state(now: Player | None = None, speaking: Player | None = None) -> None:
        """Each player's talk state for the player list: who is answering, who just spoke, hands, passes."""
        states: dict[str, str] = {}
        for q in game.alive():
            if q is now:
                states[str(q.seat)] = "thinking"
            elif q is speaking:
                states[str(q.seat)] = "speaking"
            elif q.seat in failed:
                states[str(q.seat)] = "failed"
            elif not can_speak(game, q):
                continue
            else:
                states[str(q.seat)] = "hand" if hands.get(q.seat, 0) > 0 else "done"
        game.emit("talk", log=False, states=states, why={str(k): v for k, v in failed.items()})

    def waiting(but: Player | None = None) -> list[Player]:
        return [q for q in game.alive() if can_speak(game, q) and q is not but and q is not last
                and hands.get(q.seat, 0) > 0 and q.seat not in rnd["done"]]

    def typed() -> Player | None:
        """A person who typed a line goes next, before replies and hands."""
        for seat in list(game.queued):
            q = game.players[seat]
            if game.queued[seat] and can_speak(game, q):
                return q
            game.queued.pop(seat)
        return None

    def choose() -> tuple[Player | None, bool]:
        """The next speaker, and whether it is a reply turn."""
        q = divine.floor_taker(game)  # 발언 시키기
        if q is not None and can_speak(game, q):
            if q in first:
                first.remove(q)
            return q, False
        while first:  # everyone speaks once before replies (replies had starved the person)
            q = first.pop(0)
            if can_speak(game, q):
                return q, False
        while owed:
            q = owed.pop(0)
            if not can_speak(game, q) or q is last:
                continue
            others = [o for o in game.alive() if o is not q and o is not last and can_speak(game, o) and hands.get(o.seat, 0) > 0]
            if q.seat in replied and others:  # no two reply turns in a row while others wait with hands up
                named_by.pop(q.seat, None)
                continue
            return q, True
        if silent_run >= len(game.alive()):
            return None, False
        cands = waiting()
        if not cands:
            if not rnd["said"]:
                return None, False  # a whole round and nobody had anything to say
            rnd["done"], rnd["said"] = set(), False
            for q in game.alive():
                hands[q.seat] = max(1, hands.get(q.seat, 0))
            cands = waiting()
            if not cands:
                return None, False
        return max(cands, key=lambda q: hands[q.seat] * 10 - spoke[q.seat] * 6 + game.rng.random() * 4), False

    while not end.is_set() and not game.skip:
        p = typed()  # a line the person sent while the turns lasted is never lost
        if p is None and game.turns_left <= 0 and s.moderator != "human":
            break
        reply_turn = False
        if p is None:
            p, reply_turn = choose()
        if p is None:
            if s.moderator != "human":
                break
            if not would_end:
                would_end = True
                game.emit("would_end", T("자동 진행이라면 지금 토론이 끝납니다."), log=False)
            game.talk.clear()
            await _first_of(end, game.talk)  # the moderator ends it, or the person says something more
            continue
        if game.turns_left <= 0 and not would_end:
            would_end = True
            game.emit("would_end", T("자동 진행이라면 지금 토론이 끝납니다."), log=False)
        lines = game.queued.get(p.seat)
        if lines:
            obj = {"say": lines.pop(0)}
            for queue in (first, owed):
                if p in queue:
                    queue.remove(p)
        else:
            talk_state(now=p)
            n0 = len(game.events)
            obj = await game.ask(p, discuss_request(game, p, named_by.pop(p.seat, "")))
            errs = [e for e in game.events[n0:] if e.kind == "error" and e.actor == p.seat]
            if errs and not obj:
                failed[p.seat] = str(errs[-1].data.get("reason") or "provider")
            else:
                failed.pop(p.seat, None)
        (replied.add if reply_turn else replied.discard)(p.seat)
        rnd["done"].add(p.seat)
        spoke[p.seat] += 1
        last = p
        say = clean_speech(obj.get("say"))
        if say:
            game.turns_left = max(0, game.turns_left - 1)  # a pass costs no shared turn
            rnd["said"] = True
            game.emit("say", say, actor=p.seat, sound="say", **({"reply": True} if reply_turn else {}))
            silent_run = 0
            if first:  # during the first pass only the latest line's reply waits for after it
                owed.clear()
                named_by.clear()
            for q in named_in(game, say, p)[:1]:
                if q not in owed:
                    owed.append(q)
                    named_by[q.seat] = p.name
        else:
            silent_run += 1
        ask_time(game, p, obj.get("time"))
        point(game, p, obj.get("poll"))
        hands[p.seat] = read_hand(obj.get("hand"), bool(say)) if say else 0  # silence lowers the hand
        _turns_event(game, total)
        talk_state(speaking=p if say else None)
        if not warned and 0 < game.turns_left <= len(game.alive()):
            warned = True
            game.system(T("토론 시간이 얼마 남지 않았습니다."), key=False, sound="warn")
        await game.pace(bool(say))
    for seat, left in game.queued.items():  # the discussion ended before these lines came up
        if left:
            game.observe("queued", "", actor=seat, dropped=len(left))
    game.queued, game.talk = {}, None
    game.turns_left = max(0, game.turns_left)
    _turns_event(game, total)
    game.emit("talk", log=False, states={}, why={})


async def whisper_time(game: "Game", vote_next: bool = True) -> None:
    """귓속말 시간: one whisper or a pass each, in random order, then one reply per sender."""
    game.skip = False
    game.set_step("귓속말 시간")
    game.system(T("귓속말 시간입니다."), key=False, sound="whisper")
    order = [p for p in game.alive() if can_speak(game, p)]
    game.rng.shuffle(order)
    got: dict[int, list[Player]] = {}

    async def send(p: Player) -> None:
        if game.skip or not p.alive:
            return
        others = [q.name for q in game.alive() if q is not p]
        req = TurnRequest("whisper", T("귓속말 시간이다. 네 차례다. 살아 있는 사람 한 명을 골라 귓속말을 한 번 보내거나, "
                                       "보내지 않으려면 whispers를 빈 목록으로 둔다."), whispers=1, whisper_to=others)
        obj = await game.ask(p, req)
        for q in whisper(game, p, obj.get("whispers"), 1, others):
            got.setdefault(q.seat, []).append(p)
        await game.pace(bool(obj.get("whispers")))

    await in_order(game, order, send)
    replies = [game.players[s] for s in got]
    game.rng.shuffle(replies)

    async def reply(q: Player) -> None:
        if game.skip or not q.alive or not can_speak(game, q):
            return
        senders = [s.name for s in got[q.seat] if s.alive]
        if not senders:
            return
        req = TurnRequest("whisper_reply", T("귓속말 답장 차례다. 너에게 귓속말을 보낸 사람({names})에게 "
                                             "한 번씩 답할 수 있다. 이것이 오늘 마지막 귓속말이다. 답하지 않아도 된다.", names=senders),
                          whispers=len(senders), whisper_to=senders)
        obj = await game.ask(q, req)
        whisper(game, q, obj.get("whispers"), len(senders), senders)
        await game.pace(bool(obj.get("whispers")))

    await in_order(game, replies, reply)
    if vote_next:
        game.system(T("투표 시간입니다."), key=False, sound="vote")


async def in_order(game: "Game", order: list[Player], one: Any) -> None:
    """Models one after another in `order`; a person's card is there the moment the step starts, and
    the step waits for their answer at the end."""
    people = [asyncio.ensure_future(one(p)) for p in order if p.kind == "human"]
    try:
        for p in order:
            if game.skip:
                break
            if p.kind != "human":
                await one(p)
        if not game.skip:
            await asyncio.gather(*people)
    finally:
        for t in people:
            t.cancel()


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
    """연장 adds turns, once a day each. 단축 is a public vote to move on, once a day each; when more than
    half of the living players have pressed it the talk ends at once."""
    v = str(from_word(game.lang, str(raw or "").strip()))
    if not p.alive or game.step != "토론" or v not in (EXTEND, SHORTEN):
        return
    if v == EXTEND and p.seat not in game.time_used:
        game.time_used.add(p.seat)
        game.turns_left += game.setup.extend_step
        game.system(T("{name}님이 토론 시간을 늘렸습니다.", name=p.name), key=False, time=v, actor_seat=p.seat)
        _turns_event(game, game.turns_total)
    elif v == SHORTEN and p.seat not in game.cut_votes:
        game.cut_votes.add(p.seat)
        alive = {q.seat for q in game.alive()}
        votes, need = len(game.cut_votes & alive), len(alive) // 2 + 1
        game.system(T("{name}님이 토론을 끝내자고 했습니다. ({votes}/{need})", name=p.name, votes=votes, need=need),
                    key=False, time=v, actor_seat=p.seat, cut=votes, need=need)
        if votes >= need:
            game.system(T("과반이 넘어가기를 원해 토론을 끝냅니다."), key=False, cut_done=True)
            game.end_day()


def time_open(game: "Game", p: Player) -> bool:
    return p.seat not in game.time_used or p.seat not in game.cut_votes


def point(game: "Game", p: Player, raw: Any) -> None:
    if raw is None:
        return
    if is_skip(from_word(game.lang, raw)) or str(raw).strip() == "":
        changed = game.poll.pop(p.seat, None) is not None
    else:
        name = match_name(str(raw), [q.name for q in game.alive()])
        changed = name is not None and game.poll.get(p.seat) != name
        if name is not None:
            game.poll[p.seat] = name
    if changed:
        game.emit("poll", log=False, counts=game.poll_counts())


def _tally_text(counts: dict[str, int], voters: dict[str, list[str]] | None, skipped: list[str], public: bool) -> Msg:
    parts: list[Msg] = []
    for name, n in counts.items():
        if public and voters:
            parts.append(T("{name}님 {n}표({who})", name=name, n=n, who=voters[name]))
        else:
            parts.append(T("{name}님 {n}표", name=name, n=n))
    if skipped:
        parts.append(T("기권 {n}({who})", n=len(skipped), who=skipped) if public else T("기권 {n}", n=len(skipped)))
    return T("투표 결과: {tally}", tally=parts) if parts else T("투표 결과: {tally}", tally=T("아무도 투표하지 않았습니다"))


async def vote(game: "Game") -> Player | None:
    game.skip = False
    divine.on_trial(game, None)
    game.set_step("투표")
    alive = game.alive()
    voters = [p for p in alive if p.no_vote_day != game.day]
    for p in alive:
        if p.no_vote_day == game.day:
            game.private(p, T("오늘은 투표할 수 없다."))
    opts = [q.name for q in alive]

    extras: dict[int, Any] = {}

    async def one(p: Player) -> tuple[Player, str | None]:
        req = TurnRequest("vote", T("투표 시간이다. 최후의 반론에 올릴 사람 한 명에게 투표한다. 자기 자신에게도 투표할 수 있고 기권도 된다. "
                                    "가장 많이 받은 사람이 최후의 반론을 하고, 그다음 찬반으로 처형을 정한다. 최다 득표가 동점이면 바로 밤이 된다."),
                          field="vote", options=opts, skip_word="기권")
        with_extra(req, ability_for(p).vote_extra(game, p))
        obj = await game.ask(p, req)
        if req.extra_field:
            extras[p.seat] = obj.get(req.extra_field)
        return p, game.pick(obj, req)

    picks = await asyncio.gather(*(one(p) for p in voters))
    await game.checkpoint()
    if divine.revote_pending(game):  # 재투표 while the votes came in: this vote counts for nothing
        return None
    for p, t in picks:  # 유혹자's seduction, 모방자's theft: private, after everyone voted
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
    text = _tally_text(ordered, by, skipped, public)
    game.emit("vote_result", text, key=True, counts=ordered, voters=by, skipped=skipped,
              votes={p.seat: t for p, t in picks}, public=public, sound="reveal")
    if not ordered:
        game.system(T("아무도 투표하지 않아 밤이 됩니다."))
        return None
    top = max(ordered.values())
    leaders = [n for n, c in ordered.items() if c == top]
    if len(leaders) > 1:
        game.system(T("최다 득표가 동점이라 밤이 됩니다."))
        return None
    cand = game.by_name(leaders[0])
    if cand is None:
        return None
    game.system(T("{name}님이 최다 득표로 최후의 반론을 합니다.", name=cand.name), target=cand.seat)
    divine.on_trial(game, cand)
    return cand


def with_extra(req: TurnRequest, extra: TurnRequest | None) -> None:
    """A role's second choice (모방자's theft, 폭탄마's target) rides on the same call."""
    if extra is not None and extra.extra_field:
        req.extra_field, req.extra_options, req.extra_task = extra.extra_field, extra.extra_options, extra.extra_task


async def defense(game: "Game", cand: Player) -> Any:
    """The last word; returns the answer to the candidate's defence extra (폭탄마: whom to take along)."""
    game.set_step("최후의 반론")
    req = TurnRequest("defense", T("최후의 반론이다. 너는 최다 득표로 처형 직전이다. 이번에는 2~4문장까지 말해도 된다. "
                                   "찬반에서 찬성이 반대보다 적으면 살아남는다."), say=can_speak(game, cand))
    with_extra(req, ability_for(cand).defense_extra(game, cand))
    if not can_speak(game, cand):
        game.system(T("{name}님은 오늘 말할 수 없습니다.", name=cand.name))
        if not req.extra_field:
            return None
        req.task = T("최후의 반론이지만 너는 오늘 말할 수 없다. 처형될 때를 대비한 선택만 한다.")
        extra = (await game.ask(cand, req)).get(req.extra_field)
        ability_for(cand).defense_choice(game, cand, extra)
        return extra
    obj = await game.ask(cand, req)
    if req.extra_field:
        ability_for(cand).defense_choice(game, cand, obj.get(req.extra_field))
    say = clean_speech(obj.get("say"), 600)
    if say:
        game.emit("say", say, actor=cand.seat, key=True, defense=True, sound="say")
    else:
        game.system(T("{name}님은 아무 말도 하지 않았습니다.", name=cand.name), key=False)
    await game.pace(bool(say))
    return obj.get(req.extra_field) if req.extra_field else None


def _pardoned(game: "Game", cand: Player) -> bool:
    """사면: the trial ends with no execution, whatever the count."""
    if divine.pardoned(game):
        game.system(T("신의 사면으로 {name}님은 처형되지 않았습니다.", name=cand.name), target=cand.seat)
        return True
    return False


async def verdict(game: "Game", cand: Player, extra: Any = None) -> None:
    if _pardoned(game, cand):
        return
    game.set_step("찬반")
    voters = [p for p in game.alive() if p is not cand and p.no_vote_day != game.day]
    yes_no = ["찬성", "반대"]

    async def one(p: Player) -> tuple[Player, str | None]:
        req = TurnRequest("verdict", T("찬반 투표다. {name}님을 처형할지 정한다. 찬성이 반대보다 많거나 같으면 처형된다. 기권은 반대로 센다.",
                                       name=cand.name), field="verdict", options=yes_no, skip_word="기권")
        return p, game.pick(await game.ask(p, req), req)

    picks = await asyncio.gather(*(one(p) for p in voters))
    await game.checkpoint()
    if divine.revote_pending(game) or _pardoned(game, cand):
        return
    yes = sum(ability_for(p).vote_weight(p) for p, t in picks if t == "찬성")
    no = sum(ability_for(p).vote_weight(p) for p, t in picks if t != "찬성")
    public = game.setup.vote_public
    ayes = [p.name for p, t in picks if t == "찬성"]
    nays = [p.name for p, t in picks if t == "반대"]
    skips = [p.name for p, t in picks if t is None]
    text = T("찬반 결과: 찬성 {yes}, 반대 {no}", yes=yes, no=no)
    if public:
        text = T("찬반 결과: 찬성 {yes}, 반대 {no} (찬성: {ayes} / 반대: {nays})", yes=yes, no=no,
                 ayes=ayes or "없음", nays=(nays + skips) or "없음")
    game.emit("verdict_result", text, key=True, yes=yes, no=no, ayes=ayes, nays=nays, skipped=skips,
              votes={p.seat: t for p, t in picks}, public=public, target=cand.seat, sound="reveal")
    passed = yes >= no and yes > 0
    for j, t in picks:  # 배심장 (a voter, never the candidate): the outcome follows its own pick
        turned = ability_for(j).override_verdict(game, j, t, passed) if j.alive else None
        if turned is not None:
            passed = turned
    if not passed:
        game.system(T("{name}님은 처형되지 않았습니다.", name=cand.name))
        return
    ab = ability_for(cand)
    if not ab.executable(game, cand):
        game.system(T("{name}님은 투표로 처형되지 않습니다.", name=cand.name))
        return
    if any(ability_for(q).spare(game, q, cand) for q in game.alive()):  # 위장꾼 survives once
        return
    game.kill(cand, T("{name}님이 처형되었습니다.", name=cand.name), "execution")
    ab.on_executed(game, cand, extra)
    shot = ab.last_shot(game, cand)  # 사냥꾼: after the 찬반, one living player goes along
    if shot is not None and shot.options:
        ab.take_shot(game, cand, game.pick(await game.ask(cand, shot), shot))
