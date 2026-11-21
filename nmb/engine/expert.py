"""전문가 모드: one fixed strategy section per side and role, added to the prompt only
for seats with the switch on. It teaches how strong players reason and never says anything about this game.
The text is versioned: change EXPERT_VERSION whenever a word changes, so the standings keep versions apart.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .abilities import in_mafia_team
from .roles import CULT, MAFIA, ROLES

if TYPE_CHECKING:
    from .game import Game
    from .state import Player

EXPERT_VERSION = 1

COMMON = """- 주장과 사실을 나눠 기록한다. 누가 무슨 직업이라고 했는지, 그 주장이 밤 결과, 죽음, 투표와 맞는지 날마다 맞춰 본다.
- 투표는 말보다 정직하다. 누가 누구를 찍었고(공개될 때) 표가 몰릴 때 누가 따라갔는지, 결과로 누가 이득을 봤는지 본다.
- 각 직업이 무엇을 알 수 있는지 떠올린다. 아는 척하는 정보가 그 직업으로 알 수 없는 것이면 거짓이다.
- 승리 조건을 센다. 오늘 처형이 틀리면 몇 명이 남고 다음 밤 뒤 누가 이기는지 계산하고 그 수에 맞게 위험을 고른다.
- 한 밤 앞을 생각한다. 오늘 한 말이 오늘 밤 누구를 표적으로 만들지 따진다.
- 장부를 실제 판단대로 고친다. 새 정보가 나오면 의심도를 옮기고 이유를 비고에 남긴다."""

TOWN_TEXT = """시민 팀
- 마피아는 정보가 없는 척하면서 대화를 이끌거나, 남의 의견에 조용히 올라탄다. 근거 없이 확신하는 사람과 근거를 바꿔 가며 한 사람을 미는 사람을 본다.
- 직업 공개는 시점이 중요하다. 너무 일찍 밝히면 밤에 표적이 되고, 너무 늦게 밝히면 정보가 버려진다. 확실한 결과가 있거나 처형을 막아야 할 때 밝힌다.
- 같은 직업을 두 사람이 주장하면 적어도 하나는 거짓이다. 두 주장의 지난 결과를 비교한다."""

MAFIA_TEXT = """마피아 팀
- 낮에는 시민 팀의 한 사람처럼 추리한다. 정보를 아는 티를 내지 않고, 동료를 너무 감싸거나 너무 세게 버리지 않는다.
- 거짓 직업 주장은 그 직업이 알 수 있는 결과와 앞뒤가 맞아야 한다. 주장하기 전에 진짜 그 직업이 반박하면 어떻게 될지 계산한다.
- 밤 표적은 정보를 가진 사람(확인된 경찰, 의사로 보이는 사람)과 너를 의심하는 설득력 있는 사람 순으로 따진다. 의사가 지킬 만한 사람을 피하는 것도 수다.
- 마피아 회의에서 낮의 역할을 나눈다. 둘이 같은 사람을 몰면 묶여 보인다."""

CULT_TEXT = """교주 팀
- 교주는 신도를 늘릴수록 이긴다. 신도로 만들 사람은 오래 살아남을 사람, 정보를 가진 사람을 고른다.
- 신도가 된 사람은 원래 팀처럼 말하되 교주에게 의심이 쏠리지 않게 표를 나눈다."""

ROLE_TEXT = {
    "경찰": "경찰: 조사 대상은 말이 많고 영향력이 큰 사람, 처형 후보, 확인되지 않은 직업 주장자 순으로 고른다. 결과를 밝힐 때는 날짜별 조사 기록을 함께 말한다.",
    "의사": "의사: 마피아가 노릴 사람(밝힌 경찰, 날카로운 사람)을 지킨다. 너를 밝히면 표적이 되므로 처형을 막아야 할 때까지 숨기는 편이 낫다.",
    "마피아": "마피아: 처형 위기의 동료를 끝까지 감싸면 함께 드러난다. 잃을 때는 버리고 신뢰를 얻는 것도 수다.",
    "스파이": "스파이: 접선 전에는 시민처럼 행동하며 마피아를 찾는다. 접선 뒤에는 알아낸 직업 정보를 회의에서 나눈다.",
    "기자": "기자: 기사는 모두가 보는 확정 정보다. 마피아를 찾으면 처형으로, 시민 핵심 직업을 찾으면 보호로 이어진다.",
    "군인": "군인: 공격을 버티면 모두가 알게 된다. 그 뒤로는 확인된 시민으로서 대화를 이끈다.",
    "정치인": "정치인: 처형되지 않으므로 의심을 받아도 두 표로 판을 움직일 수 있다.",
}


def expert_on(game: "Game", p: "Player") -> bool:
    seats = game.setup.seats
    spec = seats[p.seat] if p.seat < len(seats) else None
    if spec is not None and spec.expert is not None:
        return bool(spec.expert)
    return bool(game.setup.expert)


def expert_text(game: "Game", p: "Player") -> str | None:
    if not expert_on(game, p):
        return None
    team = ROLES[p.role].team
    side = MAFIA_TEXT if in_mafia_team(p) or team == MAFIA else CULT_TEXT if team == CULT else TOWN_TEXT
    parts = [f"전문가 전략 (v{EXPERT_VERSION})", COMMON, side]
    if p.role in ROLE_TEXT:
        parts.append("- " + ROLE_TEXT[p.role])
    return "\n".join(parts)
