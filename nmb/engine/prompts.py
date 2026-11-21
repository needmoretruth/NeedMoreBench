"""Builds the prompt one player gets for one call.

Information isolation is enforced here: the prompt for a seat is built only from events visible to that
seat, its own ledger and notes, and in blind mode no model, maker or country appears anywhere.

The default prompt is minimal: rules, what this player knows, the situation, the task with
its legal choices and the answer format. No strategy advice and no behaviour correction: how a model plays
is what the bench measures. Strategy only enters through the versioned expert section.

Every line is a message rendered in the game's dialogue language, so an English game's prompt holds
no Korean but the names the players were given.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .abilities import ability_of, in_mafia_team
from .abilities.base import in_cult
from .abilities.cult import leads, members
from .expert import expert_text
from .god import RULE as god_rule, revelation_block
from .lineups import by_counts, kinds_text
from .roles import COMPLEX, CULT, GAME_TITLE, MAFIA, ROLES, TEAM_LABEL
from .setup import playable
from .state import NOTE_PAGE, Event, Player
from .text import Msg, T
from .turn import TurnRequest

if TYPE_CHECKING:
    from .game import Game

# Format only: length, plain text, and names as written, because the engine finds who was addressed
# by the names in a line (reply priority) and the screen links them.
TEXT_FORMAT = T("글 형식\n- say와 귓속말은 한 번에 1~3문장의 평범한 글이다. 마크다운, 목록, 이모지, 괄호 속 행동 묘사는 쓰지 않는다.")


def day_rules(game: "Game") -> list[Msg]:
    s = game.setup
    votes = T("누가 누구에게 투표했는지도 공개된다.") if s.vote_public else T("누가 누구에게 투표했는지는 공개되지 않고 표 수만 나온다.")
    return [
        T("게임은 낮으로 시작한다. 1번째 낮에는 자리 순서대로 한 사람씩 자기를 소개하고 토론과 귓속말 시간을 가진 뒤, 투표 없이 1번째 밤이 된다. "
          "그 뒤로 밤 → 아침 → 토론 → 귓속말 시간 → 투표 → 최후의 반론 → 찬반 → 밤이 되풀이된다. N번째 밤 다음 날이 N+1번째 낮이다."),
        T("직업 주장: 누가 자기 직업이나 남의 직업에 대해 하는 말은 참일 수도 거짓일 수도 있다. 사실대로 말하든 거짓으로 말하든 말하지 않든 각자의 자유다."),
        T("아침: 밤사이 죽은 사람이 발표된다. 아무도 안 죽었으면 「{quiet}」.", quiet=T("조용하게 밤이 지나갔습니다")),
        T("토론: 발언 차례가 정해져 있다. 시작할 때 살아 있는 사람 1명당 {per}번씩이고(1번째 낮에는 소개 뒤에 1명당 1번씩), 누가 말할 때마다 1씩 줄어든다. "
          "남은 차례는 모두가 보고, 0이 되면 바로 투표다(1번째 낮에는 바로 밤이다). 처음에는 모두 한 번씩 말하고, 그다음엔 방금 이름이 불린 사람, 그다음엔 손을 많이 든 사람(hand) 순으로 말한다. "
          "차례가 와도 say를 비워 침묵할 수 있다. 침묵은 남은 차례를 쓰지 않고, 손을 내린 것이 된다. "
          "말할 수 있는 모두가 한 번씩 차례를 받으면 내린 손이 다시 올라가 모두 다시 차례를 받는다. "
          "한 바퀴 동안 아무도 말하지 않으면 토론이 끝난다. 이름이 불린 사람은 답할 차례를 먼저 받지만, 다른 사람이 손을 들고 기다리면 연달아 두 번은 받지 않는다.",
          per=s.turns_per_player),
        T("토론 시간: 각자 하루 한 번 time에 \"{extend}\"을 적으면 남은 차례가 {step} 늘어난다. 따로 하루 한 번 \"{shorten}\"을 적을 수 있는데, "
          "{shorten}은 토론을 끝내자는 표다. 살아 있는 사람의 과반이 {shorten}을 적으면 그 즉시 토론이 끝난다. {extend}과 {shorten}은 누가 했는지 모두에게 알려진다. "
          "남은 차례가 살아 있는 사람 수 이하가 되면 「{warn}」가 나온다.",
          extend="연장", shorten="단축", step=s.extend_step, warn=T("토론 시간이 얼마 남지 않았습니다")),
        T("귓속말 시간: 토론이 끝나면 살아 있는 사람이 정해진 순서대로 한 명씩, 살아 있는 사람 한 명을 골라 귓속말(1:1 비밀 대화)을 한 번 보내거나 보내지 않는다. "
          "그다음 귓속말을 받은 사람이 보낸 사람마다 한 번씩 답한다. 그것으로 그날 귓속말은 끝난다. 귓속말은 보낸 사람과 받은 사람만 보고, 다른 사람은 귓속말이 오간 것조차 모른다."),
        T("여론 조사: 토론 중 poll에 의심 가는 사람 한 명을 적을 수 있다(바꿔도 되고 {none}도 된다). 사람마다 몇 명이 찍었는지만 공개되고 누가 찍었는지는 숨겨진다. 게임 결과에는 영향이 없다.",
          none="없음"),
        T("투표: 한 사람 한 표. 자기 자신에게도, 기권도 된다. {votes} 최다 득표자가 동점이거나 아무도 투표하지 않으면 바로 밤이 된다.", votes=votes),
        T("최후의 반론: 최다 득표자 혼자 말한다. 찬반: 나머지가 처형에 찬성 또는 반대한다. 찬성이 반대보다 많거나 같으면 처형된다. 기권은 반대로 센다."),
    ]


def rules_text(game: "Game") -> str:
    s = game.setup
    t = game.t
    reveal = T("죽은 사람의 직업은 모두에게 공개된다.") if s.reveal else T("죽은 사람의 직업은 공개되지 않는다.")
    rules: list[Msg] = []
    if game.kind == COMPLEX:
        told, _roles = kinds_text(s, len(game.players), playable)
        rules = [T("{told} 각 직업의 능력은 아래 「직업」에 있다.", told=told),
                 T("마피아 팀은 마피아와, 마피아와 접선한 보조 직업이다. 보조 직업은 처음엔 마피아가 누군지 모르고, 접선하기 전에는 시민 팀 수로 센다. 보조 직업도 마피아 팀이 이기면 함께 이긴다."),
                 T("밤: 마피아 팀은 마피아 회의에서 한 명을 죽인다. 밤에 쓰는 능력이 있는 사람은 그 능력을 쓴다. 능력의 결과는 쓴 사람만 알고, 아침에는 죽은 사람과 모두에게 알려지는 일만 발표된다.")]
    else:
        rules = [T("마피아 팀(마피아)과 시민 팀(경찰, 의사, 시민)이 있다."),
                 T("밤: 마피아는 마피아 회의에서 한 명을 죽인다. 경찰은 한 명을 조사해 마피아인지 알게 된다. 의사는 한 명을 살린다(자기 자신도 된다). "
                   "의사가 살리면 아침에 모두에게 알려진다.")]
        if by_counts(s):  # 직접: the counts are public, as a named lineup's are
            rules.insert(0, kinds_text(s, len(game.players), playable)[0])
    rules.append(T("마피아 회의: 마피아 팀만 듣는 대화다. 차례대로 말하며 죽일 사람을 고르고, 살아 있는 누구든 고를 수 있다(같은 마피아 팀이나 자기 자신도). "
                   "서로의 말과 선택을 보고 바꿀 수 있고, 최대 3바퀴 돈다. 한 바퀴가 끝났을 때 죽일 사람을 고르는 모두의 선택이 같으면 끝나고, "
                   "3바퀴가 지나도 갈리면 가장 많이 나온 사람, 같으면 먼저 말한 쪽의 선택으로 정해진다. 마피아가 혼자면 한 번 고른다."))
    rules += day_rules(game)
    rules += [
        T("승패: 마피아 팀이 모두 죽으면 시민 팀이 이긴다. 마피아 팀 수가 나머지 이상이 되면 마피아 팀이 이긴다. "
          "승패는 밤이 끝날 때와 찬반이 끝날 때 본다. {n}번째 밤이 지나도 안 끝나면 마피아 팀이 이긴다.", n=s.max_nights),
    ]
    if game.kind == COMPLEX and any(ROLES[r].team == CULT for r in kinds_text(s, len(game.players), playable)[1]):
        rules.append(T("교주 팀: 교주 팀 수가 나머지 이상이 되면 교주 팀이 이긴다. 포교된 사람은 원래 팀이 아니라 교주 팀으로 이긴다. "
                       "여러 팀이 함께 조건을 채우면 마피아 팀, 교주 팀, 시민 팀 순서로 앞선다."))
    rules += [
        reveal,
        T("이름: 모든 참가자는 참가자 목록에 적힌 이름으로 불린다. 이 이름은 게임 내내 바뀌지 않는다. 다른 참가자를 말할 때는 그 이름을 그대로 쓰고, 줄이거나 다른 글자로 옮겨 쓰지 않는다."),
    ]
    if s.powers:
        rules.append(god_rule)
    out = "\n".join("- " + t(x) for x in rules)
    if game.kind == COMPLEX:
        present = kinds_text(s, len(game.players), playable)[1]
        out += "\n\n" + t(T("직업")) + "\n" + "\n".join(
            f"- {t(r)} ({t(TEAM_LABEL[ROLES[r].team])}): {t(T(ROLES[r].text))}" for r in present)
    return out


def system_text(game: "Game", p: Player) -> str:
    s = game.setup
    t = game.t
    head = T("너는 사람들과 둘러앉아 마피아 게임 「{title}」을 하고 있다. 너는 참가자 「{name}」이고 모두 너를 {name2:이라고/라고} 부른다.",
             title=GAME_TITLE[game.kind], name=p.name, name2=p.name)
    parts = [t(head), t(T("규칙")) + "\n" + rules_text(game), t(TEXT_FORMAT)]
    revealed = revelation_block(game, p)  # as binding as the rules, until the 신 lifts it
    if revealed:
        parts.append(revealed)
    if s.named:
        parts.append(t(T("참가자들은 서로 어느 회사, 어느 나라의 어떤 모델인지 알고 있다(참가자 목록에 있다).")))
    if game.lang == "en":
        parts.append("Write everything (say, whispers, thought, notes, ledger notes) in English. "
                     "Write the players' names exactly as the player list has them.")
    else:
        parts.append("모든 글은 한국어로 쓴다. 다른 나라 글자(한자 등)를 섞지 않는다. 참가자 이름만은 목록에 적힌 그대로 쓴다.")
    expert = expert_text(game, p)
    if expert:
        parts.append(t(expert))
    return "\n\n".join(parts)


def _identity_block(game: "Game", p: Player) -> str:
    t = game.t
    role = ROLES[p.role]
    rows = [T("이름: {name}", name=p.name),
            T("직업: {role} ({team}). {text}", role=p.role, team=TEAM_LABEL[role.team], text=T(role.text))]
    if in_mafia_team(p):
        mates = [T("{name}({role})", name=q.name, role=q.role) if q.alive else T("{name}({role}, 죽음)", name=q.name, role=q.role)
                 for q in game.players if q is not p and in_mafia_team(q)]
        rows.append(T("마피아 팀: {mates}", mates=mates or T("너 혼자")))
    elif role.team == MAFIA:
        rows.append(T("아직 마피아와 접선하지 않아 마피아가 누군지 모른다."))
    cult = cult_row(game, p)
    if cult is not None:
        rows.append(cult)
    status = ability_of(p.role).status(p)
    if status:
        rows.append(status)
    if game.setup.named:
        rows.append(T("다른 사람들에게 보이는 네 모습: {shown}", shown=p.shown.line(game.lang)))
    return t(T("너")) + "\n" + "\n".join("- " + t(x) for x in rows)


def cult_row(game: "Game", p: Player) -> Msg | None:
    """Who of the cult this player knows: the leader knows its converts, a convert or a linked 광신도 its leader."""
    if not in_cult(p):
        return None
    cid = p.state.get("cult")
    if cid is None:
        return T("교주 팀이다. 아직 교주가 누군지 모른다.")
    if leads(game, p):
        flock = [T("{name}({role})", name=q.name, role=q.role) if q.alive else T("{name}({role}, 죽음)", name=q.name, role=q.role)
                 for q in members(game, cid, alive=False) if q is not p]
        return T("교주 팀이다. 같은 교주 팀: {names}", names=flock or "없음")
    return T("교주 팀이다. 교주: {name}", name=game.players[cid].name)


def _roster_block(game: "Game", p: Player) -> str:
    """Fixed for the whole game, so it stays in the cached prefix."""
    out = []
    for q in game.players:
        line = f"{q.seat + 1}. {q.name}" + (game.t(T(" (너)")) if q is p else "")
        if game.setup.named:
            line += f" ({q.shown.line(game.lang)})"
        out.append(line)
    return game.t(T("참가자")) + "\n" + "\n".join(out)


def _state_block(game: "Game") -> str:
    t = game.t
    alive = [q.name for q in game.players if q.alive]
    dead = [T("{name}({role})", name=q.name, role=r) if (r := game.public_role(q)) else q.name
            for q in game.players if not q.alive]
    shown = [T("{name}({role})", name=q.name, role=q.role) for q in game.players if q.alive and q.revealed]
    rows = [T("살아 있음: {names}", names=alive), T("죽음: {names}", names=dead or "없음")]
    if shown:
        rows.append(T("직업이 공개된 사람: {names}", names=shown))
    return t(T("지금 참가자 상태")) + "\n" + "\n".join("- " + t(x) for x in rows)


def render_event(e: Event, game: "Game", seat: int) -> str | None:
    name, t = game.name_of, game.t
    if e.kind == "say":
        tag = T(" (최후의 반론)") if e.data.get("defense") else T(" (소개)") if e.data.get("intro") else ""
        return f"{name(e.actor)}{t(tag)}: {e.text}"
    if e.kind == "whisper":
        if e.actor == seat:
            return t(T("(귓속말) 너 → {to}: {text}", to=name(e.target), text=e.text))
        return t(T("(귓속말) {by} → 너: {text}", by=name(e.actor), text=e.text))
    if e.kind == "mafia":
        if e.actor is None:
            return t(T("(마피아 회의) {text}", text=e.text))
        pick = e.data.get("pick")
        line = T("(마피아 회의) {by}: {text}", by=name(e.actor), text=e.text or T("(말 없음)"))
        return t(line) + (t(T(" [죽일 사람: {name}]", name=pick)) if pick else "")
    if e.kind == "lover":
        return t(T("(연인 대화) {by}: {text}", by=name(e.actor), text=e.text))
    if e.kind == "dead":
        return t(T("(죽은 사람 대화) {by}: {text}", by=name(e.actor), text=e.text))
    if e.kind == "cult":
        return t(T("(교주의 말) {by}: {text}", by=name(e.actor), text=e.text))
    if e.kind == "god":  # never says who the 신 is; a 계시 stands in the system prompt instead
        power = e.data.get("power")
        text = e.text
        if power == "공지":
            return t(T("신의 공지: {text}", text=text))
        if power == "심문":
            return t(T("(신에게 한 답) {text}", text=text) if e.data.get("answer")
                     else T("신의 질문(너에게만, 답은 신만 본다): {text}", text=text))
        return t(T("(너만 앎) {text}", text=text) if e.to else T("(진행) {text}", text=text))
    if e.kind == "moderator":
        return t(T("사회자: {text}", text=e.text))
    if e.kind == "phase":
        return f"[{e.text}]"
    if e.kind == "private":
        return t(T("(너만 앎) {text}", text=e.text))
    if e.kind == "action":  # only the actor's own choice, as its memory; never someone else's
        return t(T("(너만 앎) 네 행동: {what}", what=e.data.get("what", ""))) if e.actor == seat else None
    return t(T("(진행) {text}", text=e.text)) if e.text else None


def log_lines(game: "Game", p: Player, upto: int | None = None) -> list[tuple[int, str]]:
    """Everything this seat may know, in order, as (event id, line). Nothing is collapsed."""
    out = []
    for e in game.events:
        if upto is not None and e.id > upto:
            break
        if not e.log or not e.visible_to(p.seat):
            continue
        line = render_event(e, game, p.seat)
        if line:
            out.append((e.id, line))
    return out


def _log_block(game: "Game", p: Player) -> str:
    t = game.t
    lines = [line for i, line in log_lines(game, p) if i > p.memory_upto]
    parts = []
    if p.memory:
        parts.append(t(T("네가 정리해 둔 기억 (그 앞의 기록은 이것으로 대신한다)")) + "\n" + p.memory)
    parts.append(t(T("그 뒤에 있었던 일") if p.memory else T("지금까지 있었던 일")) + "\n"
                 + ("\n".join(lines) if lines else t(T("(아직 없음)"))))
    return "\n\n".join(parts)


def _discussion_block(game: "Game", p: Player, req: TurnRequest) -> str | None:
    if req.kind != "discuss":
        return None
    t = game.t
    n = len(game.alive())
    rows = [T("남은 발언 차례: {left}번 (살아 있는 사람 {n}명)", left=game.turns_left, n=n)]
    if game.day == 1:
        rows.append(T("1번째 낮이라 토론이 끝나면 투표 없이 밤이 된다."))
    if game.turns_left <= n:
        rows.append(T("토론 시간이 얼마 남지 않았다."))
    used, unused = T("오늘 이미 썼다"), T("오늘 아직 안 씀")
    rows.append(T("너의 연장: {a}, 너의 단축: {b}", a=used if p.seat in game.time_used else unused,
                  b=used if p.seat in game.cut_votes else unused))
    alive = {q.seat for q in game.alive()}
    rows.append(T("단축 표: {n}명 (과반 {need}명이면 토론이 끝난다)", n=len(game.cut_votes & alive), need=len(alive) // 2 + 1))
    counts = game.poll_counts()
    rows.append(T("여론 조사: {counts}", counts=[T("{name} {n}명", name=k, n=v) for k, v in counts.items()]
                  or T("아직 아무도 안 찍음")))
    rows.append(T("네가 찍은 사람: {name}", name=game.poll.get(p.seat) or "없음"))
    return t(T("토론 상황")) + "\n" + "\n".join("- " + t(x) for x in rows)


SUSPICION = T("의심도 0~100: 이 사람이 너와 다른 팀일 가능성. 0은 확실히 같은 팀, 100은 확실히 다른 팀, 50은 모름")


def _ledger_block(game: "Game", p: Player) -> str:
    t = game.t
    rows = [T("{name}: 의심도 {s}, 추정 {guess}{known}, 비고 {note}", name=n, s=r.suspicion, guess=r.guess,
              known=T(", 확인됨") if r.known else "", note=r.note or "없음") for n, r in p.ledger.items()]
    return (t(T("네 장부 ({what}. 확인됨은 게임이 알려 준 사실)", what=SUSPICION)) + "\n"
            + "\n".join("- " + t(x) for x in rows))


def _notes_block(game: "Game", p: Player) -> str:
    page = p.notebook.page
    head = T("네 노트 ({n}/{max}자. 네 메모 한 장이다. 매 차례 너에게 보이고 아무도 못 본다)", n=f"{len(page):,}", max=f"{NOTE_PAGE:,}")
    return game.t(head) + "\n" + (page or game.t(T("(비어 있음)")))


SAY_TO = {"mafia": T("마피아 팀에게 하는 말"), "lover": T("연인에게만 하는 말. 없으면 빈 문자열"),
          "dead": T("죽은 사람 대화에서 하는 말. 없으면 빈 문자열"),
          "interrogate": T("신에게만 하는 답. 다른 참가자는 못 본다")}


def answer_format(game: "Game", p: Player, req: TurnRequest) -> str:
    t = game.t
    shape: dict[str, object] = {"thought": t(T("속마음 한두 문장. 아무도 못 본다"))}
    rules: list[Msg] = []
    if req.say:
        shape["say"] = t(SAY_TO.get(req.kind, T("모두가 듣는 말. 침묵하려면 빈 문자열")))
    if req.whispers:
        shape["whispers"] = [{"to": t(T("이름")), "text": t(T("귓속말 내용"))}]
        each = T(" 한 사람에게 하나까지.") if req.whispers > 1 else ""
        rules.append(T("whispers: 귓속말 최대 {n}개.{each} 보낼 수 있는 사람: {names}. 안 보내면 빈 목록.",
                       n=req.whispers, each=each, names=req.whisper_to))
    if req.field:
        opts = [t(o) for o in req.options + ([req.skip_word] if req.skip_word else [])]
        shape[req.field] = " | ".join(opts)
        rules.append(T("{field}: 다음 가운데 정확히 하나를 그대로 적는다: {opts}.", field=req.field, opts=opts))
    if req.extra_field:
        extra = [t(o) for o in req.extra_options + ["없음"]]
        shape[req.extra_field] = " | ".join(extra)
        rules.append(T("{field}: {task} 다음 가운데 하나: {opts}.", field=req.extra_field, task=req.extra_task, opts=extra))
    if req.hand:
        shape["hand"] = 1
        rules.append(T("hand: 곧 다시 말하고 싶은 정도. 0 할 말 없음, 1 조금, 2 꼭 하고 싶음, 3 지금 당장 반박해야 함."))
    if req.time:
        shape["time"] = ""
        words = [f"\"{t(w)}\"" for w, used in (("연장", game.time_used), ("단축", game.cut_votes)) if p.seat not in used]
        rules.append(T("time: {words}, 아니면 빈 문자열. 연장과 단축은 각각 하루 한 번만 된다.", words=t(T(" 또는 ")).join(words)))
    if req.poll:
        shape["poll"] = t(T("이름 | 없음"))
        rules.append(T("poll: 여론 조사에서 찍을 사람 한 명, 또는 없음(찍은 것을 거둔다). poll을 빼면 지금 찍은 것이 그대로 남는다."))
    shape["ledger"] = [{"name": t(T("이름")), "suspicion": 50, "guess": t(T("직업 또는 모름")), "note": t(T("짧은 비고"))}]
    shape["notes"] = t(T("노트 한 장 전체"))
    rules.append(T("ledger: 바꿀 사람의 줄만 적는다. 바꿀 것이 없으면 빈 목록. suspicion은 0~100, guess는 {guesses} 가운데 하나, note는 한 줄.",
                   guesses=game.guess_options()))
    rules.append(T("notes: 새로 쓴 노트 한 장 전체({max}자 이하). 지금 노트를 이것으로 바꾼다. 그대로 두려면 notes를 뺀다.", max=f"{NOTE_PAGE:,}"))
    return (t(T("답 형식: JSON 객체 하나만 답한다. 앞뒤에 다른 글을 쓰지 않는다.")) + "\n"
            + json.dumps(shape, ensure_ascii=False, indent=1) + "\n" + "\n".join("- " + t(r) for r in rules))


def build_prompt(game: "Game", p: Player, req: TurnRequest, error: "str | Msg | None" = None) -> tuple[str, str]:
    """(system, user) for this seat and call. Routes without a system slot join them."""
    t = game.t
    # append-only order: fixed roster, then the log in order, then what changes every call
    blocks = [_roster_block(game, p), _log_block(game, p), t(T("지금: {when}", when=game.phase_label())),
              _identity_block(game, p), _state_block(game), _discussion_block(game, p, req), _ledger_block(game, p),
              _notes_block(game, p), t(T("할 일")) + "\n" + t(req.task), answer_format(game, p, req)]
    if error:
        blocks.append(t(T("앞의 답을 쓸 수 없었다: {error}. 형식에 맞게 다시 답한다.", error=error)))
    return system_text(game, p), "\n\n".join(b for b in blocks if b)
