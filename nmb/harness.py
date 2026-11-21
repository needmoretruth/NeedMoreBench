"""Who answers for a seat: a model through a route, a person through the app, or a script.

The model controller builds the prompt, calls the route, reads the JSON, and asks once more with the reason
when the answer is unusable. Route errors get at most two retries (paid calls are capped); after
that the seat does nothing this turn and the game goes on.
"""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Callable

from .engine.parse import first_json_object, is_skip, match_name
from .engine.prompts import build_prompt, log_lines
from .engine.state import Player
from .engine.turn import TurnRequest
from .i18n import _
from .providers.base import Completion, ModelRef, ProviderError, Route, estimate_tokens
from .providers.health import KEPT, classify, words
from .providers.merge import route_name

if TYPE_CHECKING:
    from .engine.game import Game
    from .providers.registry import Routes


def route_word(routes: "Routes", ref: ModelRef) -> str:
    from .providers.base import ModelInfo
    return route_name(routes.info(ref.key) or ModelInfo(ref, ref.id))

MAX_RETRIES = 2
COMPACT_RESERVE = 8000  # room for the answer and the next few lines


def problem_with(obj: dict[str, Any] | None, req: TurnRequest) -> str | None:
    if obj is None:
        return "JSON 객체를 찾지 못했다"
    if req.field:
        v = obj.get(req.field)
        if v is None and not req.skip_word:
            return f"{req.field} 값이 없다"
        if v is not None and not (req.skip_word and is_skip(v)) and match_name(v, req.options) is None:
            return f"{req.field} 값 「{v}」은(는) 고를 수 있는 것이 아니다"
    return None


class AIController:
    """`routes` (when given) learns from every failure and offers the same model through the next route
    when this one runs out: a used-up quota, a refusal, or retries spent on a passing failure."""

    def __init__(self, route: Route, ref: ModelRef, max_tokens: int = 1200, routes: "Routes | None" = None):
        self.route = route
        self.ref = ref
        self.max_tokens = max_tokens
        self.routes = routes

    def _next_route(self) -> ModelRef | None:
        if self.routes is None:
            return None
        for key in self.routes.others(self.ref.key):
            ref = ModelRef.parse(self.routes.with_effort(key, self.ref.variant))
            if ref.route in self.routes.routes:
                return ref
        return None

    async def call(self, game: "Game", p: Player, system: str, user: str, max_tokens: int | None = None) -> Completion:
        attempt, tried = 0, []
        while True:
            try:
                comp = await asyncio.wait_for(self.route.complete(self.ref, system, user, max_tokens or self.max_tokens),
                                              game.setup.call_timeout)
                if self.routes is not None:
                    self.routes.health.ok(self.ref.key)
                return comp
            except asyncio.TimeoutError:  # the time limit ends this call; the safe default applies, no retry
                e = ProviderError("timeout", f"{game.setup.call_timeout:g}초 안에 답하지 않았다")
                game.record_error(p, e, attempt, words(p.name, classify(e)) + ". " + _("The default action applies"),
                                  attempts=tried + ["timeout"])
                raise e from None
            except ProviderError as e:
                routes = self.routes
                info = routes.info(self.ref.key) if routes is not None else None
                problem = routes.health.learn(self.ref.key, e) if routes is not None else classify(e)
                tried.append(e.reason)
                if attempt < MAX_RETRIES and problem.kind not in KEPT and e.retryable and (e.retry_after or 0) <= 30:
                    game.record_error(p, e, attempt)
                    attempt += 1
                    await asyncio.sleep(min(30.0, e.retry_after or (2.0 + 3.0 * attempt)))
                    continue
                said = words(p.name, problem, self.ref.route)
                nxt = self._next_route() if e.reason != "declined" else None  # a refusal is never asked again
                if routes is not None and nxt is not None:  # the same entrant through the next route
                    game.record_error(p, e, attempt)
                    old = self.ref
                    self.route, self.ref, attempt = routes.route(nxt), nxt, 0
                    game.observe("route", said + ". " + _("Using {route} from now on").format(route=route_word(routes, nxt)),
                                 actor=p.seat, old=old.key, new=nxt.key, reason=e.reason, message=str(e)[:300])
                    continue
                game.record_error(p, e, attempt, said + ". " + _("The default action applies"), attempts=tried,
                                  free=bool(info and info.free))
                raise e from None

    def compact_point(self, game: "Game", p: Player) -> int:
        """256K by default, lower when set for the game or the seat, and never past the model's own input limit."""
        spec = game.setup.seats[p.seat] if p.seat < len(game.setup.seats) else None
        point = (spec.compact_at if spec and spec.compact_at else None) or game.setup.compact_at
        info_of = getattr(self.route, "info", None)
        info = info_of(self.ref) if callable(info_of) else None
        context = getattr(info, "context", 0) or 0
        if context:
            point = min(point, context - self.max_tokens - COMPACT_RESERVE)
        return max(2000, point)

    async def compact(self, game: "Game", p: Player, system: str) -> None:
        """the model writes its own memory of the oldest half of what it has not summarised yet; if that
        fails the engine collapses that part into its key events. Recorded as a compaction event."""
        lines = [(i, line) for i, line in log_lines(game, p) if i > p.memory_upto]
        if len(lines) < 4:
            return
        cut = lines[len(lines) // 2 - 1][0]
        old = "\n".join(line for i, line in lines if i <= cut)
        before = p.memory
        req = TurnRequest("compaction", "기억 정리")
        user = ("기억 정리: 기록이 길어져서 오래된 부분을 네 기억으로 줄인다. 아래 기록(과 앞서 정리한 기억)을 네가 나중에 읽을 메모로 "
                "요약한다. 누가 무엇을 말하고 했는지, 네가 알게 된 사실, 네 판단을 남긴다. 이 메모가 그 기록을 대신한다.\n\n"
                + (f"앞서 정리한 기억\n{before}\n\n" if before else "") + f"줄일 기록\n{old}\n\n"
                "답 형식: JSON 객체 하나 {\"memory\": \"메모\"}. 앞뒤에 다른 글을 쓰지 않는다.")
        memory, by = "", "model"
        try:
            comp = await self.call(game, p, system, user, max_tokens=4000)
            got = first_json_object(comp.text)
            memory = str((got or {}).get("memory") or "").strip()
            game.record_call(p, req, self.ref.key, comp, system, user, None if memory else "memory가 없다")
        except ProviderError:
            memory = ""
        if not memory:
            by = "engine"
            keyed = {e.id for e in game.events if e.key}
            memory = "\n".join(filter(None, [before] + [line for i, line in lines if i <= cut and i in keyed]))
        p.memory, p.memory_upto = memory, cut
        game.observe("compaction", memory, actor=p.seat, upto=cut, by=by, lines=sum(1 for i, _ in lines if i <= cut))

    async def decide(self, game: "Game", p: Player, req: TurnRequest) -> dict[str, Any]:
        error: str | None = None
        obj: dict[str, Any] | None = None
        system, user = build_prompt(game, p, req)
        if estimate_tokens(system + user) > self.compact_point(game, p):
            await self.compact(game, p, system)
        for _ in range(2):
            system, user = build_prompt(game, p, req, error)
            try:
                comp = await self.call(game, p, system, user)
            except ProviderError:
                return {}
            obj = first_json_object(comp.text)
            error = problem_with(obj, req)
            game.record_call(p, req, self.ref.key, comp, system, user, error)
            if error is None:
                return obj or {}
        return obj or {}


class HumanController:
    """The person's seat: the app shows the request, the person answers, the app posts the answer."""

    def __init__(self) -> None:
        self.pending: asyncio.Future[dict[str, Any]] | None = None
        self.request: TurnRequest | None = None

    async def decide(self, game: "Game", p: Player, req: TurnRequest) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        self.pending = loop.create_future()
        self.request = req
        game.emit("human_turn", log=False, to=frozenset({p.seat}), request=req.to_json())
        try:
            return await self.pending
        finally:
            self.pending = None
            self.request = None

    def answer(self, obj: dict[str, Any]) -> None:
        if self.pending is not None and not self.pending.done():
            self.pending.set_result(obj)


class ScriptedController:
    """Answers from a function (tests): fn(game, player, request) → answer dict."""

    def __init__(self, fn: Callable[["Game", Player, TurnRequest], dict[str, Any]]):
        self.fn = fn

    async def decide(self, game: "Game", p: Player, req: TurnRequest) -> dict[str, Any]:
        await asyncio.sleep(0)
        return self.fn(game, p, req)


LINES = ["{t}님 아까 말이 좀 앞뒤가 안 맞았어요.", "저는 {t}님이 제일 수상해요.", "{t}님은 왜 아까부터 조용하세요?",
         "어제 투표 흐름 보면 {t}님 쪽이 이상해요.", "{t}님 믿어도 될 것 같아요."]


class RandomController:
    """Legal random answers with short lines: for tests and the offline demo, never a benchmark."""

    def __init__(self, seed: int | None = None, quiet: float = 0.2):
        self.rng = random.Random(seed)
        self.quiet = quiet

    async def decide(self, game: "Game", p: Player, req: TurnRequest) -> dict[str, Any]:
        await asyncio.sleep(0)
        r = self.rng
        others = [q.name for q in game.alive() if q is not p]
        t = r.choice(others) if others else p.name
        obj: dict[str, Any] = {"thought": f"{t}님을 지켜본다."}
        if req.say:
            obj["say"] = "" if r.random() < self.quiet and req.kind == "discuss" else r.choice(LINES).format(t=t)
        if req.field:
            pool = req.options + ([req.skip_word] if req.skip_word and r.random() < 0.15 else [])
            obj[req.field] = r.choice(pool) if pool else None
        if req.hand:
            obj["hand"] = r.randint(0, 3)
        if req.time and r.random() < 0.1:
            obj["time"] = r.choice(["연장", "단축"])
        if req.poll:
            obj["poll"] = t
        if req.whispers and others and r.random() < 0.2:
            obj["whispers"] = [{"to": t, "text": "우리 둘은 서로 믿어 봐요."}]
        if p.ledger:
            name = r.choice(list(p.ledger))
            obj["ledger"] = [{"name": name, "suspicion": r.randint(0, 100), "guess": "모름", "note": "느낌"}]
        if r.random() < 0.2:
            obj["notes"] = {"add": [f"{game.day}번째 낮: {t}님 확인"]}
        return obj
