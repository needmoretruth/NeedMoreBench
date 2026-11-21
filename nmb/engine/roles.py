"""Role data for both games and the line-up per player count.

A role is data: its team, its slot (what kind of seat it fills), what the player is told, and the name of its
ability module in `nmb.engine.abilities`. The engine never names a role; it asks the ability.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

TOWN, MAFIA, CULT = "시민", "마피아", "교주"
TEAM_LABEL = {TOWN: "시민 팀", MAFIA: "마피아 팀", CULT: "교주 팀"}
SIMPLE, COMPLEX = "simple", "complex"
GAME_TITLE = {SIMPLE: "단순 마피아", COMPLEX: "복잡한 마피아"}
SLOT_MAFIA, SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL, SLOT_CITIZEN = "마피아", "보조", "경찰 계열", "의사", "특수", "시민"


@dataclass(frozen=True)
class Role:
    name: str
    team: str
    slot: str
    ability: str  # module key in nmb.engine.abilities
    text: str  # what the player is told it can do
    classic: bool = True


ROLES: dict[str, Role] = {r.name: r for r in [
    Role("시민", TOWN, SLOT_CITIZEN, "none", "특별한 능력은 없다. 말과 투표로 마피아를 찾아낸다."),
    Role("마피아", MAFIA, SLOT_MAFIA, "mafia", "밤마다 마피아끼리 의논해 한 명을 죽인다."),
    Role("경찰", TOWN, SLOT_POLICE, "police", "밤마다 한 명을 조사해 마피아인지 아닌지 알아낸다. 결과는 너만 안다."),
    Role("의사", TOWN, SLOT_DOCTOR, "doctor", "밤마다 한 명을 지목해 마피아의 공격에서 살린다. 자기 자신도 된다."),
    # 복잡한 마피아, classic pool
    Role("스파이", MAFIA, SLOT_HELPER, "spy", "마피아 보조. 처음엔 마피아가 누군지 모른다. 밤마다 한 명의 직업을 알아낸다. 고른 사람이 마피아면 접선해 마피아 회의에 끼고, 그 밤에 한 번 더 조사한다."),
    Role("짐승인간", MAFIA, SLOT_HELPER, "beast", "마피아 보조. 처음엔 마피아가 누군지 모른다. 밤마다 한 명을 찍는다. 찍은 사람이 마피아에게 죽으면 길들여져 접선하고, 그 뒤로 마피아 회의에서 죽일 사람을 같이 고른다. 마피아의 공격으로는 죽지 않는다."),
    Role("마담", MAFIA, SLOT_HELPER, "madam", "마피아 보조. 처음엔 마피아가 누군지 모른다. 낮 투표에서 네가 표를 준 사람을 유혹한다. 유혹당한 사람은 그날 밤 능력을 못 쓰고 다음 낮에 말을 못 한다. 마피아를 유혹하면 접선한다."),
    Role("도둑", MAFIA, SLOT_HELPER, "thief", "마피아 보조. 처음엔 마피아가 누군지 모른다. 투표 때 한 사람을 골라 그 사람의 능력을 훔쳐 그날 밤에 쓴다. 마피아의 능력을 훔치면 마피아와 접선한다."),
    Role("군인", TOWN, SLOT_SPECIAL, "soldier", "마피아의 공격을 한 번 버틴다(모두에게 알려진다). 마피아 팀이 너를 조사하면 조사한 사람이 누군지 알게 된다."),
    Role("정치인", TOWN, SLOT_SPECIAL, "politician", "투표로 처형되지 않는다. 투표에서 두 표로 센다."),
    Role("영매", TOWN, SLOT_SPECIAL, "medium", "죽은 사람들의 대화를 듣고 밤에 그들과 말한다. 밤마다 죽은 사람 한 명의 직업을 알아내고 성불시킨다(그 사람은 더 말하지 못한다)."),
    Role("연인", TOWN, SLOT_SPECIAL, "lover", "연인은 두 명이다. 밤에 둘만 대화한다. 둘 다 살아 있을 때 한 명이 마피아에게 지목되면 다른 한 명이 대신 죽는다."),
    Role("건달", TOWN, SLOT_SPECIAL, "thug", "밤에 한 명을 골라 다음 날 그 사람의 투표권을 빼앗는다."),
    Role("기자", TOWN, SLOT_SPECIAL, "reporter", "게임에서 한 번, 두 번째 밤부터 한 명의 직업을 알아내고 다음 아침 기사로 모두에게 공개한다."),
    Role("사립탐정", TOWN, SLOT_SPECIAL, "detective", "밤에 한 명을 골라 그 사람이 그 밤 누구에게 능력을 썼는지 알아낸다."),
    Role("도굴꾼", TOWN, SLOT_SPECIAL, "graverobber", "첫날 밤 마피아에게 죽은 사람의 직업을 물려받는다."),
    Role("테러리스트", TOWN, SLOT_SPECIAL, "terrorist", "밤에 한 명을 찍는다. 찍은 사람이 마피아일 때 밤에 마피아에게 죽으면 그 마피아와 함께 죽는다. 투표로 처형될 때 찍은 사람이 적이면 함께 죽는다."),
    # the user's own two
    Role("복수자", TOWN, SLOT_SPECIAL, "avenger", "밤에 마피아 팀에게 죽으면 마지막 총을 쏴, 마피아 회의에서 너를 처음 고른 사람을 함께 데려간다. 미리 고를 것은 없다. 의사가 살리면 아무 일도 없다."),
    Role("사냥꾼", TOWN, SLOT_SPECIAL, "hunter", "투표로 처형되면 찬반이 끝난 뒤 살아 있는 사람 한 명을 골라 함께 데려간다. 누구든 되고 모두에게 알려진다. 다른 이유로 죽으면 쏘지 못한다."),
    Role("성직자", TOWN, SLOT_SPECIAL, "priest","게임에서 한 번, 밤에 죽은 사람 한 명을 되살린다(아침에 모두에게 알려진다). 성불한 사람은 못 살린다. 교주에게 포교되지 않는다."),
    # 복잡한 마피아, the rest of the full pool
    Role("마녀", MAFIA, SLOT_HELPER, "witch", "마피아 보조. 처음엔 마피아가 누군지 모른다. 밤마다 한 명을 개구리로 만든다. 개구리는 다음 밤이 올 때까지 직업 능력이 없다(투표권 두 배 같은 특성도 없다). 마피아를 고르면 개구리로 만들지 않고 접선한다.", False),
    Role("과학자", MAFIA, SLOT_HELPER, "scientist", "마피아 보조. 처음엔 마피아가 누군지 모른다. 죽으면 마피아와 접선하고, 다음 밤이 끝날 때 한 번 되살아난다(모두에게 알려진다).", False),
    Role("사기꾼", MAFIA, SLOT_HELPER, "fraud", "마피아 보조. 처음엔 마피아가 누군지 모른다. 시작할 때 시민 팀 한 명의 직업을 알게 되고 그 직업인 척한다. 투표로 처형될 때 한 번 살아남고 접선한다. 그 시민이 처형되어도 접선한다.", False),
    Role("청부업자", MAFIA, SLOT_HELPER, "hitman", "마피아 보조. 처음엔 마피아가 누군지 모른다. 두 번째 밤부터 밤마다 두 사람과 그 직업을 적는다. 둘 다 맞히면 둘 다 죽인다. 적은 사람이 마피아면 접선한다.", False),
    Role("대부", MAFIA, SLOT_HELPER, "godfather", "마피아 보조. 처음엔 마피아가 누군지 모른다. 세 번째 밤에 마피아와 접선한다. 그 뒤로 마피아 회의에서 죽일 사람을 같이 고르고, 마피아의 공격은 의사의 치료와 직업 특성을 무시한다.", False),
    Role("자경단원", TOWN, SLOT_POLICE, "vigilante", "게임에서 한 번, 낮 투표 때 한 명이 마피아인지 알아낸다. 마피아였다면 그 뒤 밤에 그 사람을 죽일 수 있다.", False),
    Role("요원", TOWN, SLOT_POLICE, "agent", "밤이 끝날 때마다 아직 모르는 시민 팀 한 명의 직업을 알게 된다.", False),
    Role("형사", TOWN, SLOT_POLICE, "inspector", "밤에 한 명을 고른다. 같은 팀이면 둘이 서로의 직업을 알게 된다.", False),
    Role("예언자", TOWN, SLOT_SPECIAL, "prophet", "네 번째 낮까지 살아 있으면 시민 팀이 이긴다.", False),
    Role("판사", TOWN, SLOT_SPECIAL, "judge", "찬반 결과가 네 선택과 다르면 정체를 드러내고 결과를 네 선택대로 뒤집는다. 그 뒤로 찬반은 너 혼자 정한다.", False),
    Role("간호사", TOWN, SLOT_SPECIAL, "nurse", "밤에 한 명을 고른다. 의사를 고르면 둘이 서로를 알게 된다. 의사가 죽은 뒤에는 밤마다 고른 사람을 마피아의 공격에서 살린다.", False),
    Role("마술사", TOWN, SLOT_SPECIAL, "magician", "밤에 한 명에게 트릭을 건다. 그 밤 네가 공격받으면 트릭을 건 사람이 대신 죽는다.", False),
    Role("해커", TOWN, SLOT_SPECIAL, "hacker", "낮 투표 때 한 명을 고르면 밤이 될 때 그 사람의 직업을 알게 된다.", False),
    Role("심리학자", TOWN, SLOT_SPECIAL, "psychologist", "낮 투표 때 두 명을 고르면 둘이 다른 팀인지 같은 팀인지 알게 된다.", False),
    Role("용병", TOWN, SLOT_SPECIAL, "mercenary", "시작할 때 시민 팀 한 명이 의뢰인으로 정해진다. 의뢰인이 밤에 죽으면 그 뒤 밤마다 한 명을 죽일 수 있다.", False),
    Role("공무원", TOWN, SLOT_SPECIAL, "official", "밤에 직업 하나를 적으면 그 직업을 가진 사람을 알게 된다.", False),
    Role("파파라치", TOWN, SLOT_SPECIAL, "paparazzi", "아침마다 시민 팀이 알아낸 직업 정보 가운데 하나를 받는다.", False),
    Role("최면술사", TOWN, SLOT_SPECIAL, "hypnotist", "밤에 한 명에게 최면을 건다. 낮 투표 때 최면에 걸린 사람 한 명을 깨우면, 시민 팀이 아닌 사람은 직업을 알게 된다.", False),
    Role("점쟁이", TOWN, SLOT_SPECIAL, "fortune", "밤에 한 명을 고르면 그 사람의 직업과 그와 다른 팀인 누군가의 직업이 섞여 두 개로 나온다.", False),
    # 교주팀 (setting)
    Role("교주", CULT, SLOT_SPECIAL, "cult_leader", "홀수 번째 밤마다 한 명을 포교한다(마피아 팀과 성직자는 안 된다). 포교한 사람의 직업을 알게 되고, 그 사람은 교주 팀이 된다. 포교에 성공하면 모두에게 종소리가 들린다. 밤마다 교주 팀에게 한마디를 보낼 수 있다(교주 팀은 답하지 못한다).", False),
    Role("광신도", CULT, SLOT_SPECIAL, "fanatic", "교주 팀. 처음엔 교주가 누군지 모른다. 밤에 한 명을 확인해 교주를 찾으면 교주와 이어진다. 교주가 죽으면 포교를 이어받는다.", False),
]}

# English names: the interface's source strings (translated back by gettext) and the English dialogue
EN = {"시민": "Citizen", "마피아": "Mafia", "경찰": "Police", "의사": "Doctor", "스파이": "Spy", "짐승인간": "Beastman",
      "마담": "Madam", "도둑": "Thief", "군인": "Soldier", "정치인": "Politician", "영매": "Medium", "연인": "Lover",
      "건달": "Thug", "기자": "Reporter", "사립탐정": "Detective", "도굴꾼": "Graverobber", "테러리스트": "Terrorist",
      "복수자": "Avenger", "사냥꾼": "Hunter", "성직자": "Priest", "모름": "Unknown", "교주": "Cult leader", "광신도": "Fanatic", "마녀": "Witch",
      "과학자": "Scientist", "사기꾼": "Swindler", "청부업자": "Hitman", "대부": "Godfather", "자경단원": "Vigilante",
      "요원": "Agent", "형사": "Inspector", "예언자": "Prophet", "판사": "Judge", "간호사": "Nurse", "마술사": "Magician",
      "해커": "Hacker", "심리학자": "Psychologist", "용병": "Mercenary", "공무원": "Official", "파파라치": "Paparazzi",
      "최면술사": "Hypnotist", "점쟁이": "Fortune teller"}
TEAM_EN = {TOWN: "Citizen team", MAFIA: "Mafia team", CULT: "Cult team"}

GAME_ROLES = {
    SIMPLE: ["시민", "마피아", "경찰", "의사"],
    COMPLEX: [r.name for r in ROLES.values()],
}
PLAYER_RANGE = {SIMPLE: (4, 12), COMPLEX: (4, 16)}  # fewer than 4 is refused
DEFAULT_PLAYERS = {SIMPLE: 7, COMPLEX: 10}
# slots per player count: 마피아, 보조, 경찰 계열, 의사, 특수, 시민
COMPLEX_SLOTS = {4: (1, 0, 1, 1, 1, 0), 5: (1, 0, 1, 1, 2, 0), 6: (1, 1, 1, 1, 2, 0), 7: (1, 1, 1, 1, 3, 0), 8: (2, 1, 1, 1, 3, 0), 9: (2, 1, 1, 1, 4, 0),
                 10: (2, 1, 1, 1, 5, 0), 11: (3, 1, 1, 1, 5, 0), 12: (3, 1, 1, 1, 5, 1), 13: (3, 2, 1, 1, 6, 0),
                 14: (3, 2, 1, 1, 6, 1), 15: (4, 2, 1, 1, 7, 0), 16: (4, 2, 1, 1, 7, 1)}


def simple_lineup(n: int) -> dict[str, int]:
    m = 1 if n <= 6 else 2 if n <= 9 else 3
    return {"마피아": m, "경찰": 1, "의사": 1, "시민": n - m - 2}


def pool_roles(pool: str = "classic", enabled: list[str] | None = None) -> list[str]:
    """Roles a slot may draw. The cult only comes through the 교주팀 setting."""
    roles = [r.name for r in ROLES.values() if r.team != CULT]
    if enabled:
        return [r for r in roles if r in enabled]
    return [r for r in roles if ROLES[r].classic or pool == "full"]


def draw_lineup(game: str, n: int, rng: random.Random, pool: str = "classic", enabled: list[str] | None = None,
                fixed: list[str] | None = None, cult: bool = False) -> list[str]:
    """The roles for n seats. `fixed` roles (lobby choices) take their slot first. With the 교주팀 setting
    (9 players or more) 교주 takes one 특수 slot, and at 12 or more 광신도 one more."""
    lo, hi = PLAYER_RANGE[game]
    if not lo <= n <= hi:
        raise ValueError(f"{n} players is outside {lo}..{hi}")
    if game == SIMPLE:
        return [r for r, c in simple_lineup(n).items() for _ in range(c)]
    counts = dict(zip((SLOT_MAFIA, SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL, SLOT_CITIZEN), COMPLEX_SLOTS[n]))
    allowed = pool_roles(pool, enabled)
    out: list[str] = []
    for r in fixed or []:
        counts[ROLES[r].slot] -= 1
        out.append(r)
    if out.count("연인") % 2 == 1:  # lovers come in pairs
        counts[SLOT_SPECIAL] -= 1
        out.append("연인")
    if cult and n >= 9:
        for r, at in (("교주", 9), ("광신도", 12)):
            if n >= at and r not in out:
                counts[SLOT_SPECIAL] -= 1
                out.append(r)
    for slot in (SLOT_MAFIA, SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL, SLOT_CITIZEN):
        need = counts[slot]
        if slot == SLOT_MAFIA:
            out += ["마피아"] * max(0, need)
            continue
        if slot == SLOT_CITIZEN:
            out += ["시민"] * max(0, need)
            continue
        choices = [r for r in allowed if ROLES[r].slot == slot and r not in out]
        rng.shuffle(choices)
        while need > 0:
            if not choices:
                out.append("시민")
                need -= 1
                continue
            r = choices.pop()
            if r == "연인":
                if need < 2:
                    continue
                out += ["연인", "연인"]
                need -= 2
            else:
                out.append(r)
                need -= 1
    return out[:n]


def team_of(role: str) -> str:
    return ROLES[role].team


def guess_options(game: str, present: list[str] | None = None) -> list[str]:
    """What a ledger row may guess: the roles that can exist in this game."""
    roles = GAME_ROLES[SIMPLE] if game == SIMPLE else (sorted(set(present)) if present else GAME_ROLES[COMPLEX])
    return list(roles) + ["모름"]
