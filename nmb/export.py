"""The readable record of a saved game, for handing to another AI or a person (내보내기).

Plain Korean lines under day and night headings, everything the god view saw: public lines, whispers, the
mafia chat, private results, thoughts, the models' own reasoning, votes and deaths; then each player's final ledger and notes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import SUFFIX, Saved

SKIP = {"thinking", "turns", "poll", "call", "human_turn", "would_end", "ledger", "note", "start", "pause"}


def final_books(saved: Saved) -> tuple[dict[int, dict[str, dict[str, Any]]], dict[int, list[str]]]:
    """Each seat's last ledger rows and every version of its notebook page, oldest first."""
    ledgers: dict[int, dict[str, dict[str, Any]]] = {}
    pages: dict[int, list[str]] = {}
    old: dict[int, dict[int, str]] = {}  # games saved before the page kept numbered notes
    for e in saved.events:
        seat = e.get("by_seat")
        if seat is None:
            continue
        if e["kind"] == "ledger":
            ledgers.setdefault(seat, {})[e["details"]["name"]] = e["details"]["new"]
        elif e["kind"] == "note" and "op" in e["details"]:
            book = old.setdefault(seat, {})
            if e["details"]["op"] == "delete":
                book.pop(e["details"]["id"], None)
            else:
                book[e["details"]["id"]] = e["text"]
            pages.setdefault(seat, []).append("\n".join(f"#{k} {t}" for k, t in sorted(book.items())))
        elif e["kind"] == "note":
            pages.setdefault(seat, []).append(e["text"])
    return ledgers, pages


def _reveal(settings: dict[str, Any], game: str | None) -> bool:
    r = settings.get("reveal_roles")
    return bool(r) if r is not None else game == "simple"


def render(saved: Saved) -> str:
    h = saved.header
    seats = {s["seat"]: s for s in h.get("seats", [])}
    name = {k: v["name"] for k, v in seats.items()}
    setup = saved.settings
    out = [f"# {h.get('title')} 기록", "",
           f"- 날짜: {h.get('created')}", f"- 상태: {saved.status}",
           f"- 모드: {'기본(서로 모델을 앎)' if setup.get('named', True) else '블라인드'}"
           f", 죽으면 직업 공개 {'켬' if _reveal(setup, h.get('game')) else '끔'}"
           f", 투표 공개 {'공개' if setup.get('vote_public') else '익명'}", f"- 시드: {h.get('seed')}", "",
           "## 참가자", "", "| 자리 | 이름 | 모델 | 제조사, 나라 | 직업 |", "|---|---|---|---|---|"]
    for s in seats.values():
        model = s.get("model_name") or ("사람" if s.get("kind") == "human" else s.get("model") or "")
        out.append(f"| {s['seat'] + 1} | {s['name']} | {model} | {s.get('maker') or '알 수 없음'}, {s.get('country') or '알 수 없음'} | {s.get('role')} |")
    head = None
    for e in saved.events:
        if e["kind"] in SKIP:
            continue
        if e["kind"] == "phase":
            head = e["text"]
            out += ["", f"## {head}", ""]
            continue
        who = name.get(e.get("by_seat"), "")
        vis = e.get("seen_by")
        text = e.get("text", "")
        k = e["kind"]
        d = e.get("details") or {}
        if d.get("god_effect") and not (d.get("answer") or d.get("false_result")):
            continue  # the god's own record line of that power says it, with what it changed
        if k == "god" and d.get("record"):
            line = f"(신의 권능 {d.get('power')}) {text}"
        elif k == "god" and d.get("answer"):
            line = f"(신에게 한 답 {name.get(e.get('about_seat'), '?')}) {text}"
        elif k == "private" and d.get("false_result"):
            to = ", ".join(name.get(s, "?") for s in vis) if isinstance(vis, list) else "?"
            line = f"({to}만 앎, 신이 바꾼 거짓 결과, 진짜는 {d.get('real_result')}) {text}"
        elif k == "say":
            line = f"{who}{' (최후의 반론)' if e['details'].get('defense') else ''}: {text}"
        elif k == "whisper":
            line = f"(귓속말 {who} → {name.get(e.get("about_seat"), "?")}) {text}"
        elif k == "mafia":
            pick = e["details"].get("pick")
            line = f"(마피아 회의) {who + ': ' if who else ''}{text}" + (f" [죽일 사람: {pick}]" if pick else "")
        elif k in ("lover", "dead", "cult"):
            line = f"({ {'lover': '연인 대화', 'dead': '죽은 사람 대화', 'cult': '교주의 말'}[k]}) {who}: {text}"
        elif k == "thought":
            line = f"(속마음 {who}) {text}"
        elif k == "reasoning":  # the model's own reasoning, in its own language
            kind = "추론 요약" if e["details"].get("summarized") else "추론"
            line = f"({kind} {who}) " + text.replace("\n", " ")
        elif k == "private" or (k == "god" and vis not in ("everyone", None)):
            to = ", ".join(name.get(s, "?") for s in vis) if isinstance(vis, list) else "신"
            line = f"({to}만 앎) {text}"
        elif k == "error":
            line = f"(오류) {text}"
        else:
            line = text
        if line:
            out.append(f"- {line}")
    r = saved.result
    out += ["", "## 결과", ""]
    out.append(f"{r.get('label')}. {r.get('reason')}." if r else "게임이 끝나기 전에 멈췄습니다.")
    if r:
        out += ["", "| 이름 | 직업 | 승리 | 생존 | 호출 | 실패 | 비용 |", "|---|---|---|---|---|---|---|"]
        for p in r.get("players", []):
            out.append(f"| {p['name']} | {p['role']} | {'승' if p['won'] else '패'} | {'생존' if p['alive'] else '사망'} | {p['calls']} | {p['failed']} | ${p['cost']:.4f} |")
    ledgers, pages = final_books(saved)
    out += ["", "## 마지막 장부와 노트", ""]
    for seat, s in seats.items():
        out.append(f"### {s['name']} ({s.get('role')})")
        for n, row in (ledgers.get(seat) or {}).items():
            out.append(f"- {n}: 의심도 {row['suspicion']}, 추정 {row['guess']}{', 확인됨' if row.get('known') else ''}"
                       f"{', ' + row['note'] if row.get('note') else ''}")
        versions = pages.get(seat) or []
        if versions:
            out += ["", f"노트 ({len(versions)}번 고침)", "", *("> " + line for line in versions[-1].splitlines())]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def write_markdown(saved: Saved, out: Path | None = None) -> Path:
    out = out or saved.path.with_name(saved.path.name[: -len(SUFFIX)] + ".md")
    out.write_text(render(saved), encoding="utf-8")
    return out
