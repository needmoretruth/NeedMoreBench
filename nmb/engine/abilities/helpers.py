"""마피아 보조, classic pool: 스파이, 야수, 유혹자, 모방자.

A helper does not know the mafia until it contacts them (base.contact); until then it votes and counts as a
citizen. 경찰 sees every helper as 마피아 아님 (only the 마피아 role looks like mafia), as in the source.
"""
from __future__ import annotations

from ..parse import is_skip
from ..text import T
from ..turn import TurnRequest
from .base import Ability, NightContext, ability_of, announce, choose_text, contact, mafia_alive, register, target_names


def is_mafia(q) -> bool:  # noqa: ANN001
    return q.role == "마피아"


@register
class Spy(Ability):
    key = "spy"
    act_text, pass_text = "{t}님의 직업을 알아봅니다", "아무도 알아보지 않았습니다"
    priority = 40
    helper = True

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 직업을 알아낼 사람 한 명을 고른다. 고른 사람이 마피아면 접선하고 한 번 더 조사한다."),
                           field="target", options=target_names(game, p))

    async def act(self, game, p, target, ctx: NightContext):
        q = game.by_name(target) if target else None
        if q is None:
            return
        self.learn(game, p, q, ctx)
        if is_mafia(q) and not p.contacted:
            contact(game, p)
            again = [n for n in target_names(game, p) if n != q.name]
            if again:
                req = TurnRequest("night", T("접선했다. 한 명을 더 조사할 수 있다."), field="target", options=again)
                r = game.by_name(game.pick(await game.ask(p, req), req))
                announce(game, p, choose_text(self, game, r.name if r else None), r)
                if r is not None:
                    self.learn(game, p, r, ctx)

    @staticmethod
    def learn(game, p, q, ctx: NightContext) -> None:  # noqa: ANN001
        ctx.used_on[p.seat] = q.name
        game.private(p, T("조사 결과: {name}님의 직업은 {role}입니다.", name=q.name, role=q.role), target=q.seat,
                     result=q.role, knows=[q.seat])
        if q.role == "방패병":  # a mafia-team check on the soldier shows the checker to it
            game.private(q, T("{name}님이 너를 조사했다. {name}님은 마피아 팀이다.", name=p.name), target=p.seat)


@register
class Beast(Ability):
    key = "beast"
    act_text, pass_text = "{t}님을 찍습니다", "아무도 찍지 않았습니다"
    priority = 10
    helper = True

    def night_request(self, game, p):
        if p.contacted:
            return None
        return TurnRequest("night", T("밤이다. 한 명을 찍는다. 찍은 사람이 마피아에게 죽으면 너는 길들여져 마피아와 접선한다."),
                           field="target", options=target_names(game, p))

    async def act(self, game, p, target, ctx: NightContext):
        if target:
            p.state["mark"] = target
            ctx.used_on[p.seat] = target

    def on_attack(self, game, p, attack, ctx):
        return "silent" if attack.source == "mafia" else "die"  # the mafia cannot kill it

    def is_killer(self, game, p):
        return p.contacted

    def morning(self, game, p, ctx: NightContext):
        mark = p.state.pop("mark", None)
        if not p.contacted and mark and (mark, "mafia") in ctx.deaths:
            contact(game, p)

    def status(self, p):
        return T("길들여져 마피아와 접선했다. 마피아 회의에서 죽일 사람을 같이 고른다.") if p.contacted else None


@register
class Seducer(Ability):
    key = "seducer"
    helper = True

    def after_vote(self, game, p, vote, extra):
        q = game.by_name(vote)
        if q is None or q is p or not q.alive:
            announce(game, p, T("아무도 유혹하지 않았습니다"))
            return
        announce(game, p, T("투표로 {name}님을 유혹합니다", name=q.name), q)
        game.private(p, T("투표로 {name}님을 유혹했다.", name=q.name), target=q.seat)
        if is_mafia(q):
            contact(game, p)
            return
        game.blocked_next.add(q.name)
        q.silenced_day = game.day + 1
        game.private(q, T("유혹자에게 유혹당했다. 오늘 밤 능력을 쓸 수 없고 {n}번째 낮에는 말할 수 없다.", n=game.day + 1))
        game.observe("seduce", T("유혹자 {by}님이 {name}님을 유혹했습니다.", by=p.name, name=q.name), actor=p.seat, target=q.seat)

    def status(self, p):
        return T("낮 투표에서 네가 표를 준 사람이 유혹당한다.")


@register
class Copycat(Ability):
    key = "copycat"
    helper = True

    def vote_extra(self, game, p):
        opts = target_names(game, p)
        return TurnRequest("vote", "", extra_field="steal", extra_options=opts,
                           extra_task=T("steal: 능력을 따라 할 사람 한 명(오늘 밤 그 직업의 능력을 쓴다). 따라 하지 않으려면 \"{none}\".",
                                        none="없음"))

    def after_vote(self, game, p, vote, extra):
        q = game.by_name(str(extra)) if extra and not is_skip(extra) else None
        if q is None or q is p or not q.alive:
            announce(game, p, T("아무 능력도 따라 하지 않았습니다"))
            return
        announce(game, p, T("{name}님의 능력을 따라 합니다", name=q.name), q)
        p.state["stolen"] = q.role
        game.private(p, T("{name}님의 능력을 따라 했다. {name}님은 {role:이다/다}. 오늘 밤 그 능력을 쓴다.", name=q.name, role=q.role),
                     target=q.seat, knows=[q.seat])
        if is_mafia(q) and not p.contacted:
            contact(game, p)

    def _stolen(self, p) -> Ability | None:  # noqa: ANN001
        role = p.state.get("stolen")
        return ability_of(role) if role and role != "모방자" else None

    def acting(self, p):
        return self._stolen(p) or self

    def priority_for(self, p):
        ab = self._stolen(p)
        return ab.priority_for(p) if ab is not None else self.priority

    def night_request(self, game, p):
        ab = self._stolen(p)
        return ab.night_request(game, p) if ab is not None else None

    async def act(self, game, p, target, ctx):
        ab = self._stolen(p)
        p.state.pop("stolen", None)
        if ab is not None:
            await ab.act(game, p, target, ctx)

    def is_killer(self, game, p):
        return p.contacted and not mafia_alive(game)

    def status(self, p):
        role = p.state.get("stolen")
        return T("오늘 밤 따라 한 {role} 능력을 쓴다.", role=role) if role else T("투표 때 한 사람의 능력을 따라 할 수 있다.")
