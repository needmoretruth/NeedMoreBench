"""Builds the prompt one player gets for one call.

Information isolation is enforced here: the prompt for a seat is built only from events visible to that
seat, its own ledger and notes, and in blind mode no model, maker or country appears anywhere.

The default prompt is minimal: rules, what this player knows, the situation, the task with
its legal choices and the answer format. No strategy advice and no behaviour correction: how a model plays
is what the bench measures. Strategy only enters through the versioned expert section.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .abilities import ability_of, in_mafia_team
from .expert import expert_text
from .roles import COMPLEX, GAME_TITLE, MAFIA, ROLES, TEAM_LABEL
from .state import NOTE_CHARS, NOTE_LIMIT, Event, Player
from .turn import TurnRequest

if TYPE_CHECKING:
    from .game import Game

# Format only: length, plain text, and names as written, because the engine finds who was addressed
# by the names in a line (reply priority) and the screen links them.
TEXT_FORMAT = """글 형식
- say와 귓속말은 한 번에 1~3문장의 평범한 글이다. 마크다운, 목록, 이모지, 괄호 속 행동 묘사는 쓰지 않는다."""


def day_rules(game: "Game") -> list[str]:
    s = game.setup
    per, step = s.turns_per_player, s.extend_step
    votes = "누가 누구에게 투표했는지도 공개된다." if s.vote_public else "누가 누구에게 투표했는지는 공개되지 않고 표 수만 나온다."
    return [
        "게임은 낮으로 시작한다. 1번째 낮에는 자리 순서대로 한 사람씩 자기를 소개하고 토론을 한 뒤, 투표 없이 1번째 밤이 된다. "
        "그 뒤로 밤 → 아침 → 토론 → 귓속말 시간 → 투표 → 최후의 반론 → 찬반 → 밤이 되풀이된다. N번째 밤 다음 날이 N+1번째 낮이다.",
        "직업 주장: 누가 자기 직업이나 남의 직업에 대해 하는 말은 참일 수도 거짓일 수도 있다. 사실대로 말하든 거짓으로 말하든 말하지 않든 각자의 자유다.",
        "아침: 밤사이 죽은 사람이 발표된다. 아무도 안 죽었으면 「조용하게 밤이 지나갔습니다」.",
        f"토론: 발언 차례가 정해져 있다. 시작할 때 살아 있는 사람 1명당 {per}번씩이고, 누가 말할 때마다 1씩 줄어든다. "
        "남은 차례는 모두가 보고, 0이 되면 바로 투표다(1번째 낮에는 바로 밤이다). 처음에는 모두 한 번씩 말하고, 그다음엔 방금 이름이 불린 사람, 그다음엔 손을 많이 든 사람(hand) 순으로 말한다. "
        "모두 할 말이 없으면 일찍 끝난다.",
        f"토론 시간: 각자 하루 한 번 time에 \"연장\"(남은 차례 +{step})이나 \"단축\"(-{step})을 적을 수 있다. 모두에게 알려진다. "
        "남은 차례가 살아 있는 사람 수 이하가 되면 「토론 시간이 얼마 남지 않았습니다」가 나온다.",
        "귓속말 시간: 토론이 끝나면 살아 있는 사람이 정해진 순서대로 한 명씩, 살아 있는 사람 한 명을 골라 귓속말(1:1 비밀 대화)을 한 번 보내거나 보내지 않는다. "
        "그다음 귓속말을 받은 사람이 보낸 사람마다 한 번씩 답한다. 그것으로 그날 귓속말은 끝난다. 귓속말은 보낸 사람과 받은 사람만 보고, 다른 사람은 귓속말이 오간 것조차 모른다.",
        "여론 조사: 토론 중 poll에 의심 가는 사람 한 명을 적을 수 있다(바꿔도 되고 없음도 된다). 사람마다 몇 명이 찍었는지만 공개되고 누가 찍었는지는 숨겨진다. 게임 결과에는 영향이 없다.",
        f"투표: 한 사람 한 표. 자기 자신에게도, 기권도 된다. {votes} 최다 득표자가 동점이거나 아무도 투표하지 않으면 바로 밤이 된다.",
        "최후의 반론: 최다 득표자 혼자 말한다. 찬반: 나머지가 처형에 찬성 또는 반대한다. 찬성이 반대보다 많거나 같으면 처형된다. 기권은 반대로 센다.",
    ]


def rules_text(game: "Game") -> str:
    s = game.setup
    reveal = "죽은 사람의 직업은 모두에게 공개된다." if s.reveal else "죽은 사람의 직업은 공개되지 않는다."
    if game.kind == COMPLEX:
        present = sorted({p.start_role for p in game.players})
        lines = [f"이번 판에 있을 수 있는 직업: {', '.join(present)}. 각 직업의 능력은 아래 「직업」에 있다.",
                 "마피아 팀은 마피아와, 마피아와 접선한 보조 직업이다. 보조 직업은 처음엔 마피아가 누군지 모르고, 접선하기 전에는 시민 팀 수로 센다. 보조 직업도 마피아 팀이 이기면 함께 이긴다.",
                 "밤: 마피아 팀은 마피아 회의에서 한 명을 죽인다. 밤에 쓰는 능력이 있는 사람은 그 능력을 쓴다. 능력의 결과는 쓴 사람만 알고, 아침에는 죽은 사람과 모두에게 알려지는 일만 발표된다."]
    else:
        lines = ["마피아 팀(마피아)과 시민 팀(경찰, 의사, 시민)이 있다.",
                 "밤: 마피아끼리 짧게 의논해 한 명을 죽인다. 경찰은 한 명을 조사해 마피아인지 알게 된다. 의사는 한 명을 살린다. 의사가 살리면 아침에 모두에게 알려진다."]
    lines += day_rules(game)
    lines += [
        f"승패: 마피아 팀이 모두 죽으면 시민 팀이 이긴다. 마피아 팀 수가 나머지 이상이 되면 마피아 팀이 이긴다. "
        f"승패는 밤이 끝날 때와 찬반이 끝날 때 본다. {s.max_nights}번째 밤이 지나도 안 끝나면 마피아 팀이 이긴다.",
        reveal,
        "이름: 모든 참가자는 참가자 목록에 적힌 이름으로 불린다. 이 이름은 게임 내내 바뀌지 않는다. 다른 참가자를 말할 때는 그 이름을 그대로 쓰고, 줄이거나 다른 글자로 옮겨 쓰지 않는다.",
    ]
    out = "\n".join("- " + x for x in lines)
    if game.kind == COMPLEX:
        present = sorted({p.start_role for p in game.players})
        out += "\n\n직업\n" + "\n".join(f"- {r} ({TEAM_LABEL[ROLES[r].team]}): {ROLES[r].text}" for r in present)
    return out


def system_text(game: "Game", p: Player) -> str:
    s = game.setup
    head = (f"너는 사람들과 둘러앉아 마피아 게임 「{GAME_TITLE[game.kind]}」을 하고 있다. "
            f"너는 참가자 「{p.name}」이고 모두 너를 {p.name}(이)라고 부른다.")
    parts = [head, "규칙\n" + rules_text(game), TEXT_FORMAT]
    if s.named:
        parts.append("참가자들은 서로 어느 회사, 어느 나라의 어떤 모델인지 알고 있다(참가자 목록에 있다).")
    if s.language == "en":
        parts.append("모든 글(say, whispers, thought, notes, 장부 비고)은 영어로 쓴다.")
    else:
        parts.append("모든 글은 한국어로 쓴다. 다른 나라 글자(한자 등)를 섞지 않는다. 참가자 이름만은 목록에 적힌 그대로 쓴다.")
    expert = expert_text(game, p)
    if expert:
        parts.append(expert)
    return "\n\n".join(parts)


def _identity_block(game: "Game", p: Player) -> str:
    role = ROLES[p.role]
    lines = [f"- 이름: {p.name}", f"- 직업: {p.role} ({TEAM_LABEL[role.team]}). {role.text}"]
    if in_mafia_team(p):
        mates = [f"{q.name}({q.role}{'' if q.alive else ', 죽음'})" for q in game.players if q is not p and in_mafia_team(q)]
        lines.append("- 마피아 팀: " + (", ".join(mates) if mates else "너 혼자"))
    elif role.team == MAFIA:
        lines.append("- 아직 마피아와 접선하지 않아 마피아가 누군지 모른다.")
    status = ability_of(p.role).status(p)
    if status:
        lines.append("- " + status)
    if game.setup.named:
        lines.append(f"- 다른 사람들에게 보이는 네 모습: {p.shown.line()}")
    return "너\n" + "\n".join(lines)


def _roster_block(game: "Game", p: Player) -> str:
    """Fixed for the whole game, so it stays in the cached prefix."""
    out = []
    for q in game.players:
        line = f"{q.seat + 1}. {q.name}" + (" (너)" if q is p else "")
        if game.setup.named:
            line += f" ({q.shown.line()})"
        out.append(line)
    return "참가자\n" + "\n".join(out)


def _state_block(game: "Game") -> str:
    alive = [q.name for q in game.players if q.alive]
    dead = [q.name + (f"({r})" if (r := game.public_role(q)) else "") for q in game.players if not q.alive]
    shown = [f"{q.name}({q.role})" for q in game.players if q.alive and q.revealed]
    lines = [f"- 살아 있음: {', '.join(alive)}", f"- 죽음: {', '.join(dead) or '없음'}"]
    if shown:
        lines.append(f"- 직업이 공개된 사람: {', '.join(shown)}")
    return "지금 참가자 상태\n" + "\n".join(lines)


def render_event(e: Event, game: "Game", seat: int) -> str | None:
    name = game.name_of
    if e.kind == "say":
        tag = " (최후의 반론)" if e.data.get("defense") else " (소개)" if e.data.get("intro") else ""
        return f"{name(e.actor)}{tag}: {e.text}"
    if e.kind == "whisper":
        if e.actor == seat:
            return f"(귓속말) 너 → {name(e.target)}: {e.text}"
        return f"(귓속말) {name(e.actor)} → 너: {e.text}"
    if e.kind == "mafia":
        if e.actor is None:
            return f"(마피아 회의) {e.text}"
        pick = e.data.get("pick")
        return f"(마피아 회의) {name(e.actor)}: {e.text or '(말 없음)'}" + (f" [죽일 사람: {pick}]" if pick else "")
    if e.kind == "lover":
        return f"(연인 대화) {name(e.actor)}: {e.text}"
    if e.kind == "dead":
        return f"(죽은 사람 대화) {name(e.actor)}: {e.text}"
    if e.kind == "god" and e.data.get("power") == "계시":
        return f"신의 계시(너에게만): {e.text}"
    if e.kind == "god":
        return f"신의 공지: {e.text}" if e.data.get("power") == "공지" else f"(진행) {e.text}"
    if e.kind == "moderator":
        return f"사회자: {e.text}"
    if e.kind == "phase":
        return f"[{e.text}]"
    if e.kind == "private":
        return f"(너만 앎) {e.text}"
    return f"(진행) {e.text}" if e.text else None


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
    lines = [line for i, line in log_lines(game, p) if i > p.memory_upto]
    parts = []
    if p.memory:
        parts.append("네가 정리해 둔 기억 (그 앞의 기록은 이것으로 대신한다)\n" + p.memory)
    parts.append(("그 뒤에 있었던 일" if p.memory else "지금까지 있었던 일") + "\n"
                 + ("\n".join(lines) if lines else "(아직 없음)"))
    return "\n\n".join(parts)


def _discussion_block(game: "Game", p: Player, req: TurnRequest) -> str | None:
    if req.kind != "discuss":
        return None
    n = len(game.alive())
    lines = [f"- 남은 발언 차례: {game.turns_left}번 (살아 있는 사람 {n}명)"]
    if game.day == 1:
        lines.append("- 1번째 낮이라 토론이 끝나면 투표 없이 밤이 된다.")
    if game.turns_left <= n:
        lines.append("- 토론 시간이 얼마 남지 않았다.")
    lines.append("- 너의 연장/단축: " + ("오늘 이미 썼다" if p.seat in game.time_used else "오늘 아직 안 씀"))
    counts = game.poll_counts()
    lines.append("- 여론 조사: " + (", ".join(f"{k} {v}명" for k, v in counts.items()) if counts else "아직 아무도 안 찍음"))
    mine = game.poll.get(p.seat)
    lines.append(f"- 네가 찍은 사람: {mine or '없음'}")
    return "토론 상황\n" + "\n".join(lines)


def _ledger_block(p: Player) -> str:
    rows = [f"- {n}: 의심도 {r.suspicion}, 추정 {r.guess}, 비고 {r.note or '없음'}" for n, r in p.ledger.items()]
    return "네 장부 (의심도 0~100: 0은 확실히 믿음, 100은 확실히 의심, 50은 모름)\n" + "\n".join(rows)


def _notes_block(p: Player) -> str:
    notes = p.notebook.notes
    body = "\n".join(f"#{n.id} {n.text}" for n in notes) if notes else "(비어 있음)"
    return f"네 노트 ({len(notes)}/{NOTE_LIMIT}개)\n{body}"


SAY_TO = {"mafia": "마피아 팀에게 하는 말", "lover": "연인에게만 하는 말. 없으면 빈 문자열",
          "dead": "죽은 사람 대화에서 하는 말. 없으면 빈 문자열"}


def answer_format(game: "Game", p: Player, req: TurnRequest) -> str:
    shape: dict[str, object] = {"thought": "속마음 한두 문장. 아무도 못 본다"}
    rules = []
    if req.say:
        shape["say"] = SAY_TO.get(req.kind, "모두가 듣는 말. 침묵하려면 빈 문자열")
    if req.whispers:
        shape["whispers"] = [{"to": "이름", "text": "귓속말 내용"}]
        each = " 한 사람에게 하나까지." if req.whispers > 1 else ""
        rules.append(f"whispers: 귓속말 최대 {req.whispers}개.{each} 보낼 수 있는 사람: {', '.join(req.whisper_to)}. 안 보내면 빈 목록.")
    if req.field:
        opts = req.options + ([req.skip_word] if req.skip_word else [])
        shape[req.field] = " | ".join(opts)
        rules.append(f"{req.field}: 다음 가운데 정확히 하나를 그대로 적는다: {', '.join(opts)}.")
    if req.extra_field:
        shape[req.extra_field] = " | ".join(req.extra_options + ["없음"])
        rules.append(f"{req.extra_field}: {req.extra_task} 다음 가운데 하나: {', '.join(req.extra_options + ['없음'])}.")
    if req.hand:
        shape["hand"] = 1
        rules.append("hand: 곧 다시 말하고 싶은 정도. 0 할 말 없음, 1 조금, 2 꼭 하고 싶음, 3 지금 당장 반박해야 함.")
    if req.time:
        shape["time"] = ""
        rules.append("time: 토론을 늘리려면 \"연장\", 줄이려면 \"단축\", 아니면 빈 문자열. 하루 한 번만 된다.")
    if req.poll:
        shape["poll"] = "이름 | 없음"
        rules.append("poll: 여론 조사에서 찍을 사람 한 명, 또는 없음(찍은 것을 거둔다). poll을 빼면 지금 찍은 것이 그대로 남는다.")
    shape["ledger"] = [{"name": "이름", "suspicion": 50, "guess": "직업 또는 모름", "note": "짧은 비고"}]
    shape["notes"] = {"add": ["새 노트"], "edit": [{"id": 1, "text": "고친 내용"}], "delete": [2]}
    guesses = ", ".join(game.guess_options())
    rules.append(f"ledger: 바꿀 사람의 줄만 적는다. 바꿀 것이 없으면 빈 목록. suspicion은 0~100, guess는 {guesses} 가운데 하나, note는 한 줄.")
    rules.append(f"notes: add로 더하고 edit로 고치고 delete로 지운다(번호로). 최대 {NOTE_LIMIT}개, 하나에 {NOTE_CHARS}자. 바꿀 것이 없으면 빈 목록.")
    return ("답 형식: JSON 객체 하나만 답한다. 앞뒤에 다른 글을 쓰지 않는다.\n"
            + json.dumps(shape, ensure_ascii=False, indent=1) + "\n" + "\n".join("- " + r for r in rules))


def build_prompt(game: "Game", p: Player, req: TurnRequest, error: str | None = None) -> tuple[str, str]:
    """(system, user) for this seat and call. Routes without a system slot join them."""
    # append-only order: fixed roster, then the log in order, then what changes every call
    blocks = [_roster_block(game, p), _log_block(game, p), f"지금: {game.phase_label()}", _identity_block(game, p),
              _state_block(game), _discussion_block(game, p, req), _ledger_block(p), _notes_block(p),
              "할 일\n" + req.task, answer_format(game, p, req)]
    if error:
        blocks.append(f"앞의 답을 쓸 수 없었다: {error}. 형식에 맞게 다시 답한다.")
    return system_text(game, p), "\n\n".join(b for b in blocks if b)
