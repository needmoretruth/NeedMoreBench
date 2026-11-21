"""시민 팀 특수, classic pool: 군인, 정치인, 영매, 연인, 건달, 기자, 사립탐정, 도굴꾼, 테러리스트,
복수자, 사냥꾼, 성직자."""
from __future__ import annotations

from ..parse import is_skip
from ..turn import TurnRequest
from ..words import josa
from .base import Ability, Attack, NightContext, dead_names, in_mafia_team, learned, register, target_names, tied


@register
class Soldier(Ability):
    key = "soldier"

    def on_attack(self, game, p, attack: Attack, ctx: NightContext):
        if attack.source != "mafia" or p.state.get("armor_used"):
            return "die"
        p.state["armor_used"] = True
        p.revealed = True
        ctx.morning.append(f"군인 {p.name}님이 마피아의 공격을 버텨냈습니다.")
        return "survive"

    def status(self, p):
        return "방탄을 이미 썼다." if p.state.get("armor_used") else "마피아의 공격을 한 번 버틸 수 있다."


@register
class Politician(Ability):
    key = "politician"

    def vote_weight(self, p):
        return 2

    def executable(self, game, p):
        return False

    def holds_game(self, game, p):
        return tied(game)


@register
class Medium(Ability):
    key = "medium"
    priority = 40

    def night_request(self, game, p):
        opts = dead_names(game, rested=False)
        if not opts:
            return None
        return TurnRequest("night", "밤이다. 죽은 사람 한 명을 골라 직업을 알아내고 성불시킨다. 성불한 사람은 더 말하지 못한다.",
                           field="target", options=opts, skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or q.alive or q.at_rest:
            return
        q.at_rest = True
        game.private(p, f"{q.name}님의 직업은 {q.role}였다. {q.name}님을 성불시켰다.", target=q.seat, result=q.role,
                     knows=[q.seat])
        game.private(q, "영매가 너를 성불시켰다. 이제 죽은 사람 대화에서 말할 수 없다.")
        learned(game, p, q)


def partner(game, p):  # noqa: ANN001
    return next((q for q in game.players if q is not p and q.role == "연인"), None)


@register
class Lover(Ability):
    key = "lover"

    def on_start(self, game, p):
        q = partner(game, p)
        if q is not None:
            game.private(p, f"너의 연인은 {q.name}님이다. 밤마다 둘만 대화한다.", target=q.seat, knows=[q.seat])

    def on_attack(self, game, p, attack, ctx):
        q = partner(game, p)
        if attack.source != "mafia" or q is None or not q.alive or ctx.dying(q.name) or q.name in game.god_protect:
            return "die"
        ctx.deaths.append((q.name, "lover"))
        ctx.morning.append(f"연인 {q.name}님이 {p.name}님을 대신해 죽었습니다.")
        p.revealed = q.revealed = True
        return "silent"

    def status(self, p):
        return None


@register
class Thug(Ability):
    key = "thug"
    priority = 40

    def night_request(self, game, p):
        return TurnRequest("night", "밤이다. 한 명을 골라 내일 낮 그 사람의 투표권을 빼앗는다.", field="target",
                           options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or not q.alive:
            return
        q.no_vote_day = game.day + 1  # night N is followed by day N+1
        game.private(p, f"{q.name}님을 협박했다. {q.name}님은 {q.no_vote_day}번째 낮에 투표하지 못한다.", target=q.seat)
        game.private(q, f"건달에게 협박당했다. {q.no_vote_day}번째 낮에는 투표할 수 없다.")

    def holds_game(self, game, p):
        return tied(game)


@register
class Reporter(Ability):
    key = "reporter"
    priority = 40

    def night_request(self, game, p):
        if p.state.get("used") or game.day < 2:
            return None
        return TurnRequest("night", "밤이다. 취재할 사람 한 명을 고르면 그 사람의 직업이 다음 아침 기사로 모두에게 공개된다. "
                           "게임에서 한 번만 된다. 아끼려면 없음.", field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        p.state["used"] = True
        p.state["scoop"] = q.name
        game.private(p, f"취재 결과: {q.name}님은 {josa(q.role, '이다', '다')}. 아침에 기사가 나간다.", target=q.seat,
                     result=q.role, knows=[q.seat])

    def morning(self, game, p, ctx):
        name = p.state.pop("scoop", None)
        q = game.by_name(name)
        if q is None:
            return
        q.revealed = True
        ctx.morning.append(f"특종입니다! {q.name}님의 직업은 {q.role}입니다.")
        learned(game, p, q)

    def status(self, p):
        return "취재를 이미 썼다." if p.state.get("used") else "취재는 두 번째 밤부터, 게임에서 한 번 쓸 수 있다."


@register
class Detective(Ability):
    key = "detective"
    priority = 60  # after everyone else acted

    def night_request(self, game, p):
        return TurnRequest("night", "밤이다. 한 명을 골라 그 사람이 오늘 밤 누구에게 능력을 썼는지 알아낸다.", field="target",
                           options=target_names(game, p))

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        on = ctx.used_on.get(q.seat)
        text = f"{q.name}님은 오늘 밤 {on}님에게 능력을 썼다." if on else f"{q.name}님은 오늘 밤 아무에게도 능력을 쓰지 않았다."
        game.private(p, "추적 결과: " + text, target=q.seat)


@register
class Graverobber(Ability):
    key = "graverobber"

    def morning(self, game, p, ctx):
        if ctx.night != 1 or p.state.get("robbed"):
            return
        victim = next((game.by_name(n) for n, c in ctx.deaths if c == "mafia"), None)
        if victim is None or victim is p:
            return
        p.state["robbed"] = True
        game.set_role(p, victim.role, f"첫날 밤 마피아에게 죽은 {victim.name}님의 직업을 물려받았다. 이제 너는 {josa(victim.role, '이다', '다')}.")
        learned(game, p, victim, victim.role)

    def status(self, p):
        return "첫날 밤 마피아에게 죽은 사람이 있으면 그 직업을 물려받는다."


@register
class Terrorist(Ability):
    key = "terrorist"
    priority = 10

    def night_request(self, game, p):
        return TurnRequest("night", "밤이다. 한 명을 찍는다. 찍은 사람이 마피아일 때 오늘 밤 네가 마피아에게 죽으면 그 사람도 함께 죽는다.",
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx):
        p.state["mark"] = target or ""

    def on_attack(self, game, p, attack, ctx):
        q = game.by_name(p.state.get("mark"))
        if attack.source == "mafia" and q is not None and q.alive and q.role == "마피아" and not ctx.dying(q.name):
            ctx.deaths.append((q.name, "terror"))
            ctx.morning.append(f"테러리스트 {p.name}님이 {q.name}님과 함께 죽었습니다.")
        return "die"

    def defense_extra(self, game, p):
        return TurnRequest("defense", "", extra_field="take", extra_options=target_names(game, p),
                           extra_task="take: 처형되면 함께 데려갈 사람. 그 사람이 적(마피아 팀)일 때만 함께 죽는다.")

    def on_executed(self, game, p, extra):
        q = game.by_name(str(extra)) if extra and not is_skip(extra) else None
        if q is not None and q.alive and in_mafia_team(q):
            game.kill(q, f"테러리스트 {p.name}님이 {q.name}님과 함께 죽었습니다.", "terror")


@register
class Avenger(Ability):
    """복수자: a mafia kill at night is answered with one shot at the member whose pick set the target."""
    key = "avenger"

    def on_attack(self, game, p, attack, ctx):
        q = game.players[attack.attacker] if attack.source == "mafia" and attack.attacker is not None else None
        if q is not None and q.alive and not ctx.dying(q.name) and q.name not in game.god_protect:
            ctx.deaths.append((q.name, "avenger"))
            ctx.morning.append(f"복수자 {p.name}님이 죽기 전에 쏜 총에 {q.name}님이 맞았습니다.")
        return "die"


@register
class Hunter(Ability):
    """사냥꾼: executed by vote, it takes any one living player along after the 찬반."""
    key = "hunter"

    def last_shot(self, game, p):
        return TurnRequest("shot", "너는 투표로 처형되었다. 사냥꾼의 마지막 한 발로 살아 있는 사람 한 명을 골라 함께 데려갈 수 있다. "
                           "누구든 되고 모두에게 알려진다. 아무도 데려가지 않으려면 없음.", field="target",
                           options=target_names(game, p), skip_word="없음")

    def take_shot(self, game, p, pick):
        q = game.by_name(pick)
        if q is not None and q.alive and q is not p:
            game.kill(q, f"사냥꾼 {p.name}님이 {q.name}님을 함께 데려갔습니다.", "hunter")


@register
class Priest(Ability):
    key = "priest"
    priority = 50

    def night_request(self, game, p):
        opts = dead_names(game, rested=False)
        if p.state.get("used") or not opts:
            return None
        return TurnRequest("night", "밤이다. 죽은 사람 한 명을 되살릴 수 있다. 게임에서 한 번만 된다. 아끼려면 없음.", field="target",
                           options=opts, skip_word="없음")

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None or q.alive or q.at_rest:
            return
        p.state["used"] = True
        game.revive(q, f"성직자의 기도로 {q.name}님이 되살아났습니다.", ctx)

    def holds_game(self, game, p):
        return tied(game) and not p.state.get("used") and bool(dead_names(game, rested=False))

    def status(self, p):
        return "부활을 이미 썼다." if p.state.get("used") else None
