"""의사: picks one player each night and saves them from the mafia attack. Self allowed, repeats allowed (source)."""
from __future__ import annotations

from ..text import T
from ..turn import TurnRequest
from .base import Ability, NightContext, register, target_names


@register
class Doctor(Ability):
    key = "doctor"
    act_text, pass_text = "{t}님을 지킵니다", "아무도 지키지 않았습니다"
    priority = 20

    def night_request(self, game, p):
        return TurnRequest("night", T("밤이다. 오늘 밤 살릴 사람 한 명을 고른다. 그 사람이 마피아에게 공격받으면 살아난다. 너 자신도 된다."),
                           field="target", options=target_names(game, p, include_self=True))

    async def act(self, game, p, target, ctx: NightContext):
        if target:
            ctx.protected.add(target)
            ctx.used_on[p.seat] = target
