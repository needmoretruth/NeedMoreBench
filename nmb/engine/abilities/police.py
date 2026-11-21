"""경찰: investigates one player each night and privately learns 마피아 or 마피아 아님."""
from __future__ import annotations

from ..turn import TurnRequest
from .base import Ability, NightContext, ability_of, register, target_names


@register
class Police(Ability):
    key = "police"
    priority = 40

    def night_request(self, game, p):
        return TurnRequest("night", "밤이다. 조사할 사람 한 명을 고른다. 마피아인지 아닌지 너만 알게 된다.",
                           field="target", options=target_names(game, p))

    async def act(self, game, p, target, ctx: NightContext):
        q = game.by_name(target) if target else None
        if q is None:
            return
        ctx.used_on[p.seat] = q.name
        verdict = "마피아입니다" if ability_of(q.role).looks_mafia(q) else "마피아가 아닙니다"
        game.private(p, f"조사 결과: {q.name}님은 {verdict}.", target=q.seat, result=verdict)
