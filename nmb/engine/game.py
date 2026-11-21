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
from . import night as night_flow
from .abilities import NightContext, ability_of, in_mafia_team
from .parse import clean_speech, is_skip, match_name, read_ledger, read_notes
from .roles import MAFIA, ROLES, TEAM_LABEL, TOWN, guess_options, team_of
from .setup import GameSetup
from .state import Event, Player
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
        self.blocked_next: set[str] = set()  # no ability on the coming night (마담's seduction)
        self.town_learned: list[tuple[str, str]] = []  # (name, role) the citizen team found out (파파라치)
        self.skip = False
        self.turns_left = 0
        self.time_used: set[int] = set()
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
        return guess_options(self.kind, [p.start_role for p in self.players])

    def phase_label(self) -> str:
        base = f"{self.day}번째 밤" if self.phase == "night" else f"{self.day}번째 낮"
        return f"{base}, {self.step}" if self.step else base

    def set_step(self, step: str, **data: Any) -> None:
        """The part of the day (소개, 아침, 토론, 투표, 최후의 반론, 찬반): screens and replays read it from this event."""
        self.step = step
        self.emit("step", step, log=False, step=step, **data)

    def poll_counts(self) -> dict[str, int]:
        alive = {p.name for p in self.alive()}
        c = Counter(t for s, t in self.poll.items() if t in alive and self.players[s].alive)
        return dict(c.most_common())

    # ---- events --------------------------------------------------------------------------------------
    def emit(self, kind: str, text: str = "", actor: int | None = None, target: int | None = None,
             to: frozenset[int] | None = None, log: bool = True, key: bool = False, **data: Any) -> Event:
        e = Event(len(self.events), kind, self.day, self.phase, text, actor, target, to, log, key, data)
        self.events.append(e)
        self.sink(e)
        return e

    def system(self, text: str, key: bool = True, target: int | None = None, **data: Any) -> Event:
        return self.emit("system", text, target=target, key=key, **data)

    def private(self, p: Player, text: str, kind: str = "private", target: int | None = None, **data: Any) -> Event:
        return self.emit(kind, text, target=target, to=frozenset({p.seat}), key=True, **data)

    def observe(self, kind: str, text: str = "", actor: int | None = None, **data: Any) -> Event:
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
        v = obj.get(field) if field else None
        if is_skip(v):
            return None
        return match_name(v, options if options is not None else req.options)

    def apply_common(self, p: Player, obj: dict[str, Any]) -> None:
        thought = clean_speech(obj.get("thought"), 400)
        if thought:
            self.observe("thought", thought, actor=p.seat)
        edits, _ = read_ledger(obj.get("ledger"), list(p.ledger), self.guess_options())
        for ed in edits:
            row = p.ledger[ed["name"]]
            old = {"suspicion": row.suspicion, "guess": row.guess, "note": row.note}
            row.suspicion = ed.get("suspicion", row.suspicion)
            row.guess = ed.get("guess", row.guess)
            row.note = ed.get("note", row.note)
            new = {"suspicion": row.suspicion, "guess": row.guess, "note": row.note}
            if new != old:
                self.observe("ledger", ed["name"], actor=p.seat, name=ed["name"], old=old, new=new)
        ops = read_notes(obj.get("notes"))
        for nid in ops["delete"]:
            n = p.notebook.delete(nid)
            if n:
                self.observe("note", n.text, actor=p.seat, op="delete", id=nid)
        for nid, text in ops["edit"]:
            n = p.notebook.edit(nid, text)
            if n:
                self.observe("note", n.text, actor=p.seat, op="edit", id=nid)
        for text in ops["add"]:
            n = p.notebook.add(text)
            if n:
                self.observe("note", n.text, actor=p.seat, op="add", id=n.id)

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
        self.observe("start", "게임을 시작합니다", roster=[self.seat_info(p) for p in self.players])
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
                self.result = self.make_result(MAFIA, f"{night}번째 밤이 지나도록 끝나지 않아 마피아 팀이 이겼습니다")
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

    def kill(self, q: Player, text: str, cause: str, ctx: NightContext | None = None) -> None:
        q.alive = False
        q.died_day = ctx.night if ctx is not None else self.day  # a night death belongs to that night's date
        role = f" {q.name}님은 {josa(q.role, '이었습니다', '였습니다')}." if self.setup.reveal else ""
        self.emit("death", text + role, target=q.seat, key=True, cause=cause, role=q.role, sound="death")
        ability_of(q.role).on_death(self, q, cause, ctx)

    def set_role(self, p: Player, role: str, text: str) -> None:
        """p's role changes (도굴꾼, 역할 바꾸기): p alone is told, the observer sees it."""
        old, p.role = p.role, role
        self.private(p, text, role=role)
        self.emit("role", f"{p.name}님의 직업이 {old}에서 {role}(으)로 바뀌었습니다.", target=p.seat, to=frozenset({p.seat}),
                  log=False, old=old, role=role)  # the screens of the observer and that player only

    def revive(self, q: Player, text: str, ctx: NightContext | None = None) -> None:
        """A dead player comes back (성직자, 과학자): announced in the morning, or at once by day."""
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
        alive = self.alive()
        if not alive:
            self.result = self.make_result(None, "모두 죽었습니다")
            return
        mafia = [p for p in alive if in_mafia_team(p)]
        held = any(ability_of(p.role).holds_game(self, p) for p in alive)
        if mafia and len(mafia) >= len(alive) - len(mafia) and not held:
            self.result = self.make_result(MAFIA, "마피아 팀 수가 시민 팀 수와 같아졌습니다")
        elif not mafia and not held:
            self.result = self.make_result(TOWN, "마피아 팀이 모두 죽었습니다")

    def make_result(self, team: str | None, reason: str) -> dict[str, Any]:
        winners = set() if team is None else {p.seat for p in self.players if team_of(p.role) == team}
        label = "무승부" if team is None else f"{TEAM_LABEL[team]} 승리"
        return {"team": team, "label": label, "reason": reason, "winners": sorted(winners), "day": self.day}

    def finish(self) -> None:
        self.phase, self.step = "end", ""
        r = self.result or self.make_result(None, "게임이 중단되었습니다")
        self.result = r
        self.emit("end", f"{r['label']}. {r['reason']}.", key=True, result=r, sound="win" if r["team"] else "lose",
                  roles={p.seat: p.role for p in self.players})

    def seat_info(self, p: Player) -> dict[str, Any]:
        return {"seat": p.seat, "name": p.name, "role": p.role, "kind": p.kind, "model_key": p.model_key,
                "model_name": p.model_name, "shown": p.shown.line()}

    # ---- god powers and the human moderator (called inside the loop) ---------------------------------
    def god(self, power: str, seat: int | None = None, text: str = "", role: str | None = None, by: str = "신") -> None:
        q = self.players[seat] if seat is not None else None
        if power == "공지" and text:
            self.emit("moderator" if by == "사회자" else "god", text, key=True, power="공지", by=by, sound="god")
        elif power == "계시" and q and text:
            self.emit("god", text, target=q.seat, to=frozenset({q.seat}), key=True, power="계시", sound="god")
        elif power == "천벌" and q and q.alive:
            self.emit("god", "하늘에서 벼락이 떨어졌습니다.", target=q.seat, key=True, power="천벌", sound="god")
            self.kill(q, f"신의 천벌로 {q.name}님이 죽었습니다.", "god")
        elif power == "부활" and q and not q.alive:
            q.alive = True
            self.emit("god", f"신의 뜻으로 {q.name}님이 살아 돌아왔습니다.", target=q.seat, key=True, power="부활", sound="god")
        elif power == "역할 바꾸기" and q and role in ROLES:
            old, q.role = q.role, role
            self.observe("god", f"{q.name}님의 역할을 {old}에서 {role}(으)로 바꿨습니다.", target=q.seat, power="역할 바꾸기", role=role, sound="god")
            self.private(q, f"신이 네 역할을 {role}(으)로 바꿨다. 이제 너는 {josa(role, '이다', '다')}.", kind="god", power="계시")
        elif power == "보호" and q:
            self.god_protect.add(q.name)
            self.observe("god", f"오늘 밤 {q.name}님을 향한 공격은 모두 막힙니다.", target=q.seat, power="보호", sound="god")
        elif power == "침묵" and q:
            q.silenced_day = self.day + 1 if self.phase == "night" else self.day
            self.observe("god", f"{q.name}님은 {q.silenced_day}번째 낮에 말할 수 없습니다.", target=q.seat, power="침묵", sound="god")
        elif power == "다음 단계로":
            self.skip = True
            self.end_day()
            self.observe("god", "다음 단계로 넘어갑니다.", power="다음 단계로", sound="god")
        elif power == "일시정지":
            self.set_paused(not self.paused)

    def stop(self) -> None:
        """The user stopped the game: it ends where it stands and the record stays 중단됨 (no result line)."""
        if self.result is None:
            self.result = {"team": None, "label": "중단됨", "reason": "게임을 멈췄습니다", "winners": [], "day": self.day,
                           "stopped": True}
        self.set_paused(False)

    def set_paused(self, paused: bool) -> None:
        self.paused = paused
        if self._resume is not None:
            self._resume.clear() if paused else self._resume.set()
        self.observe("pause", "일시정지" if paused else "다시 진행", paused=paused)

    def end_day(self) -> None:
        """사람 사회자 ends the discussion (투표로)."""
        if self._end_day is not None:
            self._end_day.set()

    def post(self, fn: Callable[..., None], *args: Any, **kw: Any) -> None:
        """Thread-safe: run fn(*args, **kw) inside the game loop."""
        if self.loop is not None and not self.loop.is_closed():  # a finished game ignores late clicks
            self.loop.call_soon_threadsafe(lambda: fn(*args, **kw))
