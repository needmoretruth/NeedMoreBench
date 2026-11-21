"""시민 팀, the rest of the full pool, part one: 자경단원, 정보원, 연락관 (경찰 계열), 기수, 배심장,
조수, 환술사, 도청꾼."""
from __future__ import annotations

from ..parse import is_skip
from ..roles import TOWN
from ..text import T
from ..turn import TurnRequest
from .base import Ability, Attack, NightContext, ability_of, announce, learned, register, side, target_names, tied


def picked(game, extra):  # noqa: ANN001, ANN201
    """The living player a day extra names, or None."""
    q = game.by_name(str(extra)) if extra and not is_skip(str(extra)) else None
    return q if q is not None and q.alive else None


@register
class Vigilante(Ability):
    """Once a game, at the day vote, checks whether one player is mafia; a mafia found it may kill at a later night."""
    key = "vigilante"
    act_text, pass_text = "{t}님을 처단합니다", "처단을 미뤘습니다"
    priority = 30

    def vote_extra(self, game, p):
        if p.state.get("checked"):
            return None
        return TurnRequest("vote", "", extra_field="check", extra_options=target_names(game, p),
                           extra_task=T("check: 마피아인지 알아볼 사람(게임에서 한 번). 마피아면 그 뒤 밤에 죽일 수 있다. 아끼려면 \"{none}\".",
                                        none="없음"))

    def after_vote(self, game, p, vote, extra):
        q = picked(game, extra)
        if q is None or q is p:
            return
        p.state["checked"] = True
        announce(game, p, T("{name}님이 마피아인지 알아봅니다", name=q.name), q)
        if ability_of(q.role).looks_mafia(q):
            p.state["hunt"] = q.name
            game.private(p, T("조사 결과: {name}님은 마피아입니다. 밤에 처단할 수 있다.", name=q.name), target=q.seat, result="마피아입니다")
        else:
            game.private(p, T("조사 결과: {name}님은 마피아가 아닙니다.", name=q.name), target=q.seat, result="마피아가 아닙니다")

    def night_request(self, game, p):
        q = game.by_name(p.state.get("hunt"))
        if q is None or not q.alive:
            return None
        return TurnRequest("night", T("밤이다. 마피아로 밝혀낸 {name}님을 처단할 수 있다. 미루려면 {none}.", name=q.name, none="없음"),
                           field="target", options=[q.name], skip_word="없음")

    async def act(self, game, p, target, ctx: NightContext):
        if target and target == p.state.get("hunt"):
            p.state.pop("hunt")
            ctx.attacks.append(Attack("vigilante", target, attacker=p.seat))

    def status(self, p):
        if p.state.get("hunt"):
            return T("마피아로 밝혀낸 {name}님을 밤에 처단할 수 있다.", name=p.state["hunt"])
        return T("조사를 이미 썼다.") if p.state.get("checked") else T("낮 투표 때 한 번, 한 명이 마피아인지 알아볼 수 있다.")


@register
class Informant(Ability):
    """When a night ends it learns the role of one citizen-team player it did not know yet."""
    key = "informant"

    def morning(self, game, p, ctx):
        known = set(p.state.get("known", []))
        town = [q for q in game.alive() if q is not p and side(q) == TOWN and q.name not in known]
        if not town:
            return
        q = game.rng.choice(town)
        p.state["known"] = sorted(known | {q.name})
        game.private(p, T("정보: {name}님은 시민 팀 {role:이다/다}.", name=q.name, role=q.role), target=q.seat, result=q.role,
                     knows=[q.seat])
        game.know(p, q)
        learned(game, p, q)


@register
class Liaison(Ability):
    """Names one player at night; on the same team both learn each other's role."""
    key = "liaison"
    act_text, pass_text = "{t}님에게 연락합니다", "아무에게도 연락하지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 연락할 사람 한 명을 고른다. 같은 팀이면 둘이 서로의 직업을 알게 된다."),
                           field="target", options=target_names(game, p))

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        if side(q) != side(p):
            game.private(p, T("{name}님과는 이어지지 않았다.", name=q.name), target=q.seat)
            return
        game.private(p, T("{name}님과 이어졌다. {name}님은 {role:이다/다}.", name=q.name, role=q.role), target=q.seat,
                     result=q.role, knows=[q.seat])
        game.private(q, T("연락관 {name}님과 이어졌다. 같은 팀이다.", name=p.name), target=p.seat, knows=[p.seat])
        game.know(p, q)
        game.know(q, p)
        learned(game, p, q)
        learned(game, q, p)


FLAG_DAY = 4


@register
class Flagbearer(Ability):
    """Alive on the 4th day, its team wins."""
    key = "flagbearer"

    def wins(self, game, p):
        return game.day >= FLAG_DAY

    def holds_game(self, game, p):
        return tied(game) and game.day < FLAG_DAY

    def status(self, p):
        return T("{n}번째 낮까지 살아 있으면 네 팀이 이긴다.", n=FLAG_DAY)


@register
class Foreman(Ability):
    """When the 찬반 goes against its own pick it reveals itself and turns it; from then on it decides alone."""
    key = "foreman"

    def override_verdict(self, game, p, pick, passed):
        mine = None if pick is None else pick == "찬성"
        if p.state.get("ruling"):
            if bool(mine) != passed:  # 기권 counts as 반대
                game.system(T("배심장 {name}님의 선택대로 결과가 바뀌었습니다.", name=p.name), target=p.seat)
            return bool(mine)
        if mine is None or mine == passed:
            return None
        p.state["ruling"] = True
        p.revealed = True
        game.system(T("배심장 {name}님이 찬반 결과를 뒤집었습니다. 이제 찬반은 배심장 혼자 정합니다.", name=p.name), target=p.seat)
        return mine

    def holds_game(self, game, p):
        return tied(game)

    def status(self, p):
        return T("정체를 드러냈다. 찬반은 너 혼자 정한다.") if p.state.get("ruling") else None


@register
class Assistant(Ability):
    """Looks for the 의사; once no 의사 lives it saves its pick from the mafia attack each night."""
    key = "assistant"
    act_text, pass_text = "{t}님을 찾아갑니다", "아무도 찾아가지 않았습니다"
    priority = 20

    def night_request(self, game, p):
        if doctor_alive(game):
            task = T("밤이다. 한 명을 찾아간다. 의사면 둘이 서로를 알게 된다.")
            return TurnRequest("night", task, field="target", options=target_names(game, p))
        return TurnRequest("night", T("밤이다. 의사가 없으니 오늘 밤 살릴 사람 한 명을 고른다. 너 자신도 된다."),
                           field="target", options=target_names(game, p, include_self=True))

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        if not doctor_alive(game):
            ctx.protected.add(q.name)
            return
        if q.role != "의사":
            game.private(p, T("{name}님은 의사가 아니다.", name=q.name), target=q.seat)
            return
        game.private(p, T("{name}님이 의사다. 서로를 알게 되었다.", name=q.name), target=q.seat, result=q.role, knows=[q.seat])
        game.private(q, T("조수 {name}님이 너를 찾아왔다.", name=p.name), target=p.seat, knows=[p.seat])
        for a, b in ((p, q), (q, p)):
            if side(a) == side(b):
                game.know(a, b)
        learned(game, p, q)

    def status(self, p):
        return None


def doctor_alive(game) -> bool:  # noqa: ANN001
    return any(q.alive and q.role == "의사" for q in game.players)


@register
class Illusionist(Ability):
    """Tricks one player at night; attacked that night, the tricked player dies in its place."""
    key = "illusionist"
    act_text, pass_text = "{t}님에게 트릭을 겁니다", "아무에게도 트릭을 걸지 않았습니다"
    priority = 10

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 트릭을 걸 사람 한 명을 고른다. 오늘 밤 네가 공격받으면 그 사람이 대신 죽는다."),
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        p.state["trick"] = target or ""
        if target:
            ctx.used_on[p.seat] = target

    def on_attack(self, game, p, attack, ctx):
        q = game.by_name(p.state.get("trick"))
        if q is None or q is p or not q.alive or ctx.dying(q.name) or q.name in game.god_protect:
            return "die"
        ctx.deaths.append((q.name, "trick"))
        game.observe("trick", T("환술사 {by}님 대신 {name}님이 죽습니다.", by=p.name, name=q.name), actor=p.seat, target=q.seat)
        game.private(p, T("공격받았지만 트릭을 건 {name}님이 대신 죽었다.", name=q.name), target=q.seat)
        return "silent"

    def morning(self, game, p, ctx):
        p.state.pop("trick", None)


@register
class Wiretapper(Ability):
    """Picks one player at the day vote and learns that player's role when night falls."""
    key = "wiretapper"

    def vote_extra(self, game, p):
        return TurnRequest("vote", "", extra_field="tap", extra_options=target_names(game, p),
                           extra_task=T("tap: 밤이 될 때 직업을 알아낼 사람. 안 하려면 \"{none}\".", none="없음"))

    def after_vote(self, game, p, vote, extra):
        q = picked(game, extra)
        if q is None or q is p:
            return
        p.state["tap"] = q.name
        announce(game, p, T("{name}님을 도청합니다", name=q.name), q)

    def nightfall(self, game, p, ctx):
        q = game.by_name(p.state.pop("tap", None))
        if q is None:
            return
        game.private(p, T("도청 결과: {name}님의 직업은 {role}입니다.", name=q.name, role=q.role), target=q.seat, result=q.role,
                     knows=[q.seat])
        learned(game, p, q)
