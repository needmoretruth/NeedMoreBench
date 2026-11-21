"""마피아 보조, the rest of the full pool: 마녀, 불사신, 위장꾼, 암살자, 대부.

Like the classic helpers they do not know the mafia until they contact them (base.contact), and the 경찰 sees
them as 마피아 아님.
"""
from __future__ import annotations

from ..parse import is_skip
from ..roles import TOWN
from ..text import T
from ..turn import TurnRequest
from .base import Ability, Attack, NightContext, announce, contact, register, side, target_names


def is_mafia(q) -> bool:  # noqa: ANN001
    return q.role == "마피아"


@register
class Witch(Ability):
    """Curses one player a night: a frog has no role ability, and no trait, until the next night falls."""
    key = "witch"
    act_text, pass_text = "{t}님에게 저주를 겁니다", "아무에게도 저주를 걸지 않았습니다"
    priority = 60  # after tonight's abilities: the frog loses the coming day
    helper = True

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 개구리로 만들 사람 한 명을 고른다. 그 사람은 다음 밤이 올 때까지 직업 능력이 없다. "
                                      "고른 사람이 마피아면 개구리로 만들지 않고 접선한다."),
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx: NightContext):
        q = game.by_name(target) if target else None
        if q is None or not q.alive or ctx.dying(q.name):
            return
        ctx.used_on[p.seat] = q.name
        if is_mafia(q):
            contact(game, p)
            return
        q.state["frog"] = True
        game.private(p, T("{name}님을 개구리로 만들었다. 다음 밤이 올 때까지 그 사람은 직업 능력이 없다.", name=q.name), target=q.seat)
        game.private(q, T("마녀의 저주로 개구리가 되었다. 다음 밤이 올 때까지 직업 능력이 없다."))
        game.observe("frog", T("마녀 {by}님이 {name}님을 개구리로 만들었습니다.", by=p.name, name=q.name), actor=p.seat, target=q.seat)


@register
class Undying(Ability):
    """Dies, contacts the mafia, and comes back once when the next night ends (everyone learns it)."""
    key = "undying"
    helper = True

    def on_death(self, game, p, cause, ctx):
        if p.state.get("risen"):
            return
        contact(game, p)
        p.state["rise_at"] = ctx.night + 1 if ctx is not None else game.day  # an execution by day: tonight

    def while_dead(self, game, p, ctx):
        at = p.state.get("rise_at")
        if at is None or ctx.night < at or p.at_rest:
            return
        p.state.pop("rise_at")
        p.state["risen"] = True
        game.revive(p, T("불사신 {name}님이 되살아났습니다.", name=p.name), ctx)
        p.revealed = True
        game.private(p, T("되살아났다. 다시 죽으면 돌아오지 못한다."))

    def status(self, p):
        if p.state.get("risen"):
            return T("한 번 되살아났다. 다시 죽으면 돌아오지 못한다.")
        return T("죽으면 다음 밤이 끝날 때 한 번 되살아난다.")


@register
class Masquerader(Ability):
    """Knows one citizen's role from the start and poses as it; survives its first execution and contacts, and
    contacts when that citizen is executed."""
    key = "masquerader"
    helper = True

    def on_start(self, game, p):
        town = [q for q in game.players if q is not p and side(q) == TOWN]
        if not town:
            return
        q = game.rng.choice(town)
        p.state["cover"] = q.name
        game.private(p, T("{name}님의 직업은 {role:이다/다}. 너는 이 직업인 척할 수 있다.", name=q.name, role=q.role),
                     target=q.seat, result=q.role, knows=[q.seat])

    def spare(self, game, p, cand):
        if cand is p and not p.state.get("spared"):
            p.state["spared"] = True
            contact(game, p)
            game.system(T("{name}님은 처형되지 않았습니다.", name=cand.name), target=cand.seat)
            game.observe("spare", T("위장꾼 {name}님이 처형을 한 번 피했습니다.", name=p.name), actor=p.seat)
            return True
        if cand.name == p.state.get("cover"):
            contact(game, p)
        return False

    def status(self, p):
        cover = p.state.get("cover")
        line = T("투표로 처형될 때 한 번 살아남는다.") if not p.state.get("spared") else T("처형을 이미 한 번 피했다.")
        return T("{line} 네가 직업을 아는 시민: {name}님.", line=line, name=cover) if cover else line


@register
class Assassin(Ability):
    """From the second night writes two players and their roles; both right kills both. Naming a 마피아 contacts."""
    key = "assassin"
    act_text, pass_text = "{t}님을 노립니다", "아무도 노리지 않았습니다"
    priority = 30
    helper = True

    def night_request(self, game, p):
        if game.day < 2:
            return None
        return TurnRequest("night", T("밤이다. 두 사람과 그 직업을 맞히면 둘 다 죽인다. 먼저 한 사람과 그 직업을 적는다. "
                                      "적은 사람이 마피아면 죽이지 않고 접선한다. 쓰지 않으려면 {none}.", none="없음"),
                           field="target", options=target_names(game, p), skip_word="없음",
                           extra_field="role", extra_options=self._roles(game),
                           extra_task=T("role: 그 사람의 직업이라고 보는 것."))

    @staticmethod
    def _roles(game) -> list[str]:  # noqa: ANN001
        return [r for r in game.guess_options() if r != "모름"]

    async def act(self, game, p, target, ctx: NightContext):
        a = game.by_name(target) if target else None
        if a is None:
            return
        first_role = self._role(game, ctx.answers.get(p.seat, {}).get("role"))
        opts = [n for n in target_names(game, p) if n != a.name]
        req = TurnRequest("night", T("두 번째 사람과 그 직업을 적는다."), field="target", options=opts, skip_word="없음",
                          extra_field="role", extra_options=self._roles(game), extra_task=T("role: 그 사람의 직업이라고 보는 것."))
        obj = await game.ask(p, req) if opts else {}
        b = game.by_name(game.pick(obj, req)) if opts else None
        second_role = self._role(game, obj.get("role"))
        announce(game, p, T("{a}님({ra}), {b}님({rb}) 두 사람을 노립니다", a=a.name, ra=first_role or "모름",
                            b=b.name if b else "없음", rb=second_role or "모름"), a)
        if is_mafia(a) or (b is not None and is_mafia(b)):
            contact(game, p)
            return
        if b is None or first_role != a.role or second_role != b.role:
            game.private(p, T("둘 다 맞히지 못해 아무도 죽이지 않았다."))
            return
        game.private(p, T("둘 다 맞혔다. {a}님과 {b}님을 죽인다.", a=a.name, b=b.name), knows=[a.seat, b.seat])
        ctx.attacks += [Attack("hitman", a.name, attacker=p.seat), Attack("hitman", b.name, attacker=p.seat)]

    @staticmethod
    def _role(game, raw) -> str | None:  # noqa: ANN001
        if raw is None or is_skip(str(raw)):
            return None
        return game.pick({"role": str(raw)}, TurnRequest("night", ""), "role", Assassin._roles(game))

    def status(self, p):
        return T("두 번째 밤부터 두 사람과 그 직업을 맞혀 죽일 수 있다.")


@register
class Godfather(Ability):
    """Contacts the mafia on the third night; from then on it chooses the kill with them and the mafia attack
    ignores the 의사 and the target's traits."""
    key = "godfather"
    helper = True

    def nightfall(self, game, p, ctx):
        if not p.contacted and game.day >= 3:
            contact(game, p)

    def is_killer(self, game, p):
        return p.contacted

    def pierce(self, game, p):
        return p.contacted

    def status(self, p):
        if p.contacted:
            return T("마피아와 접선했다. 마피아의 공격은 의사의 치료와 직업 특성을 무시한다.")
        return T("세 번째 밤에 마피아와 접선한다.")
