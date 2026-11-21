"""Role data for both games and the line-up per player count.

A role is data: its team, its slot (what kind of seat it fills), what the player is told, and the name of its
ability module in `nmb.engine.abilities`. The engine never names a role; it asks the ability.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

TOWN, MAFIA, CULT = "시민", "마피아", "교주"
TEAM_LABEL = {TOWN: "시민 팀", MAFIA: "마피아 팀", CULT: "교주 팀"}
SIMPLE, COMPLEX = "simple", "complex"
GAME_TITLE = {SIMPLE: "단순 마피아", COMPLEX: "복잡한 마피아"}
SLOT_MAFIA, SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL, SLOT_CITIZEN = "마피아", "보조", "경찰 계열", "의사", "특수", "시민"
SLOTS = (SLOT_MAFIA, SLOT_HELPER, SLOT_POLICE, SLOT_DOCTOR, SLOT_SPECIAL, SLOT_CITIZEN)


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
    Role("야수", MAFIA, SLOT_HELPER, "beast", "마피아 보조. 처음엔 마피아가 누군지 모른다. 밤마다 한 명을 찍는다. 찍은 사람이 마피아에게 죽으면 길들여져 접선하고, 그 뒤로 마피아 회의에서 죽일 사람을 같이 고른다. 마피아의 공격으로는 죽지 않는다."),
    Role("유혹자", MAFIA, SLOT_HELPER, "seducer", "마피아 보조. 처음엔 마피아가 누군지 모른다. 낮 투표에서 네가 표를 준 사람을 유혹한다. 유혹당한 사람은 그날 밤 능력을 못 쓰고 다음 낮에 말을 못 한다. 마피아를 유혹하면 접선한다."),
    Role("모방자", MAFIA, SLOT_HELPER, "copycat", "마피아 보조. 처음엔 마피아가 누군지 모른다. 투표 때 한 사람을 골라 그 사람의 능력을 따라 해 그날 밤에 쓴다. 마피아의 능력을 따라 하면 마피아와 접선한다."),
    Role("방패병", TOWN, SLOT_SPECIAL, "shieldbearer", "마피아의 공격을 한 번 버틴다(모두에게 알려진다). 마피아 팀이 너를 조사하면 조사한 사람이 누군지 알게 된다."),
    Role("시장", TOWN, SLOT_SPECIAL, "mayor", "투표로 처형되지 않는다. 투표에서 두 표로 센다."),
    Role("영매", TOWN, SLOT_SPECIAL, "medium", "죽은 사람들의 대화를 듣고 밤에 그들과 말한다. 밤마다 죽은 사람 한 명의 직업을 알아내고 성불시킨다(그 사람은 더 말하지 못한다)."),
    Role("연인", TOWN, SLOT_SPECIAL, "lover", "연인은 두 명이다. 밤에 둘만 대화한다. 둘 다 살아 있을 때 한 명이 마피아에게 지목되면 다른 한 명이 대신 죽는다."),
    Role("협박꾼", TOWN, SLOT_SPECIAL, "blackmailer", "밤에 한 명을 골라 다음 날 그 사람의 투표권을 빼앗는다."),
    Role("폭로자", TOWN, SLOT_SPECIAL, "exposer", "게임에서 한 번, 두 번째 밤부터 한 명의 직업을 알아내고 다음 아침 모두에게 폭로한다."),
    Role("미행꾼", TOWN, SLOT_SPECIAL, "shadow", "밤에 한 명을 골라 그 사람이 그 밤 누구에게 능력을 썼는지 알아낸다."),
    Role("계승자", TOWN, SLOT_SPECIAL, "heir", "첫날 밤 마피아에게 죽은 사람의 직업을 물려받는다."),
    Role("폭탄마", TOWN, SLOT_SPECIAL, "bomber", "밤에 한 명을 찍는다. 찍은 사람이 마피아일 때 밤에 마피아에게 죽으면 그 마피아와 함께 죽는다. 투표로 처형될 때 찍은 사람이 적이면 함께 죽는다."),
    # the user's own two
    Role("복수자", TOWN, SLOT_SPECIAL, "avenger", "밤에 마피아 팀에게 죽으면 마지막 총을 쏴, 마피아 회의에서 너를 처음 고른 사람을 함께 데려간다. 미리 고를 것은 없다. 의사가 살리면 아무 일도 없다."),
    Role("사냥꾼", TOWN, SLOT_SPECIAL, "hunter", "투표로 처형되면 찬반이 끝난 뒤 살아 있는 사람 한 명을 골라 함께 데려간다. 누구든 되고 모두에게 알려진다. 다른 이유로 죽으면 쏘지 못한다."),
    Role("부활술사", TOWN, SLOT_SPECIAL, "reviver","게임에서 한 번, 밤에 죽은 사람 한 명을 되살린다(아침에 모두에게 알려진다). 성불한 사람은 못 살린다. 교주에게 포교되지 않는다."),
    # 복잡한 마피아, the rest of the full pool
    Role("마녀", MAFIA, SLOT_HELPER, "witch", "마피아 보조. 처음엔 마피아가 누군지 모른다. 밤마다 한 명을 개구리로 만든다. 개구리는 다음 밤이 올 때까지 직업 능력이 없다(투표권 두 배 같은 특성도 없다). 마피아를 고르면 개구리로 만들지 않고 접선한다.", False),
    Role("불사신", MAFIA, SLOT_HELPER, "undying", "마피아 보조. 처음엔 마피아가 누군지 모른다. 죽으면 마피아와 접선하고, 다음 밤이 끝날 때 한 번 되살아난다(모두에게 알려진다).", False),
    Role("위장꾼", MAFIA, SLOT_HELPER, "masquerader", "마피아 보조. 처음엔 마피아가 누군지 모른다. 시작할 때 시민 팀 한 명의 직업을 알게 되고 그 직업인 척한다. 투표로 처형될 때 한 번 살아남고 접선한다. 그 시민이 처형되어도 접선한다.", False),
    Role("암살자", MAFIA, SLOT_HELPER, "assassin", "마피아 보조. 처음엔 마피아가 누군지 모른다. 두 번째 밤부터 밤마다 두 사람과 그 직업을 적는다. 둘 다 맞히면 둘 다 죽인다. 적은 사람이 마피아면 접선한다.", False),
    Role("대부", MAFIA, SLOT_HELPER, "godfather", "마피아 보조. 처음엔 마피아가 누군지 모른다. 세 번째 밤에 마피아와 접선한다. 그 뒤로 마피아 회의에서 죽일 사람을 같이 고르고, 마피아의 공격은 의사의 치료와 직업 특성을 무시한다.", False),
    Role("자경단원", TOWN, SLOT_POLICE, "vigilante", "게임에서 한 번, 낮 투표 때 한 명이 마피아인지 알아낸다. 마피아였다면 그 뒤 밤에 그 사람을 죽일 수 있다.", False),
    Role("정보원", TOWN, SLOT_POLICE, "informant", "밤이 끝날 때마다 아직 모르는 시민 팀 한 명의 직업을 알게 된다.", False),
    Role("연락관", TOWN, SLOT_POLICE, "liaison", "밤에 한 명을 고른다. 같은 팀이면 둘이 서로의 직업을 알게 된다.", False),
    Role("기수", TOWN, SLOT_SPECIAL, "flagbearer", "네 번째 낮까지 살아 있으면 시민 팀이 이긴다.", False),
    Role("배심장", TOWN, SLOT_SPECIAL, "foreman", "찬반 결과가 네 선택과 다르면 정체를 드러내고 결과를 네 선택대로 뒤집는다. 그 뒤로 찬반은 너 혼자 정한다.", False),
    Role("조수", TOWN, SLOT_SPECIAL, "assistant", "밤에 한 명을 고른다. 의사를 고르면 둘이 서로를 알게 된다. 의사가 죽은 뒤에는 밤마다 고른 사람을 마피아의 공격에서 살린다.", False),
    Role("환술사", TOWN, SLOT_SPECIAL, "illusionist", "밤에 한 명에게 트릭을 건다. 그 밤 네가 공격받으면 트릭을 건 사람이 대신 죽는다.", False),
    Role("도청꾼", TOWN, SLOT_SPECIAL, "wiretapper", "낮 투표 때 한 명을 고르면 밤이 될 때 그 사람의 직업을 알게 된다.", False),
    Role("관상가", TOWN, SLOT_SPECIAL, "face_reader", "밤에 두 명을 고르면 둘이 같은 팀인지 다른 팀인지 알게 된다.", False),
    Role("해결사", TOWN, SLOT_SPECIAL, "fixer", "시작할 때 시민 팀 한 명이 의뢰인으로 정해진다. 의뢰인이 밤에 죽으면 그 뒤 밤마다 한 명을 죽일 수 있다.", False),
    Role("기록관", TOWN, SLOT_SPECIAL, "archivist", "밤에 직업 하나를 적으면 그 직업을 가진 사람을 알게 된다.", False),
    Role("소문꾼", TOWN, SLOT_SPECIAL, "gossip", "아침마다 시민 팀이 알아낸 직업 정보 가운데 하나를 받는다.", False),
    Role("주술사", TOWN, SLOT_SPECIAL, "enchanter", "밤에 한 명에게 주술을 건다. 낮 투표 때 주술에 걸린 사람 한 명을 깨우면, 시민 팀이 아닌 사람은 직업을 알게 된다.", False),
    Role("점성가", TOWN, SLOT_SPECIAL, "astrologer", "밤에 한 명을 고르면 그 사람의 직업과 그와 다른 팀인 누군가의 직업이 섞여 두 개로 나온다.", False),
    # 교주팀 (setting)
    Role("교주", CULT, SLOT_SPECIAL, "cult_leader", "홀수 번째 밤마다 한 명을 포교한다(마피아 팀과 부활술사는 안 된다). 포교한 사람의 직업을 알게 되고, 그 사람은 교주 팀이 된다. 포교에 성공하면 모두에게 종소리가 들린다. 밤마다 교주 팀에게 한마디를 보낼 수 있다(교주 팀은 답하지 못한다).", False),
    Role("광신도", CULT, SLOT_SPECIAL, "fanatic", "교주 팀. 처음엔 교주가 누군지 모른다. 밤에 한 명을 확인해 교주를 찾으면 교주와 이어진다. 교주가 죽으면 포교를 이어받는다.", False),
]}

# English names: the interface's source strings (translated back by gettext) and the English dialogue
EN = {"시민": "Citizen", "마피아": "Mafia", "경찰": "Police", "의사": "Doctor", "스파이": "Spy", "야수": "Beast",
      "유혹자": "Seducer", "모방자": "Copycat", "방패병": "Shieldbearer", "시장": "Mayor", "영매": "Medium", "연인": "Lover",
      "협박꾼": "Blackmailer", "폭로자": "Exposer", "미행꾼": "Shadow", "계승자": "Heir", "폭탄마": "Bomber",
      "복수자": "Avenger", "사냥꾼": "Hunter", "부활술사": "Reviver", "모름": "Unknown", "교주": "Cult leader", "광신도": "Fanatic", "마녀": "Witch",
      "불사신": "Undying", "위장꾼": "Masquerader", "암살자": "Assassin", "대부": "Godfather", "자경단원": "Vigilante",
      "정보원": "Informant", "연락관": "Liaison", "기수": "Flagbearer", "배심장": "Foreman", "조수": "Assistant", "환술사": "Illusionist",
      "도청꾼": "Wiretapper", "관상가": "Face reader", "해결사": "Fixer", "기록관": "Archivist", "소문꾼": "Gossip",
      "주술사": "Enchanter", "점성가": "Astrologer"}
TEAM_EN = {TOWN: "Citizen team", MAFIA: "Mafia team", CULT: "Cult team"}

# Names used before gave NMB its own: games, presets and settings saved with them load under the new ones
OLD_NAMES = {"짐승인간": "야수", "마담": "유혹자", "도둑": "모방자", "군인": "방패병", "정치인": "시장", "건달": "협박꾼",
             "기자": "폭로자", "사립탐정": "미행꾼", "도굴꾼": "계승자", "테러리스트": "폭탄마", "성직자": "부활술사",
             "과학자": "불사신", "사기꾼": "위장꾼", "청부업자": "암살자", "요원": "정보원", "형사": "연락관", "예언자": "기수",
             "판사": "배심장", "간호사": "조수", "마술사": "환술사", "해커": "도청꾼", "심리학자": "관상가", "용병": "해결사",
             "공무원": "기록관", "파파라치": "소문꾼", "최면술사": "주술사", "점쟁이": "점성가"}


def canon_role(role: str | None) -> str | None:
    return OLD_NAMES.get(role, role) if role else role


def canon_tree(o: Any) -> Any:
    """Every string value that is exactly an old role name, inside dicts and lists, becomes the new name.
    Free text (what was said, morning lines) stays as it was written."""
    if isinstance(o, str):
        return OLD_NAMES.get(o, o)
    if isinstance(o, list):
        return [canon_tree(x) for x in o]
    if isinstance(o, dict):
        return {k: (v if k in ("text", "say", "how_to_read") else canon_tree(v)) for k, v in o.items()}
    return o

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


CULT_FROM = {"교주": 9, "광신도": 12}  # the 교주팀 setting's seats by player count


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
                fixed: list[str] | None = None, cult: bool = False, slots: tuple[int, ...] | None = None) -> list[str]:
    """The roles for n seats. `fixed` roles (lobby choices) take their slot first. With the 교주팀 setting
    (9 players or more) 교주 takes one 특수 slot, and at 12 or more 광신도 one more. `slots` replaces the
    table's counts per kind (직접)."""
    lo, hi = PLAYER_RANGE[game]
    if not lo <= n <= hi:
        raise ValueError(f"{n} players is outside {lo}..{hi}")
    if game == SIMPLE:
        return [r for r, c in simple_lineup(n).items() for _ in range(c)]
    counts = dict(zip(SLOTS, slots or COMPLEX_SLOTS[n]))
    allowed = pool_roles(pool, enabled)
    out: list[str] = []
    for r in fixed or []:
        counts[ROLES[r].slot] -= 1
        out.append(r)
    if out.count("연인") % 2 == 1:  # lovers come in pairs
        counts[SLOT_SPECIAL] -= 1
        out.append("연인")
    if cult and n >= CULT_FROM["교주"]:
        for r, at in CULT_FROM.items():
            if n >= at and r not in out:
                counts[SLOT_SPECIAL] -= 1
                out.append(r)
    for slot in SLOTS:
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
