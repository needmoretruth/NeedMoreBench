"""English for the full pool's and the cult's engine messages, kept apart from en.py for size."""
from __future__ import annotations

ABILITY_FULL = {
    "{t} 직업을 찾아봅니다": "looks up who is {t}", "아무 직업도 찾아보지 않았습니다": "looked up no role",
    "{t}님을 찾아갑니다": "visits {t}", "아무도 찾아가지 않았습니다": "visited nobody",
    "{t}님의 별을 봅니다": "reads the stars of {t}", "별을 보지 않았습니다": "read no stars",
    "{t}님을 포교합니다": "converts {t}", "아무도 포교하지 않았습니다": "converted nobody",
    "{t}님에게 주술을 겁니다": "casts a spell on {t}", "아무에게도 주술을 걸지 않았습니다": "cast no spell",
    "{t}님의 관상을 봅니다": "reads the faces of {t} and another", "관상을 보지 않았습니다": "read no faces",
    "{t}님을 확인합니다": "checks {t}", "아무도 확인하지 않았습니다": "checked nobody",
    "{t}님을 제거합니다": "takes out {t}", "아무도 제거하지 않았습니다": "took out nobody",
    "{t}님에게 트릭을 겁니다": "plays a trick on {t}", "아무에게도 트릭을 걸지 않았습니다": "played no trick",
    "{t}님에게 연락합니다": "reaches out to {t}", "아무에게도 연락하지 않았습니다": "reached out to nobody",
    "{t}님을 처단합니다": "executes {t}", "처단을 미뤘습니다": "held off the execution",
    "{t}님에게 저주를 겁니다": "curses {t}", "아무에게도 저주를 걸지 않았습니다": "cursed nobody",
    "{a}님({ra}), {b}님({rb}) 두 사람을 노립니다": "targets {a} ({ra}) and {b} ({rb})",
    "{name}님이 마피아인지 알아봅니다": "checks whether {name} is Mafia", "{name}님을 도청합니다": "wiretaps {name}",
    "{name}님을 주술에서 깨웁니다": "wakes {name} from the spell",
}

PRIVATE_FULL = {
    "{name}님 포교에 실패했다.": "Converting {name} failed.",
    "{name}님을 포교했다. {name}님의 직업은 {role:이다/다}.": "You converted {name}. {name} is the {role}.",
    "교주 {name}님에게 포교되어 교주 팀이 되었다. 이제 교주 팀이 이기면 너도 이긴다. 원래 직업 능력은 그대로 쓴다.":
        "Cult leader {name} converted you: you are on the cult team now and win when it wins. You keep your role's ability.",
    "{by}님이 {name}님을 포교했습니다.": "{by} converted {name}.",
    "교주가 죽어 포교를 이어받았다. 홀수 번째 밤마다 한 명을 포교한다.": "The Cult leader died and you took over: convert one person every odd night.",
    "{name}님은 교주가 아니다.": "{name} is not the Cult leader.",
    "{name}님이 교주다. 교주와 이어졌다.": "{name} is the Cult leader. You are linked now.",
    "광신도 {name}님이 너를 찾아 이어졌다.": "The Fanatic {name} found you; you are linked now.",
    "교주를 이어받아 홀수 번째 밤마다 포교한다.": "You took over from the Cult leader and convert every odd night.",
    "투표로 처형될 때 한 번 살아남는다.": "You survive being executed by vote once.",
    "처형을 이미 한 번 피했다.": "You have already escaped an execution once.",
    "{line} 네가 직업을 아는 시민: {name}님.": "{line} The citizen whose role you know: {name}.",
    "둘 다 맞히지 못해 아무도 죽이지 않았다.": "You did not get both right, so nobody dies.",
    "둘 다 맞혔다. {a}님과 {b}님을 죽인다.": "Both right. {a} and {b} will die.",
    "두 번째 밤부터 두 사람과 그 직업을 맞혀 죽일 수 있다.": "From the second night you can kill two people by naming their roles right.",
    "마피아와 접선했다. 마피아의 공격은 의사의 치료와 직업 특성을 무시한다.": "You have contacted the Mafia. The mafia attack ignores the Doctor and role traits.",
    "세 번째 밤에 마피아와 접선한다.": "You contact the Mafia on the third night.",
    "{name}님을 개구리로 만들었다. 다음 밤이 올 때까지 그 사람은 직업 능력이 없다.": "You turned {name} into a frog. They have no role ability until the next night.",
    "마녀의 저주로 개구리가 되었다. 다음 밤이 올 때까지 직업 능력이 없다.": "The Witch's curse turned you into a frog. You have no role ability until the next night.",
    "마녀 {by}님이 {name}님을 개구리로 만들었습니다.": "Witch {by} turned {name} into a frog.",
    "되살아났다. 다시 죽으면 돌아오지 못한다.": "You came back. If you die again you will not return.",
    "한 번 되살아났다. 다시 죽으면 돌아오지 못한다.": "You have come back once. If you die again you will not return.",
    "죽으면 다음 밤이 끝날 때 한 번 되살아난다.": "When you die you come back once, when the next night ends.",
    "{name}님의 직업은 {role:이다/다}. 너는 이 직업인 척할 수 있다.": "{name} is the {role}. You can pose as this role.",
    "위장꾼 {name}님이 처형을 한 번 피했습니다.": "Masquerader {name} escaped an execution once.",
    "연락관 {name}님과 이어졌다. 같은 팀이다.": "Liaison {name} reached you. You are on the same team.",
    "{n}번째 낮까지 살아 있으면 네 팀이 이긴다.": "If you are alive on day {n}, your team wins.",
    "정체를 드러냈다. 찬반은 너 혼자 정한다.": "You are revealed. You alone decide verdicts.",
    "{name}님은 의사가 아니다.": "{name} is not the Doctor.",
    "{name}님이 의사다. 서로를 알게 되었다.": "{name} is the Doctor. You now know each other.",
    "조수 {name}님이 너를 찾아왔다.": "Assistant {name} came to you.",
    "환술사 {by}님 대신 {name}님이 죽습니다.": "{name} dies in place of Illusionist {by}.",
    "공격받았지만 트릭을 건 {name}님이 대신 죽었다.": "You were attacked, but {name}, whom you tricked, died in your place.",
    "도청 결과: {name}님의 직업은 {role}입니다.": "Wiretap result: {name} is the {role}.",
    "조사 결과: {name}님은 마피아입니다. 밤에 처단할 수 있다.": "Result: {name} is Mafia. You can execute them at night.",
    "마피아로 밝혀낸 {name}님을 밤에 처단할 수 있다.": "You can execute {name}, whom you found to be Mafia, at night.",
    "조사를 이미 썼다.": "You have used your check.",
    "낮 투표 때 한 번, 한 명이 마피아인지 알아볼 수 있다.": "Once, at a day vote, you can check whether one person is Mafia.",
    "정보: {name}님은 시민 팀 {role:이다/다}.": "Information: {name} is the {role}, on the citizen team.",
    "{name}님과는 이어지지 않았다.": "You did not link up with {name}.",
    "{name}님과 이어졌다. {name}님은 {role:이다/다}.": "You linked up with {name}. {name} is the {role}.",
    "기록 결과: {role:은/는} {names}님이다.": "Records: the {role} is {names}.",
    "기록 결과: 살아 있는 사람 가운데 {role:은/는} 없다.": "Records: no living player is the {role}.",
    "소문: {name}님의 직업은 {role:이라고/라고} 한다.": "Gossip: {name} is said to be the {role}.",
    "{name}님을 깨웠다. 직업은 알 수 없었다.": "You woke {name}. Their role stays unknown.",
    "{name}님을 깨웠다. {name}님의 직업은 {role:이다/다}.": "You woke {name}. {name} is the {role}.",
    "주술에 걸린 사람: {names}": "Under your spell: {names}",
    "점괘: {name}님의 직업은 {role:이다/다}.": "Reading: {name} is the {role}.",
    "점괘: {name}님의 직업은 {a}, {b} 가운데 하나다.": "Reading: {name} is either the {a} or the {b}.",
    "둘째 사람을 고르지 않아 관상을 보지 못했다.": "You named no second person, so you read no faces.",
    "관상 결과: {a}님과 {b}님은 같은 팀이다.": "Faces: {a} and {b} are on the same team.",
    "관상 결과: {a}님과 {b}님은 다른 팀이다.": "Faces: {a} and {b} are on different teams.",
    "너의 의뢰인은 {name}님이다. 의뢰인이 밤에 죽으면 그 뒤 밤마다 한 명을 죽일 수 있다.":
        "Your client is {name}. If your client dies at night, from then on you may kill one person each night.",
    "의뢰인 {name}님이 밤에 죽었다. 이제 밤마다 한 명을 죽일 수 있다.": "Your client {name} died at night. Now you may kill one person each night.",
    "의뢰인이 죽어 밤마다 한 명을 죽일 수 있다.": "Your client is dead: you may kill one person each night.",
    "너의 의뢰인: {name}님.": "Your client: {name}.",
    "교주 팀이다. 아직 교주가 누군지 모른다.": "You are on the cult team. You do not know the Cult leader yet.",
    "교주 팀이다. 같은 교주 팀: {names}": "You are on the cult team. Your cult: {names}",
    "교주 팀이다. 교주: {name}": "You are on the cult team. Cult leader: {name}",
}

TASKS_FULL = {
    "밤이다.": "It is night.",
    "포교할 사람 한 명을 고른다. 마피아 팀, 부활술사, 이미 교주 팀인 사람은 포교되지 않는다.":
        "Pick one person to convert. The mafia team, the Reviver and anyone already in a cult cannot be converted.",
    "짝수 번째 밤이라 포교할 수 없다.": "It is an even night, so you cannot convert.",
    "say에 쓴 말은 교주 팀({names})에게 간다. 그들은 답하지 못한다. 없으면 빈 문자열.":
        "What you write in say goes to your cult ({names}). They cannot reply. Leave it empty for nothing.",
    "밤이다. 한 명을 골라 교주인지 확인한다. 교주면 교주와 이어진다.": "It is night. Pick one person to check for the Cult leader. If it is, you are linked.",
    "밤이다. 두 사람과 그 직업을 맞히면 둘 다 죽인다. 먼저 한 사람과 그 직업을 적는다. 적은 사람이 마피아면 죽이지 않고 접선한다. 쓰지 않으려면 {none}.":
        "It is night. Name two people and their roles; if both are right, both die. First write one person and their role. "
        "Naming a Mafia makes contact instead of killing. To pass, {none}.",
    "role: 그 사람의 직업이라고 보는 것.": "role: the role you think that person has.",
    "두 번째 사람과 그 직업을 적는다.": "Write the second person and their role.",
    "밤이다. 개구리로 만들 사람 한 명을 고른다. 그 사람은 다음 밤이 올 때까지 직업 능력이 없다. 고른 사람이 마피아면 개구리로 만들지 않고 접선한다.":
        "It is night. Pick one person to turn into a frog: they have no role ability until the next night. Picking a Mafia makes contact instead.",
    "밤이다. 한 명을 찾아간다. 의사면 둘이 서로를 알게 된다.": "It is night. Visit one person. If they are the Doctor, you get to know each other.",
    "밤이다. 의사가 없으니 오늘 밤 살릴 사람 한 명을 고른다. 너 자신도 된다.":
        "It is night. There is no Doctor, so pick one person to save tonight. You may pick yourself.",
    "밤이다. 트릭을 걸 사람 한 명을 고른다. 오늘 밤 네가 공격받으면 그 사람이 대신 죽는다.":
        "It is night. Pick one person to trick. If you are attacked tonight, they die in your place.",
    "tap: 밤이 될 때 직업을 알아낼 사람. 안 하려면 \"{none}\".": "tap: the person whose role you learn when night falls. To skip, \"{none}\".",
    "check: 마피아인지 알아볼 사람(게임에서 한 번). 마피아면 그 뒤 밤에 죽일 수 있다. 아끼려면 \"{none}\".":
        "check: the person to check for Mafia (once a game). If Mafia, you may kill them at a later night. To save it, \"{none}\".",
    "밤이다. 마피아로 밝혀낸 {name}님을 처단할 수 있다. 미루려면 {none}.": "It is night. You can execute {name}, whom you found to be Mafia. To wait, {none}.",
    "밤이다. 연락할 사람 한 명을 고른다. 같은 팀이면 둘이 서로의 직업을 알게 된다.":
        "It is night. Pick one person to reach out to. If you are on the same team, you both learn each other's role.",
    "밤이다. 주술을 걸 사람 한 명을 고른다.": "It is night. Pick one person to put under a spell.",
    "wake: 주술에서 깨울 사람. 시민 팀이 아니면 직업을 알게 된다. 안 깨우려면 \"{none}\".":
        "wake: the person to wake from the spell. If they are not on the citizen team, you learn their role. To skip, \"{none}\".",
    "밤이다. 한 명을 고르면 그 사람의 직업과, 그와 다른 팀인 누군가의 직업이 섞여 두 개로 나온다.":
        "It is night. Pick one person; you get two roles in mixed order, theirs and that of someone on a different team.",
    "밤이다. 두 사람을 고르면 둘이 같은 팀인지 다른 팀인지 알게 된다. 첫 사람은 target, 둘째는 second에 적는다.":
        "It is night. Pick two people and learn whether they are on the same team. Write the first in target and the second in second.",
    "second: 첫 사람과 견줄 둘째 사람.": "second: the person to compare with the first.",
    "밤이다. 죽일 사람 한 명을 고른다. 안 죽이려면 {none}.": "It is night. Pick one person to kill. To kill nobody, {none}.",
    "밤이다. 직업 하나를 적으면 지금 그 직업을 가진 사람을 알게 된다.": "It is night. Write one role and learn who has it now.",
}

PUBLIC_FULL = {
    "불사신 {name}님이 되살아났습니다.": "Undying {name} came back to life.",
    "배심장 {name}님의 선택대로 결과가 바뀌었습니다.": "The result follows Foreman {name}'s choice.",
    "배심장 {name}님이 찬반 결과를 뒤집었습니다. 이제 찬반은 배심장 혼자 정합니다.":
        "Foreman {name} overturned the verdict. From now on the Foreman alone decides verdicts.",
    "{role} {name}님이 {n}번째 낮까지 살아남았습니다": "{role} {name} survived to day {n}",
    "교주 팀이 산 사람의 절반 이상이 되었습니다": "The cult team is half of the living or more",
    "종소리가 울렸습니다. 누군가 교주 팀이 되었습니다.": "A bell rang. Someone has joined a cult.",
    "(교주의 말) {by}: {text}": "(Cult leader's word) {by}: {text}",
    "교주 팀: 교주 팀 수가 나머지 이상이 되면 교주 팀이 이긴다. 포교된 사람은 원래 팀이 아니라 교주 팀으로 이긴다. 여러 팀이 함께 조건을 채우면 마피아 팀, 교주 팀, 시민 팀 순서로 앞선다.":
        "Cult team: the cult team wins when it is at least as many as everyone else. A converted player wins with the cult, "
        "not their first team. If several teams qualify at once, the mafia team comes first, then the cult, then the citizen team.",
}

EN_FULL: dict[str, str] = {**ABILITY_FULL, **PRIVATE_FULL, **TASKS_FULL, **PUBLIC_FULL}
