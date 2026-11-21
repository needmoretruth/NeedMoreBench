"""The game loop shared by both games: events, calls, the night, deaths, god powers and the win checks.

The engine is the moderator: it keeps the rules and the clock. A game starts in the
day with introductions and talk and no vote; then every night is followed by a day of 토론 → 귓속말 시간 → 투표 →
최후의 반론 → 찬반 (nmb.engine.day). It runs on an asyncio loop; the UI posts god
powers and human answers into that loop and reads the event stream.
"""
from __future__ import annotations

import asyncio
import random
import time
from collections import Counter
from typing import Any, Callable, Protocol

from . import day as day_flow
from . import god as divine
from . import night as night_flow
from .abilities import NightContext, ability_for, ability_of, in_mafia_team
from .abilities.base import side
from .abilities.cult import cults, members
from .parse import clean_speech, is_skip, match_name, read_ledger, read_notes
from .roles import CULT, MAFIA, ROLES, TEAM_LABEL, TOWN, guess_options
from .setup import GameSetup
from .state import Event, Player
from .text import LANGS, Msg, T, from_word, say
from .turn import TurnRequest
from .words import josa


class GameOver(Exception):
    pass


class Controller(Protocol):
    async def decide(self, game: "Game", p: Player, req: TurnRequest) -> dict[str, Any]: ...


class Game:
    def __init__(self, setup: GameSetup, players: list[Player], controllers: dict[int, Controller],
                 sink: Callable[[Event], None] | None = None, rng: random.Random | None = None):
        self.setup = setup
        self.kind = setup.kind
        self.players = players
        self.controllers = controllers
        self.sink = sink or (lambda e: None)
        self.rng = rng or random.Random(setup.seed)
        self.events: list[Event] = []
        self.day, self.phase, self.step = 0, "day", ""
        self.result: dict[str, Any] | None = None
        self.god_protect: set[str] = set()
        self.divine = divine.Divine()  # what the god powers keep between steps
        self.blocked_next: set[str] = set()  # no ability on the coming night (유혹자's seduction)
        self.town_learned: list[tuple[str, str]] = []  # (name, role) the citizen team found out (소문꾼)
        self.skip = False
        self.turns_left = 0
        self.time_used: set[int] = set()  # pressed 연장 today
        self.cut_votes: set[int] = set()  # pressed 단축 today: a vote to end the talk
        self.turns_total = 0
        self.poll: dict[int, str] = {}
        self.calls: list[dict[str, Any]] = []
        self.on_raw: Callable[[int, int, str, str, str], None] | None = None  # call id, seat, system, user, raw answer
        self.snapshots: list[dict[str, Any]] = []
        self.started = time.time()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._resume: asyncio.Event | None = None
        self._end_day: asyncio.Event | None = None
        self.paused = False
        self.locks: dict[int, asyncio.Lock] = {}
        self.queued: dict[int, list[str]] = {}  # a person's lines typed during 토론, said at the next boundary
        self.talk: asyncio.Event | None = None  # set when such a line arrives, so a waiting discussion goes on
        self.meeting: frozenset[int] | None = None  # who reads the mafia meeting while it runs

    # ---- lookups -------------------------------------------------------------------------------------
    def name_of(self, seat: int | None) -> str:
        return self.players[seat].name if seat is not None and 0 <= seat < len(self.players) else "?"

    def by_name(self, name: str | None) -> Player | None:
        if not name:
            return None
        for p in self.players:
            if p.name == name:
                return p
        m = match_name(name, [p.name for p in self.players])
        return next((p for p in self.players if p.name == m), None)

    def alive(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def public_role(self, q: Player) -> str | None:
        if q.revealed or (not q.alive and self.setup.reveal):
            return q.role
        return None

    def guess_options(self) -> list[str]:
        from .lineups import possible_roles
        from .setup import playable
        return guess_options(self.kind, possible_roles(self.setup, len(self.players), playable))

    @property
    def lang(self) -> str:
        return self.setup.language if self.setup.language in LANGS else "ko"

    def t(self, x: "str | Msg | None") -> str:
        """Engine text in this game's dialogue language."""
        return say(self.lang, x)

    def phase_label(self) -> Msg:
        base = T("{n}번째 밤", n=self.day) if self.phase == "night" else T("{n}번째 낮", n=self.day)
        return T("{base}, {step}", base=base, step=self.step) if self.step else base

    def set_step(self, step: str, **data: Any) -> None:
        """The part of the day (소개, 아침, 토론, 투표, 최후의 반론, 찬반): screens and replays read it from this event."""
        self.step = step
        self.emit("step", T("{step}", step=step), log=False, step=step, **data)

    def poll_counts(self) -> dict[str, int]:
        alive = {p.name for p in self.alive()}
        c = Counter(t for s, t in self.poll.items() if t in alive and self.players[s].alive)
        return dict(c.most_common())

    # ---- events --------------------------------------------------------------------------------------
    def emit(self, kind: str, text: "str | Msg" = "", actor: int | None = None, target: int | None = None,
             to: frozenset[int] | None = None, log: bool = True, key: bool = False, **data: Any) -> Event:
        if isinstance(text, Msg):  # the record keeps the key and parameters; the text is in the game's language
            data["msg"] = text.record()
            text = text.render(self.lang)
        e = Event(len(self.events), kind, self.day, self.phase, text, actor, target, to, log, key, data)
        self.events.append(e)
        self.sink(e)
        return e

    def system(self, text: "str | Msg", key: bool = True, target: int | None = None, **data: Any) -> Event:
        return self.emit("system", text, target=target, key=key, **data)

    def private(self, p: Player, text: "str | Msg", kind: str = "private", target: int | None = None, **data: Any) -> Event:
        if "result" in data:  # a pending 거짓 결과 arrives as this very line
            text, data = divine.fake_result(self, p, text, data)
        return self.emit(kind, text, target=target, to=frozenset({p.seat}), key=True, **data)

    def observe(self, kind: str, text: "str | Msg" = "", actor: int | None = None, **data: Any) -> Event:
        """Observer-only: never in a prompt; a playing human sees only their own."""
        to = frozenset({actor}) if actor is not None else frozenset()
        return self.emit(kind, text, actor=actor, to=to, log=False, **data)

    # ---- calls ---------------------------------------------------------------------------------------
    async def ask(self, p: Player, req: TurnRequest) -> dict[str, Any]:
        """One call. A player never has two calls at once: a mafia member with a night ability of its
        own answers the meeting and the ability one after the other, so its context never branches."""
        lock = self.locks.setdefault(p.seat, asyncio.Lock())
        async with lock:
            self.observe("thinking", actor=p.seat, on=True, call=req.kind)
            try:
                obj = await self.controllers[p.seat].decide(self, p, req)
            finally:
                self.observe("thinking", actor=p.seat, on=False)
        obj = obj if isinstance(obj, dict) else {}
        if p.alive:
            self.apply_common(p, obj)
        return obj

    def pick(self, obj: dict[str, Any], req: TurnRequest, field: str | None = None,
             options: list[str] | None = None) -> str | None:
        field = field or req.field
        v = from_word(self.lang, obj.get(field) if field else None)  # 'Yes' in an English game is 찬성
        if is_skip(v):
            return None
        return match_name(v, options if options is not None else req.options)

    def apply_common(self, p: Player, obj: dict[str, Any]) -> None:
        thought = clean_speech(obj.get("thought"), 400)
        if thought:
            self.observe("thought", thought, actor=p.seat)
        edits, _ = read_ledger(obj.get("ledger"), list(p.ledger), self.guess_options(), lambda g: from_word(self.lang, g))
        for ed in edits:
            row = p.ledger[ed["name"]]
            old = {"suspicion": row.suspicion, "guess": row.guess, "note": row.note}
            row.suspicion = ed.get("suspicion", row.suspicion)
            row.guess = ed.get("guess", row.guess)
            row.note = ed.get("note", row.note)
            new = {"suspicion": row.suspicion, "guess": row.guess, "note": row.note}
            if new != old:
                self.observe("ledger", ed["name"], actor=p.seat, name=ed["name"], old=old, new=new)
        page = read_notes(obj.get("notes"))
        if page is not None and p.notebook.write(page):  # over the limit after the one send-back: the page stays
            self.observe("note", page, actor=p.seat, version=p.notebook.version, chars=len(page))

    def know(self, p: Player, q: Player) -> None:
        """p is told for certain that q is on its team, and q's role: the row starts at 0, 확인됨."""
        row = p.ledger.get(q.name)
        if row is None or row.known:
            return
        old = {"suspicion": row.suspicion, "guess": row.guess, "note": row.note, "known": row.known}
        row.suspicion, row.known = 0, True
        row.guess = q.role if q.role in self.guess_options() else row.guess
        self.observe("ledger", q.name, actor=p.seat, name=q.name, old=old,
                     new={"suspicion": row.suspicion, "guess": row.guess, "note": row.note, "known": True})

    def edit_own(self, seat: int | None, obj: dict[str, Any]) -> None:
        """A person changes their own ledger and notes from the screen at any time (참가); the same
        checks as a model's edits apply, and a model seat cannot be edited this way."""
        if self.result is not None or seat is None or not 0 <= seat < len(self.players):
            return
        p = self.players[seat]
        if p.kind == "human":
            self.apply_common(p, {"ledger": obj.get("ledger"), "notes": obj.get("notes")})

    def record_call(self, p: Player, req: TurnRequest, model: str, comp: Any, system: str, user: str,
                    problem: str | None) -> None:
        """One model call: its cost and timing for the record, its raw answer on an observer event."""
        entry = {"id": len(self.calls), "seat": p.seat, "kind": req.kind, "model": model, "day": self.day,
                 "phase": self.phase, "ms": comp.ms, "tokens_in": comp.tokens_in, "tokens_out": comp.tokens_out,
                 "estimated": comp.estimated, "cost": comp.cost, "problem": problem}
        self.calls.append(entry)
        self.observe("call", "", actor=p.seat, call_id=entry["id"], call_kind=req.kind, model=model, ms=comp.ms,
                     tokens_in=comp.tokens_in, tokens_out=comp.tokens_out, tokens_estimated=comp.estimated,
                     cost=comp.cost, problem=problem)
        reasoning = getattr(comp, "reasoning", "")
        if reasoning:  # the model's own reasoning: the god view and the record only, never a prompt
            self.emit("reasoning", reasoning, actor=p.seat, to=frozenset(), log=False, call_id=entry["id"],
                      route=model.split(":", 1)[0], summarized=bool(getattr(comp, "summarized", False)),
                      tokens=getattr(comp, "reasoning_tokens", None))
        if self.on_raw is not None:
            self.on_raw(entry["id"], p.seat, system, user, comp.text)

    def record_error(self, p: Player, err: Exception, attempt: int, text: str | None = None, **data: Any) -> None:
        """A failed call counts in the stats; the timeline gets a line (in plain words) only when `text` is given:
        when the seat gives up this turn or changes route, not on every retry."""
        reason = getattr(err, "reason", "provider")
        self.calls.append({"id": len(self.calls), "seat": p.seat, "kind": "error", "day": self.day, "phase": self.phase,
                           "ms": 0, "tokens_in": 0, "tokens_out": 0, "estimated": True, "cost": 0.0, "problem": reason})
        if text:
            self.observe("error", text, actor=p.seat, reason=reason, attempt=attempt, message=str(err)[:300], **data)

    async def pace(self, said: bool) -> None:
        if said and self.setup.delay > 0:
            await asyncio.sleep(self.setup.delay)
        await self.checkpoint()

    async def checkpoint(self) -> None:
        if self._resume is not None and not self._resume.is_set():
            await self._resume.wait()
        if self.result is not None:
            raise GameOver

    # ---- flow ----------------------------------------------------------------------------------------
    async def run(self) -> dict[str, Any] | None:
        self.loop = asyncio.get_running_loop()
        self._resume = asyncio.Event()
        self._resume.set()
        self._end_day = asyncio.Event()
        self.observe("start", T("게임을 시작합니다"), roster=[self.seat_info(p) for p in self.players])
        team = [p for p in self.players if in_mafia_team(p)]
        for p in team:  # the mafia know each other from the start
            for q in team:
                if q is not p:
                    self.know(p, q)
        for p in self.players:
            ability_of(p.role).on_start(self, p)
        try:
            await self.play()
        except GameOver:
            pass
        self.finish()
        return self.result

    async def play(self) -> None:
        """Day first: 1번째 낮 is introductions and talk with no vote, then 1번째 밤; night N is followed by
        day N+1."""
        await day_flow.first_day(self)
        self.judge()
        while True:
            night = self.day
            await self.night()
            self.judge()
            if night >= self.setup.max_nights:
                self.result = self.make_result(MAFIA, T("{n}번째 밤이 지나도록 끝나지 않아 마피아 팀이 이겼습니다", n=night))
                raise GameOver
            await day_flow.run_day(self)
            self.judge()

    def judge(self) -> None:
        """The win check, run only at the end of a night and after the 찬반."""
        if self.result is None:
            self.check_win()
        if self.result is not None:
            raise GameOver

    async def night(self) -> None:
        await night_flow.run_night(self)

    def kill(self, q: Player, text: "str | Msg", cause: str, ctx: NightContext | None = None) -> None:
        q.alive = False
        q.died_day = ctx.night if ctx is not None else self.day  # a night death belongs to that night's date
        line = T("{text} {name}님은 {role:이었습니다/였습니다}.", text=text, name=q.name, role=q.role) if self.setup.reveal else text
        self.emit("death", line, target=q.seat, key=True, cause=cause, role=q.role, sound="death")
        ability_of(q.role).on_death(self, q, cause, ctx)

    def set_role(self, p: Player, role: str, text: "str | Msg") -> None:
        """p's role changes (계승자, 역할 바꾸기): p alone is told, the observer sees it."""
        old, p.role = p.role, role
        self.private(p, text, role=role)
        self.emit("role", T("{name}님의 직업이 {old}에서 {role:으로/로} 바뀌었습니다.", name=p.name, old=old, role=role),
                  target=p.seat, to=frozenset({p.seat}), log=False, old=old, role=role)  # the observer and that player

    def revive(self, q: Player, text: "str | Msg", ctx: NightContext | None = None) -> None:
        """A dead player comes back (부활술사, 불사신): announced in the morning, or at once by day."""
        q.alive = True
        q.at_rest = False
        if ctx is not None:
            ctx.morning.append(text)
        else:
            self.system(text, target=q.seat, sound="save")
        self.emit("revive", "", target=q.seat, log=False)  # every screen: the card comes back to life

    def snapshot(self) -> None:
        for p in self.alive():
            self.snapshots.append({"day": self.day, "seat": p.seat,
                                   "sus": {n: r.suspicion for n, r in p.ledger.items()},
                                   "guess": {n: r.guess for n, r in p.ledger.items()}})

    # ---- winning -------------------------------------------------------------------------------------
    def check_win(self) -> None:
        """In order: the mafia team, a cult, the citizen team, a role that wins for its side (기수)."""
        alive = self.alive()
        if not alive:
            self.result = self.make_result(None, T("모두 죽었습니다"))
            return
        mafia = [p for p in alive if in_mafia_team(p)]
        held = any(ability_of(p.role).holds_game(self, p) for p in alive)
        if mafia and len(mafia) >= len(alive) - len(mafia) and not held:
            self.result = self.make_result(MAFIA, T("마피아 팀 수가 시민 팀 수와 같아졌습니다"))
            return
        for cid, flock in cults(self).items():
            if flock and len(flock) >= len(alive) - len(flock):
                winners = [p.seat for p in members(self, cid, alive=False)]
                self.result = self.make_result(CULT, T("교주 팀이 산 사람의 절반 이상이 되었습니다"), winners)
                return
        if not mafia and not held:
            self.result = self.make_result(TOWN, T("마피아 팀이 모두 죽었습니다"))
            return
        flag = next((p for p in alive if ability_for(p).wins(self, p)), None)
        if flag is not None:
            self.result = self.make_result(side(flag), T("{role} {name}님이 {n}번째 낮까지 살아남았습니다", role=flag.role,
                                                         name=flag.name, n=self.day))
            return

    def make_result(self, team: str | None, reason: "str | Msg", winners: list[int] | None = None) -> dict[str, Any]:
        """label and reason in the game's language; `msg` keeps both as messages for another interface language.
        The winners are the players on that side at the end (a convert wins with its cult, not its first team)."""
        if winners is None:
            winners = [] if team is None else [p.seat for p in self.players if side(p) == team]
        label = T("무승부") if team is None else T("{team} 승리", team=TEAM_LABEL[team])
        return {"team": team, "label": self.t(label), "reason": self.t(reason), "winners": sorted(winners),
                "day": self.day, "msg": {"label": label.record(), "reason": reason.record() if isinstance(reason, Msg) else None}}

    def finish(self) -> None:
        self.phase, self.step = "end", ""
        r = self.result or self.make_result(None, T("게임이 중단되었습니다"))
        self.result = r
        line = T("{label}. {reason}.", label=Msg.load(r.get("msg", {}).get("label")) or r["label"],
                 reason=Msg.load(r.get("msg", {}).get("reason")) or r["reason"])
        self.emit("end", line, key=True, result=r, sound="win" if r["team"] else "lose",
                  roles={p.seat: p.role for p in self.players})

    def seat_info(self, p: Player) -> dict[str, Any]:
        return {"seat": p.seat, "name": p.name, "role": p.role, "kind": p.kind, "model_key": p.model_key,
                "model_name": p.model_name, "shown": p.shown.line()}

    # ---- god powers and the human moderator (called inside the loop) ---------------------------------
    def god(self, power: str, seat: int | None = None, text: str = "", role: str | None = None, by: str = "신",
            other: int | None = None, n: int = 0, user: int | None = None) -> bool:
        """신의 권능 (nmb.engine.god). `role` carries the pick a power takes (a role, a false result);
        `user` is a cheating participant's seat, kept only in the god-only record. The human moderator's 공지
        is its own line."""
        if by == "사회자":
            if power == "공지" and text.strip():
                self.emit("moderator", text.strip(), key=True, power="공지", by=by, sound="god")
            return True
        return divine.use(self, power, seat, text, role, other, n, user)

    def stop(self) -> None:
        """The user stopped the game: it ends where it stands and the record stays 중단됨 (no result line)."""
        if self.result is None:
            label, reason = T("중단됨"), T("게임을 멈췄습니다")
            self.result = {"team": None, "label": self.t(label), "reason": self.t(reason), "winners": [], "day": self.day,
                           "stopped": True, "msg": {"label": label.record(), "reason": reason.record()}}
        self.set_paused(False)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if self._resume is not None:
            self._resume.clear() if paused else self._resume.set()
        self.observe("pause", T("일시정지") if paused else T("다시 진행"), paused=paused)

    def queue_line(self, seat: int | None, text: str) -> None:
        """a playing person speaks whenever they want in 토론. The line goes in right after the current
        speaker, ahead of replies and hands, and spends one shared turn."""
        if seat is None or not 0 <= seat < len(self.players) or self.result is not None:
            return
        p, line = self.players[seat], clean_speech(text)
        if p.kind != "human" or not p.alive or not line:
            return
        if self.meeting is not None and seat in self.meeting:  # a person on the mafia team speaks in the meeting
            self.emit("mafia", line, actor=seat, to=self.meeting, key=True, pick=None, sound="mafia")
            return
        if self.step != "토론":
            return
        self.queued.setdefault(seat, []).append(line)
        self.observe("queued", line, actor=seat)
        if self.talk is not None:
            self.talk.set()

    def press_time(self, seat: int | None, word: str) -> None:
        """The person's 연장 / 단축 buttons during 토론: the same rules as a model's `time`."""
        if seat is not None and 0 <= seat < len(self.players) and self.players[seat].kind == "human" and self.result is None:
            day_flow.ask_time(self, self.players[seat], word)

    def end_day(self) -> None:
        """사람 사회자 ends the discussion (투표로)."""
        if self._end_day is not None:
            self._end_day.set()

    def post(self, fn: Callable[..., None], *args: Any, **kw: Any) -> None:
        """Thread-safe: run fn(*args, **kw) inside the game loop."""
        if self.loop is not None and not self.loop.is_closed():  # a finished game ignores late clicks
            self.loop.call_soon_threadsafe(lambda: fn(*args, **kw))
