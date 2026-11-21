"""English for the god powers' messages: what the players meet, the god's own record lines, the
rule and the 계시 block in the system prompt. Kept apart from en.py for size; en.py merges it into EN_TEXT."""
from __future__ import annotations

EN_GOD: dict[str, str] = {
    # the rule and the system prompt block
    "신: 이 판에는 신이 끼어들 수 있다. 신은 관전자일 수도 있고 참가자 가운데 한 명일 수도 있으며, 누가 신인지는 "
    "아무도 모른다. 신이 한 일은 모두 「신」이 한 것으로만 알려진다.":
        "God: a god may step into this game. The god may be a spectator or one of the players, and nobody knows who. "
        "Everything the god does is known only as done by \"God\".",
    "신의 계시": "God's revelation",
    "신이 너에게만 내린 지침이다. 게임 규칙과 같은 무게로 따른다. 신이 거둘 때까지 계속 따른다. 신이 누구인지는 모른다.":
        "A directive the god gave you alone. Follow it with the same weight as the game rules, until the god lifts it. "
        "You do not know who the god is.",
    # lines in a player's history
    "신의 공지: {text}": "God's announcement: {text}",
    "신의 질문(너에게만, 답은 신만 본다): {text}": "God's question (to you alone; only the god sees your answer): {text}",
    "(신에게 한 답) {text}": "(your answer to the god) {text}",
    "신이 너에게 질문했다(기록의 마지막 「신의 질문」). say에 신에게 할 답을 쓴다. 이 답은 신만 보고 다른 참가자는 아무도 보지 못한다.":
        "The god asked you a question (the last \"God's question\" in the log). Write your answer to the god in say. "
        "Only the god sees it; no other player does.",
    "신에게만 하는 답. 다른 참가자는 못 본다": "your answer to the god only; no other player sees it",
    "(답하지 않음)": "(no answer)",
    "신이 계시를 거뒀다. 이제 따르지 않아도 된다: {text}": "The god lifted a revelation. You no longer have to follow it: {text}",
    "신이 알립니다. {name}님의 직업은 {role}입니다.": "The god announces: {name} is the {role}.",
    "신이 알립니다. {name}님의 정체는 {who}입니다.": "The god announces: {name} is {who}.",
    "하늘에서 벼락이 떨어졌습니다.": "Lightning struck from the sky.",
    "신의 천벌로 {name}님이 죽었습니다.": "{name} died by the god's wrath.",
    "신의 뜻으로 {name}님이 살아 돌아왔습니다.": "By the god's will, {name} came back to life.",
    "신이 네 직업을 바꿨다. 이제 너는 {role:이다/다}.": "The god changed your role. You are now the {role}.",
    "신이 네 직업을 다른 사람과 맞바꿨다. 이제 너는 {role:이다/다}.": "The god swapped your role with someone else's. You are now the {role}.",
    "신이 너를 침묵시켰다. {n}번째 낮에는 말할 수 없다.": "The god silenced you. You cannot speak on day {n}.",
    "신이 너의 투표권을 빼앗았다. {n}번째 낮에는 투표할 수 없다.": "The god took your vote. You cannot vote on day {n}.",
    "신이 {name}님을 사면했습니다. 이번에는 처형되지 않습니다.": "The god pardoned {name}. There is no execution this time.",
    "신의 사면으로 {name}님은 처형되지 않았습니다.": "Pardoned by the god, {name} was not executed.",
    "신이 이번 투표를 없던 일로 했습니다. 다시 투표합니다.": "The god threw out this vote. Everyone votes again.",
    "신이 남은 발언 차례를 {n}번 늘렸습니다. 이제 {left}번입니다.": "The god added {n} turns to speak. {left} are left.",
    "신이 남은 발언 차례를 {n}번 줄였습니다. 이제 {left}번입니다.": "The god took away {n} turns to speak. {left} are left.",
    # the god's own record lines (god view and saved record only)
    "{name}님에게 계시: {text}": "Revelation to {name}: {text}",
    "{name}님의 계시를 거뒀습니다: {text}": "Lifted {name}'s revelation: {text}",
    "{by}님 이름으로 {name}님에게 귓속말: {text}": "Whisper to {name} in {by}'s name: {text}",
    "{name}님의 입을 빌려: {text}": "Through {name}'s mouth: {text}",
    "{name}님에게 신의 질문: {text}": "God's question to {name}: {text}",
    "{name}님의 다음 능력 결과를 바꿉니다: 「{choice}」": "{name}'s next ability result will read: \"{choice}\"",
    "마피아입니다": "Mafia", "마피아가 아닙니다": "not Mafia",
    "{name}님의 직업({role})을 모두에게 알렸습니다.": "Told everyone {name}'s role ({role}).",
    "{name}님의 정체({who})를 모두에게 알렸습니다.": "Told everyone who {name} is ({who}).",
    "{name}님에게 천벌을 내렸습니다.": "Struck {name} down.",
    "{name}님을 되살렸습니다.": "Brought {name} back to life.",
    "오늘 밤 {name}님을 향한 공격은 모두 막힙니다.": "Every attack on {name} is stopped tonight.",
    "{name}님의 직업을 {old}에서 {role:으로/로} 바꿨습니다.": "Changed {name}'s role from {old} to {role}.",
    "{a}님({ra})과 {b}님({rb})의 직업을 맞바꿨습니다.": "Swapped the roles of {a} ({ra}) and {b} ({rb}).",
    "{name}님은 {n}번째 낮에 말할 수 없습니다.": "{name} cannot speak on day {n}.",
    "{name}님은 {n}번째 낮에 투표하지 못합니다.": "{name} cannot vote on day {n}.",
    "{name}님을 사면했습니다.": "Pardoned {name}.",
    "이번 투표를 없던 일로 하고 다시 투표합니다.": "Threw out this vote; everyone votes again.",
    "다음 발언은 {name}님입니다.": "{name} speaks next.",
    "남은 발언 차례 {a}번에서 {b}번으로.": "Turns left: from {a} to {b}.",
    "다음 단계로 넘어갑니다.": "Moved on to the next step.",
}
