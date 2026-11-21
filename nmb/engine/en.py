"""English for the engine's messages: the dialogue language of an English game.

EN_TEXT maps each Korean template (the message key) to its English template with the same parameters and no
particle specs. EN_WORDS translates the words the engine uses as ids when they appear as parameters, and
EN_ANSWERS reads an English answer back to the id. `tests/test_engine_text.py` keeps EN_TEXT complete.
"""
from __future__ import annotations

from .roles import EN, GAME_TITLE, TEAM_EN, TEAM_LABEL

EN_WORDS: dict[str, str] = {
    **EN,
    **{TEAM_LABEL[t]: TEAM_EN[t] for t in TEAM_LABEL},
    **{GAME_TITLE[k]: v for k, v in (("simple", "Simple Mafia"), ("complex", "Complex Mafia"))},
    # steps of the day
    "소개": "Introductions", "아침": "Morning", "토론": "Discussion", "귓속말 시간": "Whisper time", "투표": "Vote",
    "최후의 반론": "Last defence", "찬반": "Verdict",
    # slot kinds
    "보조": "Helper", "경찰 계열": "Police kind", "특수": "Special",
    # answer words
    "찬성": "Yes", "반대": "No", "기권": "Abstain", "없음": "None", "연장": "Extend", "단축": "Shorten",
    # how a seat looks
    "사람": "Human", "알 수 없음": "Unknown", "미국": "United States", "중국": "China", "프랑스": "France",
    "이스라엘": "Israel", "한국": "South Korea", "일본": "Japan", "캐나다": "Canada",
}

# answers a model may write that are not the plain translation
EN_ANSWERS: dict[str, str] = {"yes": "찬성", "no": "반대", "abstain": "기권", "none": "없음", "extend": "연장",
                              "shorten": "단축", "unknown": "모름", "guilty": "찬성", "not guilty": "반대"}

ABILITY = {
    "{t}님에게 능력을 씁니다": "uses their ability on {t}", "아무에게도 능력을 쓰지 않습니다": "uses their ability on nobody",
    "{t}님을 찍습니다": "marks {t}", "아무도 찍지 않았습니다": "marked nobody",
    "{t}님을 협박합니다": "blackmails {t}", "아무도 협박하지 않았습니다": "blackmailed nobody",
    "{t}님을 지킵니다": "protects {t}", "아무도 지키지 않았습니다": "protected nobody",
    "{t}님을 폭로합니다": "exposes {t}", "폭로를 아꼈습니다": "saved the exposé",
    "{t}님을 성불시킵니다": "lays {t} to rest", "아무도 성불시키지 않았습니다": "laid nobody to rest",
    "{t}님을 조사합니다": "investigates {t}", "아무도 조사하지 않았습니다": "investigated nobody",
    "{t}님을 되살립니다": "revives {t}", "부활을 아꼈습니다": "saved the revival",
    "{t}님을 미행합니다": "follows {t}", "아무도 미행하지 않았습니다": "followed nobody",
    "{t}님의 직업을 알아봅니다": "looks into {t}'s role", "아무도 알아보지 않았습니다": "looked into nobody",
    "{t}님을 노립니다": "targets {t}", "아무도 노리지 않았습니다": "targeted nobody",
    "{role} {name}님이 {what}": "{role} {name} {what}",
    "아무도 유혹하지 않았습니다": "seduced nobody", "투표로 {name}님을 유혹합니다": "seduces {name} with the vote",
    "아무 능력도 따라 하지 않았습니다": "copied no ability", "{name}님의 능력을 따라 합니다": "copies {name}'s ability",
    "처형되면 {name}님을 함께 데려가려 합니다": "will take {name} along if executed",
    "처형되어도 아무도 데려가지 않기로 했습니다": "will take nobody along if executed",
    "{name}님을 함께 데려갑니다": "takes {name} along", "아무도 데려가지 않았습니다": "took nobody along",
}

PRIVATE = {
    "마피아와 접선했다. 마피아 팀: {mates}. 이제 마피아 회의에 낀다.": "You made contact with the mafia. Mafia team: {mates}. You now join the mafia meeting.",
    "{name}({role})": "{name} ({role})",
    "{who:이/가} 마피아 팀과 접선했다.": "{who} made contact with the mafia team.",
    "{who:이/가} 마피아와 접선했습니다.": "{who} made contact with the mafia.",
    "유혹자에게 유혹당했다. 오늘 밤 능력을 쓸 수 없고 {n}번째 낮에는 말할 수 없다.": "The Seducer seduced you. You cannot use your ability tonight and cannot speak on day {n}.",
    "유혹자 {by}님이 {name}님을 유혹했습니다.": "Seducer {by} seduced {name}.",
    "낮 투표에서 네가 표를 준 사람이 유혹당한다.": "Whoever you vote for in the day vote is seduced.",
    "steal: 능력을 따라 할 사람 한 명(오늘 밤 그 직업의 능력을 쓴다). 따라 하지 않으려면 \"{none}\".": "steal: one person whose ability you copy (you use that role's ability tonight). To copy nobody, \"{none}\".",
    "{name}님의 능력을 따라 했다. {name}님은 {role:이다/다}. 오늘 밤 그 능력을 쓴다.": "You copied {name}'s ability. {name} is the {role}. You use that ability tonight.",
    "오늘 밤 따라 한 {role} 능력을 쓴다.": "Tonight you use the copied {role} ability.",
    "투표 때 한 사람의 능력을 따라 할 수 있다.": "At the vote you may copy one person's ability.",
    "접선했다. 한 명을 더 조사할 수 있다.": "You made contact. You may investigate one more person.",
    "조사 결과: {name}님의 직업은 {role}입니다.": "Result: {name} is the {role}.",
    "{name}님이 너를 조사했다. {name}님은 마피아 팀이다.": "{name} investigated you. {name} is on the mafia team.",
    "길들여져 마피아와 접선했다. 마피아 회의에서 죽일 사람을 같이 고른다.": "You were tamed and made contact with the mafia. You choose the kill together in the mafia meeting.",
    "투표로 {name}님을 유혹했다.": "You seduced {name} with your vote.",
    "조사 결과: {name}님은 마피아입니다.": "Result: {name} is Mafia.",
    "조사 결과: {name}님은 마피아가 아닙니다.": "Result: {name} is not Mafia.",
    "{name}님을 협박했다. {name}님은 {n}번째 낮에 투표하지 못한다.": "You blackmailed {name}. {name} cannot vote on day {n}.",
    "협박꾼에게 협박당했다. {n}번째 낮에는 투표할 수 없다.": "The Blackmailer got to you. You cannot vote on day {n}.",
    "폭로할 사람: {name}님은 {role:이다/다}. 아침에 모두에게 알려진다.": "To expose: {name} is the {role}. Everyone learns it in the morning.",
    "폭로자가 밝혔습니다. {name}님의 직업은 {role}입니다.": "The Exposer reveals: {name} is the {role}.",
    "폭로를 이미 썼다.": "You have used your exposé.",
    "폭로는 두 번째 밤부터, 게임에서 한 번 쓸 수 있다.": "You can expose once per game, from the second night.",
    "추적 결과: {name}님은 오늘 밤 {on}님에게 능력을 썼다.": "You followed {name}: tonight they used their ability on {on}.",
    "추적 결과: {name}님은 오늘 밤 아무에게도 능력을 쓰지 않았다.": "You followed {name}: tonight they used no ability on anyone.",
    "첫날 밤 마피아에게 죽은 {name}님의 직업을 물려받았다. 이제 너는 {role:이다/다}.": "You inherited the role of {name}, killed by the mafia on the first night. You are now the {role}.",
    "첫날 밤 마피아에게 죽은 사람이 있으면 그 직업을 물려받는다.": "If the mafia kills someone on the first night, you inherit their role.",
    "방패병 {name}님이 마피아의 공격을 버텨냈습니다.": "Shieldbearer {name} withstood the mafia's attack.",
    "폭탄마 {by}님이 {name}님과 함께 죽었습니다.": "Bomber {by} died and took {name} with them.",
    "복수자 {by}님이 죽기 전에 쏜 총에 {name}님이 맞았습니다.": "Avenger {by} fired one last shot before dying and hit {name}.",
    "방패를 이미 썼다.": "Your shield is used up.",
    "마피아의 공격을 한 번 버틸 수 있다.": "You can withstand one mafia attack.",
    "사냥꾼 {by}님이 {name}님을 함께 데려갔습니다.": "Hunter {by} took {name} along.",
    "부활술사가 {name}님을 되살렸습니다.": "The Reviver brought {name} back to life.",
    "부활을 이미 썼다.": "You have used your revival.",
    "{name}님의 직업은 {role:이었다/였다}. {name}님을 성불시켰다.": "{name} was the {role}. You laid {name} to rest.",
    "영매가 너를 성불시켰다. 이제 죽은 사람 대화에서 말할 수 없다.": "The Medium laid you to rest. You can no longer speak in the chat of the dead.",
    "너의 연인은 {name}님이다. 밤마다 둘만 대화한다.": "Your lover is {name}. Each night the two of you talk alone.",
    "연인 {name}님이 {other}님을 대신해 죽었습니다.": "Lover {name} died in place of {other}.",
    "개구리에서 풀려났다. 다시 직업 능력을 쓸 수 있다.": "You are no longer a frog. You can use your ability again.",
    "유혹당해 오늘 밤 능력을 쓰지 못한다.": "You were seduced and cannot use your ability tonight.",
    "유혹당해 오늘 밤 능력을 쓰지 못했다.": "You were seduced and could not use your ability tonight.",
}

TASKS = {
    "밤이다. 오늘 밤 살릴 사람 한 명을 고른다. 그 사람이 마피아에게 공격받으면 살아난다. 너 자신도 된다.": "It is night. Choose one person to save tonight. If the mafia attacks them, they survive. You may choose yourself.",
    "밤이다. 직업을 알아낼 사람 한 명을 고른다. 고른 사람이 마피아면 접선하고 한 번 더 조사한다.": "It is night. Choose one person whose role you learn. If they are Mafia, you make contact and investigate once more.",
    "밤이다. 한 명을 찍는다. 찍은 사람이 마피아에게 죽으면 너는 길들여져 마피아와 접선한다.": "It is night. Mark one person. If the mafia kills them, you are tamed and make contact with the mafia.",
    "밤이다. 조사할 사람 한 명을 고른다. 마피아인지 아닌지 너만 알게 된다.": "It is night. Choose one person to investigate. Only you learn whether they are Mafia.",
    "밤이다. 폭로할 사람 한 명을 고르면 그 사람의 직업이 다음 아침 모두에게 공개된다. 게임에서 한 번만 된다. 아끼려면 {none}.": "It is night. Choose one person to expose and their role is revealed to everyone next morning. Once per game. To save it, {none}.",
    "밤이다. 한 명을 골라 그 사람이 오늘 밤 누구에게 능력을 썼는지 알아낸다.": "It is night. Choose one person and learn whom they used their ability on tonight.",
    "밤이다. 한 명을 찍는다. 찍은 사람이 마피아일 때 오늘 밤 네가 마피아에게 죽으면 그 사람도 함께 죽는다.": "It is night. Mark one person. If they are Mafia and the mafia kills you tonight, they die with you.",
    "take: 처형되면 함께 데려갈 사람. 그 사람이 적(마피아 팀)일 때만 함께 죽는다.": "take: the person you take along if you are executed. They die with you only if they are an enemy (mafia team).",
    "너는 투표로 처형되었다. 사냥꾼의 마지막 한 발로 살아 있는 사람 한 명을 골라 함께 데려갈 수 있다. 누구든 되고 모두에게 알려진다. 아무도 데려가지 않으려면 {none}.": "You were executed by vote. With the Hunter's last shot you may take one living person along. Anyone will do and everyone learns it. To take nobody, {none}.",
    "밤이다. 죽은 사람 한 명을 되살릴 수 있다. 게임에서 한 번만 된다. 아끼려면 {none}.": "It is night. You may bring one dead person back to life. Once per game. To save it, {none}.",
    "밤이다. 죽은 사람 한 명을 골라 직업을 알아내고 성불시킨다. 성불한 사람은 더 말하지 못한다.": "It is night. Choose one dead person: you learn their role and lay them to rest. Someone laid to rest speaks no more.",
    "밤이다. 한 명을 골라 내일 낮 그 사람의 투표권을 빼앗는다.": "It is night. Choose one person who cannot vote tomorrow.",
    "귓속말 시간이다. 네 차례다. 살아 있는 사람 한 명을 골라 귓속말을 한 번 보내거나, 보내지 않으려면 whispers를 빈 목록으로 둔다.": "It is whisper time and your turn. Send one whisper to one living person, or leave whispers as an empty list to send none.",
    "귓속말 답장 차례다. 너에게 귓속말을 보낸 사람({names})에게 한 번씩 답할 수 있다. 이것이 오늘 마지막 귓속말이다. 답하지 않아도 된다.": "Your turn to reply. You may answer each person who whispered to you ({names}) once. These are today's last whispers. You need not reply.",
    "투표 시간이다. 최후의 반론에 올릴 사람 한 명에게 투표한다. 자기 자신에게도 투표할 수 있고 기권도 된다. 가장 많이 받은 사람이 최후의 반론을 하고, 그다음 찬반으로 처형을 정한다. 최다 득표가 동점이면 바로 밤이 된다.": "Time to vote. Vote for one person to put up for the last defence. You may vote for yourself or abstain. Whoever gets the most votes gives the last defence, then the verdict decides the execution. If the top votes tie, night falls at once.",
    "소개 차례다. 모두에게 너를 소개한다. 네 직업을 사실대로 말하든, 거짓으로 말하든, 말하지 않든 자유다.": "Your turn to introduce yourself to everyone. You may tell your role truthfully, lie about it, or not mention it.",
    "최후의 반론이다. 너는 최다 득표로 처형 직전이다. 이번에는 2~4문장까지 말해도 된다. 찬반에서 찬성이 반대보다 적으면 살아남는다.": "Your last defence. You got the most votes and face execution. This time you may say 2 to 4 sentences. If Yes gets fewer votes than No in the verdict, you live.",
    "최후의 반론이지만 너는 오늘 말할 수 없다. 처형될 때를 대비한 선택만 한다.": "It is your last defence, but you cannot speak today. Make only the choice for your execution.",
    "찬반 투표다. {name}님을 처형할지 정한다. 찬성이 반대보다 많거나 같으면 처형된다. 기권은 반대로 센다.": "The verdict. Decide whether {name} is executed. If Yes gets at least as many votes as No, they are executed. Abstaining counts as No.",
    "토론 중이다. 네 차례다. 할 말이 없으면 say를 비워 침묵해도 된다.": "The discussion is on and it is your turn. If you have nothing to say, leave say empty to stay silent.",
    "마피아 회의다. 마피아 팀에게만 들린다. say는 마피아 팀에게만 하는 말이다.": "This is the mafia meeting. Only the mafia team hears it. say goes to the mafia team only.",
    "회의 {n}번째 바퀴다. 위의 회의 내용을 보고 말한다.": "Meeting round {n}. Speak with the meeting so far in mind.",
    "죽일 사람은 마피아가 정한다.": "The Mafia choose the kill.",
    "지금 네 선택: {name}. 바꾸거나 그대로 둔다.": "Your current choice: {name}. Change it or keep it.",
    "오늘 밤 죽일 사람을 target에 적는다. 살아 있는 누구든 된다(같은 마피아 팀이나 너 자신도). 회의는 차례대로 최대 {n}바퀴 돈다. 한 바퀴가 끝났을 때 죽일 사람을 고르는 모두의 선택이 같으면 회의가 끝나고, {n}바퀴가 지나도 갈리면 가장 많이 나온 사람, 같으면 먼저 말한 쪽의 선택으로 정해진다.": "Write tonight's kill in target. Any living person will do (a mafia teammate or yourself too). The meeting goes round in turn at most {n} times. When a round ends with everyone who picks the kill agreeing, the meeting ends; if they still differ after {n} rounds, the most picked person dies, and on a tie the earlier speaker's pick.",
    "연인 대화다({rnd}/{n}번째 바퀴). 연인 {name}님과 너만 듣는다. 하고 싶은 말이 없으면 say를 비운다.": "Lovers' talk (round {rnd} of {n}). Only you and your lover {name} hear it. If you have nothing to say, leave say empty.",
    "죽은 사람 대화다({rnd}/{n}번째 바퀴). 영매인 너와 죽은 사람들({names})만 듣는다. 하고 싶은 말이 없으면 say를 비운다.": "Chat of the dead (round {rnd} of {n}). Only you, the Medium, and the dead ({names}) hear it. If you have nothing to say, leave say empty.",
    "죽은 사람 대화다({rnd}/{n}번째 바퀴). 죽은 사람들과 영매만 듣는다. 산 사람에게는 들리지 않는다. 하고 싶은 말이 없으면 say를 비운다.": "Chat of the dead (round {rnd} of {n}). Only the dead and the Medium hear it; the living do not. If you have nothing to say, leave say empty.",
}

PUBLIC = {
    "토론을 시작합니다. 남은 발언 차례는 {n}번입니다.": "The discussion begins. {n} turns to speak are left.",
    "자동 진행이라면 지금 토론이 끝납니다.": "On automatic pacing the discussion would end now.",
    "토론 시간이 얼마 남지 않았습니다.": "Little discussion time is left.",
    "토론 시간이 얼마 남지 않았습니다": "Little discussion time is left",
    "귓속말 시간입니다.": "Whisper time.",
    "투표 시간입니다.": "Time to vote.",
    "{n}번째 낮": "Day {n}", "{n}번째 밤": "Night {n}", "{base}, {step}": "{base}, {step}", "{step}": "{step}",
    "{name}님이 토론 시간을 늘렸습니다.": "{name} extended the discussion.",
    "{name}님이 토론을 끝내자고 했습니다. ({votes}/{need})": "{name} asked to end the discussion. ({votes}/{need})",
    "과반이 넘어가기를 원해 토론을 끝냅니다.": "A majority wants to move on, so the discussion ends.",
    "첫날은 투표 없이 밤이 됩니다.": "On the first day night falls without a vote.",
    "{name}님 {n}표({who})": "{name} {n} ({who})", "{name}님 {n}표": "{name} {n}",
    "기권 {n}({who})": "Abstain {n} ({who})", "기권 {n}": "Abstain {n}",
    "투표 결과: {tally}": "Vote result: {tally}", "아무도 투표하지 않았습니다": "nobody voted",
    "오늘은 투표할 수 없다.": "You cannot vote today.",
    "소개 시간입니다. 자리 순서대로 한 사람씩 자기를 소개합니다.": "Introductions. One by one in seat order, everyone introduces themselves.",
    "아무도 투표하지 않아 밤이 됩니다.": "Nobody voted, so night falls.",
    "최다 득표가 동점이라 밤이 됩니다.": "The top votes are tied, so night falls.",
    "{name}님이 최다 득표로 최후의 반론을 합니다.": "{name} got the most votes and gives the last defence.",
    "{name}님은 오늘 말할 수 없습니다.": "{name} cannot speak today.",
    "{name}님은 아무 말도 하지 않았습니다.": "{name} said nothing.",
    "찬반 결과: 찬성 {yes}, 반대 {no}": "Verdict: Yes {yes}, No {no}",
    "찬반 결과: 찬성 {yes}, 반대 {no} (찬성: {ayes} / 반대: {nays})": "Verdict: Yes {yes}, No {no} (Yes: {ayes} / No: {nays})",
    "{name}님은 처형되지 않았습니다.": "{name} was not executed.",
    "{name}님은 투표로 처형되지 않습니다.": "{name} cannot be executed by vote.",
    "{name}님이 처형되었습니다.": "{name} was executed.",
    "{name}님은 소개하지 않았습니다.": "{name} gave no introduction.",
    "게임을 시작합니다": "The game begins",
    "{n}번째 밤이 지나도록 끝나지 않아 마피아 팀이 이겼습니다": "The game did not end by night {n}, so the mafia team won",
    "{text} {name}님은 {role:이었습니다/였습니다}.": "{text} {name} was the {role}.",
    "{name}님의 직업이 {old}에서 {role:으로/로} 바뀌었습니다.": "{name}'s role changed from {old} to {role}.",
    "모두 죽었습니다": "Everyone died", "마피아 팀 수가 시민 팀 수와 같아졌습니다": "The mafia team equals the citizen team in number",
    "마피아 팀이 모두 죽었습니다": "The whole mafia team is dead", "무승부": "Draw", "{team} 승리": "{team} wins",
    "게임이 중단되었습니다": "The game was stopped", "{label}. {reason}.": "{label}. {reason}.",
    "중단됨": "Stopped", "게임을 멈췄습니다": "The game was stopped", "일시정지": "Paused", "다시 진행": "Resumed",
    "신의 보호로 {name}님이 살았습니다.": "{name} survived under god's protection.",
    "의사의 치료로 {name}님이 살아났습니다.": "The Doctor's care saved {name}.",
    "의사가 {name}님을 살렸습니다.": "The Doctor saved {name}.",
    "밤사이 {name}님이 죽었습니다.": "{name} died in the night.",
    "조용하게 밤이 지나갔습니다.": "The night passed quietly.", "조용하게 밤이 지나갔습니다": "The night passed quietly",
    "오늘 밤 죽일 사람: {name}": "Tonight's kill: {name}", "밤이 되었습니다": "Night has fallen",
}

LINEUP = {
    "이번 판의 직업(직접 정한 구성, 모두 공개): {listed}. 같은 직업이 여럿이면 각자 자기 능력을 따로 쓴다.": "Roles this game (a chosen lineup, all public): {listed}. Several players with the same role each use their own ability.",
    "이번 판의 직업(직접 정한 구성, 모두 공개): {listed}.": "Roles this game (a chosen lineup, all public): {listed}.",
    "이번 판의 직업(정해진 구성, 모두 공개): {listed}.": "Roles this game (the set lineup, all public): {listed}.",
    "{role} {n}명": "{role} {n}", "{slot} {n}자리({names} 가운데에서)": "{slot} {n} (from {names})",
    "이번 판의 직업은 자리 종류마다 정해진 수만큼 아래 후보 가운데에서 뽑혔다. 어떤 후보가 뽑혔는지는 모른다. 뽑을 후보가 모자란 자리는 시민이 된다. {parts}.": "This game's roles were drawn, a set number per kind of seat, from the candidates below. Which candidates were drawn is not known. A seat with too few candidates becomes a Citizen. {parts}.",
}

EN_TEXT: dict[str, str] = {**ABILITY, **PRIVATE, **TASKS, **PUBLIC, **LINEUP}

from .en_prompt import EN_PROMPT  # noqa: E402  (the prompt's frame, rules and roles: kept apart for size)

EN_TEXT.update(EN_PROMPT)

from .en_full import EN_FULL  # noqa: E402  (the full pool and the cult)

EN_TEXT.update(EN_FULL)

from .en_god import EN_GOD  # noqa: E402  (the god powers)

EN_TEXT.update(EN_GOD)
