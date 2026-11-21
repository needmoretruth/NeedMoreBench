"""시민 팀, the rest of the full pool, part two: 관상가, 해결사, 기록관, 소문꾼, 주술사, 점성가."""
from __future__ import annotations

from ..roles import TOWN
from ..text import T
from ..turn import TurnRequest
from .base import Ability, Attack, NightContext, announce, learned, register, side, target_names, tied
from .town_full import picked


@register
class FaceReader(Ability):
    """Names two players at night and learns whether they are on the same team."""
    key = "face_reader"
    act_text, pass_text = "{t}님의 관상을 봅니다", "관상을 보지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        opts = target_names(game, p)
        if len(opts) < 2:
            return None
        return TurnRequest("night", T("밤이다. 두 사람을 고르면 둘이 같은 팀인지 다른 팀인지 알게 된다. 첫 사람은 target, 둘째는 second에 적는다."),
                           field="target", options=opts, skip_word="없음", extra_field="second", extra_options=opts,
                           extra_task=T("second: 첫 사람과 견줄 둘째 사람."))

    async def act(self, game, p, target, ctx):
        a = game.by_name(target) if target else None
        b = picked(game, ctx.answers.get(p.seat, {}).get("second"))
        if a is None or b is None or a is b or b is p:
            if a is not None:
                game.private(p, T("둘째 사람을 고르지 않아 관상을 보지 못했다."))
            return
        same = side(a) == side(b)
        line = T("관상 결과: {a}님과 {b}님은 같은 팀이다.", a=a.name, b=b.name) if same else \
            T("관상 결과: {a}님과 {b}님은 다른 팀이다.", a=a.name, b=b.name)
        game.private(p, line, target=a.seat, result="같은 팀" if same else "다른 팀")


@register
class Fixer(Ability):
    """Has a citizen client from the start; once the client dies at night it may kill one player each night."""
    key = "fixer"
    act_text, pass_text = "{t}님을 제거합니다", "아무도 제거하지 않았습니다"
    priority = 30

    def on_start(self, game, p):
        town = [q for q in game.players if q is not p and side(q) == TOWN]
        if not town:
            return
        q = game.rng.choice(town)
        p.state["client"] = q.name
        game.private(p, T("너의 의뢰인은 {name}님이다. 의뢰인이 밤에 죽으면 그 뒤 밤마다 한 명을 죽일 수 있다.", name=q.name), target=q.seat)

    def morning(self, game, p, ctx):
        client = p.state.get("client")
        if client and not p.state.get("armed") and any(n == client for n, _c in ctx.deaths):
            p.state["armed"] = True
            game.private(p, T("의뢰인 {name}님이 밤에 죽었다. 이제 밤마다 한 명을 죽일 수 있다.", name=client))

    def night_request(self, game, p):
        if not p.state.get("armed"):
            return None
        return TurnRequest("night", T("밤이다. 죽일 사람 한 명을 고른다. 안 죽이려면 {none}.", none="없음"),
                           field="target", options=target_names(game, p), skip_word="없음")

    async def act(self, game, p, target, ctx: NightContext):
        if target and p.state.get("armed"):
            ctx.attacks.append(Attack("mercenary", target, attacker=p.seat))

    def holds_game(self, game, p):
        return tied(game) and bool(p.state.get("armed"))

    def status(self, p):
        if p.state.get("armed"):
            return T("의뢰인이 죽어 밤마다 한 명을 죽일 수 있다.")
        client = p.state.get("client")
        return T("너의 의뢰인: {name}님.", name=client) if client else None


@register
class Archivist(Ability):
    """Writes one role at night and learns who has it."""
    key = "archivist"
    act_text, pass_text = "{t} 직업을 찾아봅니다", "아무 직업도 찾아보지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        roles = [r for r in game.guess_options() if r not in ("모름", "시민", "마피아")]
        if not roles:
            return None
        return TurnRequest("night", T("밤이다. 직업 하나를 적으면 지금 그 직업을 가진 사람을 알게 된다."), field="target",
                           options=roles, skip_word="없음")

    async def act(self, game, p, target, ctx):
        if not target:
            return
        who = [q for q in game.alive() if q is not p and q.role == target]
        if not who:
            game.private(p, T("기록 결과: 살아 있는 사람 가운데 {role:은/는} 없다.", role=target), result="없음")
            return
        game.private(p, T("기록 결과: {role:은/는} {names}님이다.", role=target, names=[q.name for q in who]),
                     result=target, knows=[q.seat for q in who])
        for q in who:
            learned(game, p, q)


@register
class Gossip(Ability):
    """Each morning receives one role the citizen team has found out (from what others learned)."""
    key = "gossip"

    def morning(self, game, p, ctx):
        heard = set(map(tuple, p.state.get("heard", [])))
        news = [(n, r) for n, r in game.town_learned if n != p.name and (n, r) not in heard]
        if not news:
            return
        name, role = news[0]
        p.state["heard"] = sorted(heard | {(name, role)})
        q = game.by_name(name)
        game.private(p, T("소문: {name}님의 직업은 {role:이라고/라고} 한다.", name=name, role=role),
                     target=q.seat if q else None, result=role)


@register
class Enchanter(Ability):
    """Puts a spell on one player at night; at the day vote it may wake one spellbound player and, if that player
    is not on the citizen team, learns the role."""
    key = "enchanter"
    act_text, pass_text = "{t}님에게 주술을 겁니다", "아무에게도 주술을 걸지 않았습니다"
    priority = 10

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 주술을 걸 사람 한 명을 고른다."), field="target", options=target_names(game, p),
                           skip_word="없음")

    async def act(self, game, p, target, ctx):
        if target:
            p.state["spell"] = sorted(set(p.state.get("spell", [])) | {target})

    def _spelled(self, game, p) -> list[str]:  # noqa: ANN001
        return [n for n in p.state.get("spell", []) if (q := game.by_name(n)) is not None and q.alive]

    def vote_extra(self, game, p):
        names = self._spelled(game, p)
        if not names:
            return None
        return TurnRequest("vote", "", extra_field="wake", extra_options=names,
                           extra_task=T("wake: 주술에서 깨울 사람. 시민 팀이 아니면 직업을 알게 된다. 안 깨우려면 \"{none}\".", none="없음"))

    def after_vote(self, game, p, vote, extra):
        q = picked(game, extra)
        if q is None or q.name not in p.state.get("spell", []):
            return
        p.state["spell"] = [n for n in p.state["spell"] if n != q.name]
        announce(game, p, T("{name}님을 주술에서 깨웁니다", name=q.name), q)
        if side(q) == TOWN:
            game.private(p, T("{name}님을 깨웠다. 직업은 알 수 없었다.", name=q.name), target=q.seat)
            return
        game.private(p, T("{name}님을 깨웠다. {name}님의 직업은 {role:이다/다}.", name=q.name, role=q.role), target=q.seat,
                     result=q.role, knows=[q.seat])
        learned(game, p, q)

    def status(self, p):
        names = p.state.get("spell") or []
        return T("주술에 걸린 사람: {names}", names=names) if names else None


@register
class Astrologer(Ability):
    """Names one player at night and is shown two roles in mixed order: that player's and that of someone on
    another team."""
    key = "astrologer"
    act_text, pass_text = "{t}님의 별을 봅니다", "별을 보지 않았습니다"
    priority = 40

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 한 명을 고르면 그 사람의 직업과, 그와 다른 팀인 누군가의 직업이 섞여 두 개로 나온다."),
                           field="target", options=target_names(game, p))

    async def act(self, game, p, target, ctx):
        q = game.by_name(target) if target else None
        if q is None:
            return
        other = [r.role for r in game.players if r is not q and r is not p and side(r) != side(q) and r.role != q.role]
        if not other:
            game.private(p, T("점괘: {name}님의 직업은 {role:이다/다}.", name=q.name, role=q.role), target=q.seat, result=q.role)
            return
        two = [q.role, game.rng.choice(other)]
        game.rng.shuffle(two)
        game.private(p, T("점괘: {name}님의 직업은 {a}, {b} 가운데 하나다.", name=q.name, a=two[0], b=two[1]), target=q.seat,
                     result=two)
