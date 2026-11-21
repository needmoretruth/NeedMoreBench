"""시민 팀 특수, classic pool: 방패병, 시장, 영매, 연인, 협박꾼, 폭로자, 미행꾼, 계승자, 폭탄마,
복수자, 사냥꾼, 부활술사."""
from __future__ import annotations

from ..parse import is_skip
from ..text import T
from ..turn import TurnRequest
from .base import Ability, Attack, NightContext, announce, dead_names, in_mafia_team, learned, register, target_names, tied


@register
class Shieldbearer(Ability):
    key = "shieldbearer"

    def on_attack(self, game, p, attack: Attack, ctx: NightContext):
        if attack.source != "mafia" or p.state.get("armor_used"):
            return "die"
        p.state["armor_used"] = True
        p.revealed = True
        ctx.morning.append(T("방패병 {name}님이 마피아의 공격을 버텨냈습니다.", name=p.name))
        return "survive"

    def status(self, p):
        return T("방패를 이미 썼다.") if p.state.get("armor_used") else T("마피아의 공격을 한 번 버틸 수 있다.")


@register
class Mayor(Ability):
    key = "mayor"

    def vote_weight(self, p):
        return 2

    def executable(self, game, p):
        return False

    def holds_game(self, game, p):
        return tied(game)


@register
class Medium(Ability):
    key = "medium"
    act_text, pass_text = "{t}님을 성불시킵니다", "아무도 성불시키지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        opts = dead_names(game, rested=False)
        if not opts:
            return None
        return TurnRequest("night", T("밤이다. 죽은 사람 한 명을 골라 직업을 알아내고 성불시킨다. 성불한 사람은 더 말하지 못한다."),
                           field="target", options=opts, skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or q.alive or q.at_rest:
            return
        q.at_rest = True
        game.private(p, T("{name}님의 직업은 {role:이었다/였다}. {name}님을 성불시켰다.", name=q.name, role=q.role),
                     target=q.seat, result=q.role, knows=[q.seat])
        game.private(q, T("영매가 너를 성불시켰다. 이제 죽은 사람 대화에서 말할 수 없다."))
        learned(game, p, q)


def partner(game, p):  # noqa: ANN001
    return next((q for q in game.players if q is not p and q.role == "연인"), None)


@register
class Lover(Ability):
    key = "lover"

    def on_start(self, game, p):
        q = partner(game, p)
        if q is not None:
            game.private(p, T("너의 연인은 {name}님이다. 밤마다 둘만 대화한다.", name=q.name), target=q.seat, knows=[q.seat])
            game.know(p, q)

    def on_attack(self, game, p, attack, ctx):
        q = partner(game, p)
        if attack.source != "mafia" or q is None or not q.alive or ctx.dying(q.name) or q.name in game.god_protect:
            return "die"
        ctx.deaths.append((q.name, "lover"))
        ctx.morning.append(T("연인 {name}님이 {other}님을 대신해 죽었습니다.", name=q.name, other=p.name))
        p.revealed = q.revealed = True
        return "silent"

    def status(self, p):
        return None


@register
class Blackmailer(Ability):
    key = "blackmailer"
    act_text, pass_text = "{t}님을 협박합니다", "아무도 협박하지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 한 명을 골라 내일 낮 그 사람의 투표권을 빼앗는다."), field="target",
                           options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or not q.alive:
            return
        q.no_vote_day = game.day + 1  # night N is followed by day N+1
        game.private(p, T("{name}님을 협박했다. {name}님은 {n}번째 낮에 투표하지 못한다.", name=q.name, n=q.no_vote_day), target=q.seat)
        game.private(q, T("협박꾼에게 협박당했다. {n}번째 낮에는 투표할 수 없다.", n=q.no_vote_day))

    def holds_game(self, game, p):
        return tied(game)


@register
class Exposer(Ability):
    key = "exposer"
    act_text, pass_text = "{t}님을 폭로합니다", "폭로를 아꼈습니다"
    priority = 40

    def night_request(self, game, p):
        if p.state.get("used") or game.day < 2:
            return None
        return TurnRequest("night", T("밤이다. 폭로할 사람 한 명을 고르면 그 사람의 직업이 다음 아침 모두에게 공개된다. "
                                      "게임에서 한 번만 된다. 아끼려면 {none}.", none="없음"),
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        p.state["used"] = True
        p.state["scoop"] = q.name
        game.private(p, T("폭로할 사람: {name}님은 {role:이다/다}. 아침에 모두에게 알려진다.", name=q.name, role=q.role),
                     target=q.seat, result=q.role, knows=[q.seat])

    def morning(self, game, p, ctx):
        name = p.state.pop("scoop", None)
        q = game.by_name(name)
        if q is None:
            return
        q.revealed = True
        ctx.morning.append(T("폭로자가 밝혔습니다. {name}님의 직업은 {role}입니다.", name=q.name, role=q.role))
        learned(game, p, q)

    def status(self, p):
        return T("폭로를 이미 썼다.") if p.state.get("used") else T("폭로는 두 번째 밤부터, 게임에서 한 번 쓸 수 있다.")


@register
class Shadow(Ability):
    key = "shadow"
    act_text, pass_text = "{t}님을 미행합니다", "아무도 미행하지 않았습니다"
    priority = 60  # after everyone else acted

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 한 명을 골라 그 사람이 오늘 밤 누구에게 능력을 썼는지 알아낸다."), field="target",
                           options=target_names(game, p))

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        on = ctx.used_on.get(q.seat)
        if on:
            text = T("추적 결과: {name}님은 오늘 밤 {on}님에게 능력을 썼다.", name=q.name, on=on)
        else:
            text = T("추적 결과: {name}님은 오늘 밤 아무에게도 능력을 쓰지 않았다.", name=q.name)
        game.private(p, text, target=q.seat)


@register
class Heir(Ability):
    key = "heir"

    def morning(self, game, p, ctx):
        if ctx.night != 1 or p.state.get("robbed"):
            return
        victim = next((game.by_name(n) for n, c in ctx.deaths if c == "mafia"), None)
        if victim is None or victim is p:
            return
        p.state["robbed"] = True
        game.set_role(p, victim.role, T("첫날 밤 마피아에게 죽은 {name}님의 직업을 물려받았다. 이제 너는 {role:이다/다}.",
                                        name=victim.name, role=victim.role))
        learned(game, p, victim, victim.role)

    def status(self, p):
        return T("첫날 밤 마피아에게 죽은 사람이 있으면 그 직업을 물려받는다.")


@register
class Bomber(Ability):
    key = "bomber"
    act_text, pass_text = "{t}님을 찍습니다", "아무도 찍지 않았습니다"
    priority = 10

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 한 명을 찍는다. 찍은 사람이 마피아일 때 오늘 밤 네가 마피아에게 죽으면 그 사람도 함께 죽는다."),
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        p.state["mark"] = target or ""

    def on_attack(self, game, p, attack, ctx):
        q = game.by_name(p.state.get("mark"))
        if attack.source == "mafia" and q is not None and q.alive and q.role == "마피아" and not ctx.dying(q.name):
            ctx.deaths.append((q.name, "terror"))
            ctx.morning.append(T("폭탄마 {by}님이 {name}님과 함께 죽었습니다.", by=p.name, name=q.name))
        return "die"

    def defense_extra(self, game, p):
        return TurnRequest("defense", "", extra_field="take", extra_options=target_names(game, p),
                           extra_task=T("take: 처형되면 함께 데려갈 사람. 그 사람이 적(마피아 팀)일 때만 함께 죽는다."))

    def defense_choice(self, game, p, extra):
        q = game.by_name(str(extra)) if extra and not is_skip(extra) else None
        what = T("처형되면 {name}님을 함께 데려가려 합니다", name=q.name) if q else T("처형되어도 아무도 데려가지 않기로 했습니다")
        announce(game, p, what, q)

    def on_executed(self, game, p, extra):
        q = game.by_name(str(extra)) if extra and not is_skip(extra) else None
        if q is not None and q.alive and in_mafia_team(q):
            game.kill(q, T("폭탄마 {by}님이 {name}님과 함께 죽었습니다.", by=p.name, name=q.name), "terror")


@register
class Avenger(Ability):
    """복수자: a mafia kill at night is answered with one shot at the member whose pick set the target."""
    key = "avenger"

    def on_attack(self, game, p, attack, ctx):
        q = game.players[attack.attacker] if attack.source == "mafia" and attack.attacker is not None else None
        if q is not None and q.alive and not ctx.dying(q.name) and q.name not in game.god_protect:
            ctx.deaths.append((q.name, "avenger"))
            ctx.morning.append(T("복수자 {by}님이 죽기 전에 쏜 총에 {name}님이 맞았습니다.", by=p.name, name=q.name))
        return "die"


@register
class Hunter(Ability):
    """사냥꾼: executed by vote, it takes any one living player along after the 찬반."""
    key = "hunter"

    def last_shot(self, game, p):
        return TurnRequest("shot", T("너는 투표로 처형되었다. 사냥꾼의 마지막 한 발로 살아 있는 사람 한 명을 골라 함께 데려갈 수 있다. "
                                     "누구든 되고 모두에게 알려진다. 아무도 데려가지 않으려면 {none}.", none="없음"),
                           field="target", options=target_names(game, p), skip_word="없음")

    def take_shot(self, game, p, pick):
        q = game.by_name(pick)
        ok = q is not None and q.alive and q is not p
        announce(game, p, T("{name}님을 함께 데려갑니다", name=q.name) if ok else T("아무도 데려가지 않았습니다"), q if ok else None)
        if ok:
            game.kill(q, T("사냥꾼 {by}님이 {name}님을 함께 데려갔습니다.", by=p.name, name=q.name), "hunter")


@register
class Reviver(Ability):
    key = "reviver"
    act_text, pass_text = "{t}님을 되살립니다", "부활을 아꼈습니다"
    priority = 50

    def night_request(self, game, p):
        opts = dead_names(game, rested=False)
        if p.state.get("used") or not opts:
            return None
        return TurnRequest("night", T("밤이다. 죽은 사람 한 명을 되살릴 수 있다. 게임에서 한 번만 된다. 아끼려면 {none}.", none="없음"),
                           field="target", options=opts, skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or q.alive or q.at_rest:
            return
        p.state["used"] = True
        game.revive(q, T("부활술사가 {name}님을 되살렸습니다.", name=q.name), ctx)

    def holds_game(self, game, p):
        return tied(game) and not p.state.get("used") and bool(dead_names(game, rested=False))

    def status(self, p):
        return T("부활을 이미 썼다.") if p.state.get("used") else None
