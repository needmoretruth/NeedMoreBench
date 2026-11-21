"""Who answers for a seat: a model through a route, a person through the app, or a script.

The model controller builds the prompt, calls the route, reads the JSON, and asks once more with the reason
when the answer is unusable. Route errors get at most two retries (paid calls are capped); after
that the seat does nothing this turn and the game goes on.
"""
from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING, Any, Callable

from .engine.parse import first_json_object, is_skip, match_name, read_notes
from .engine.prompts import build_prompt, log_lines
from .engine.state import NOTE_PAGE, Player
from .engine.text import Msg, T, from_word, say
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


def problem_with(obj: dict[str, Any] | None, req: TurnRequest, lang: str = "ko") -> Msg | None:
    """Why the answer cannot be used, as a message the retry prompt renders in the game's language."""
    if obj is None:
        return T("JSON 객체를 찾지 못했다")
    page = read_notes(obj.get("notes"))
    if page is not None and len(page) > NOTE_PAGE:  # sent back once; a second long page is not kept
        return T("notes가 {n}자다. {max}자 이하로 줄여라", n=len(page), max=f"{NOTE_PAGE:,}")
    if req.field:
        raw = obj.get(req.field)
        v = from_word(lang, raw)  # 'Yes' in an English game is 찬성
        if v is None and not req.skip_word:
            return T("{field} 값이 없다", field=req.field)
        if v is not None and not (req.skip_word and is_skip(v)) and match_name(v, req.options) is None:
            return T("{field} 값 {v:은/는} 고를 수 있는 것이 아니다", field=req.field, v=T("「{x}」", x=str(raw)))
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
        req = TurnRequest("compaction", T("기억 정리"))
        t = game.t
        user = (t(T("기억 정리: 기록이 길어져서 오래된 부분을 네 기억으로 줄인다. 아래 기록(과 앞서 정리한 기억)을 네가 나중에 읽을 메모로 "
                    "요약한다. 누가 무엇을 말하고 했는지, 네가 알게 된 사실, 네 판단을 남긴다. 이 메모가 그 기록을 대신한다.")) + "\n\n"
                + (t(T("앞서 정리한 기억")) + f"\n{before}\n\n" if before else "") + t(T("줄일 기록")) + f"\n{old}\n\n"
                + t(T("답 형식: JSON 객체 하나 {shape}. 앞뒤에 다른 글을 쓰지 않는다.",
                      shape='{"memory": "' + t(T("메모")) + '"}')))
        memory, by = "", "model"
        try:
            comp = await self.call(game, p, system, user, max_tokens=4000)
            got = first_json_object(comp.text)
            memory = str((got or {}).get("memory") or "").strip()
            game.record_call(p, req, self.ref.key, comp, system, user, None if memory else t(T("memory가 없다")))
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
            problem = problem_with(obj, req, game.lang)
            error = game.t(problem) if problem else None
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
        """A request with a time limit (a discussion turn) passes when the time runs out; the card goes
        away whenever the turn ends, answered, timed out or cut short."""
        loop = asyncio.get_running_loop()
        pending: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.pending, self.request = pending, req
        game.emit("human_turn", log=False, to=frozenset({p.seat}), request=req.to_json(game.lang))
        try:
            if req.limit > 0:
                try:
                    return await asyncio.wait_for(pending, req.limit)
                except asyncio.TimeoutError:
                    return {}
            return await pending
        finally:
            if self.pending is pending:
                self.pending, self.request = None, None
            game.observe("human_done", "", actor=p.seat)

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


LINES = {"ko": ["{t}님 아까 말이 좀 앞뒤가 안 맞았어요.", "저는 {t}님이 제일 수상해요.", "{t}님은 왜 아까부터 조용하세요?",
                "어제 투표 흐름 보면 {t}님 쪽이 이상해요.", "{t}님 믿어도 될 것 같아요."],
         "en": ["{t}, what you said earlier didn't add up.", "I find {t} the most suspicious.", "{t}, why so quiet all this time?",
                "Looking at yesterday's vote, something is off about {t}.", "I think we can trust {t}."]}
DEMO = {"ko": ("{t}님을 지켜본다.", "우리 둘은 서로 믿어 봐요.", "느낌", "{d}번째 낮: {t}님 확인"),
        "en": ("Keeping an eye on {t}.", "Let's trust each other, the two of us.", "a hunch", "Day {d}: check {t}")}


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
        lang = game.lang
        thought, whisper, hunch, note = DEMO[lang]
        obj: dict[str, Any] = {"thought": thought.format(t=t)}
        if req.say:
            obj["say"] = "" if r.random() < self.quiet and req.kind == "discuss" else r.choice(LINES[lang]).format(t=t)
        if req.field:  # answered in the game's language, as a model would ('Yes' in an English game)
            pool = req.options + ([req.skip_word] if req.skip_word and r.random() < 0.15 else [])
            obj[req.field] = say(lang, r.choice(pool)) if pool else None
        if req.extra_field and req.extra_options:  # a role's second choice (모방자, 폭탄마, 도청꾼)
            obj[req.extra_field] = say(lang, r.choice(req.extra_options))
        if req.hand:
            obj["hand"] = r.randint(0, 3)
        if req.time and r.random() < 0.1:
            obj["time"] = say(lang, r.choice(["연장", "단축"]))
        if req.poll:
            obj["poll"] = t
        if req.whispers and others and r.random() < 0.2:
            obj["whispers"] = [{"to": t, "text": whisper}]
        if p.ledger:
            name = r.choice(list(p.ledger))
            obj["ledger"] = [{"name": name, "suspicion": r.randint(0, 100), "guess": say(lang, "모름"), "note": hunch}]
        if r.random() < 0.2:
            obj["notes"] = (p.notebook.page + "\n" if p.notebook.page else "") + note.format(d=game.day, t=t)
            if len(obj["notes"]) > NOTE_PAGE:
                obj["notes"] = obj["notes"][-NOTE_PAGE:]
        return obj
