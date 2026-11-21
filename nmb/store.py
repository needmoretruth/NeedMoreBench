"""Saved games as JSON Lines, appended while the game runs.

`<date>-<game>-<id>.nmb.jsonl`: line 1 the header (how to read the file, every setting, the seed, the
seats), then one event per line with who saw it, then the result line. The file explains itself to any AI
it is handed to. Raw model answers and full prompts go to `<same>.raw.jsonl.gz` so the main file stays
small. A game that stopped without a result line is listed as 중단됨 and replays up to where it stopped.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import __version__
from .config import REAL_HOME, folder
from .engine.roles import GAME_TITLE
from .engine.state import Event

if TYPE_CHECKING:
    from .engine.game import Game

FORMAT = 1
SUFFIX = ".nmb.jsonl"
RAW_SUFFIX = ".raw.jsonl.gz"

HOW_TO_READ = (
    "NeedMoreBench 마피아 게임 기록이다. 한 줄이 JSON 객체 하나다. 첫 줄(record=header)은 설정과 자리(seats: 자리 번호 seat, "
    "게임 속 이름 name(모두가 이 이름 하나로 부른다), 실제 모델 model, 제조사 maker, 나라 country, 직업 role)다. 그다음 줄(record=event)이 일어난 순서대로의 사건이고 "
    "마지막 줄(record=result)이 결과와 플레이어별 통계다. 결과 줄이 없으면 게임이 도중에 멈춘 것이다. "
    "사건의 by_seat는 행동한 자리, about_seat는 대상 자리, seen_by는 그 사건을 본 사람이다: everyone은 모두, god은 관전자만, "
    "숫자 목록은 그 자리들만. in_prompts가 true면 볼 수 있는 플레이어의 프롬프트에 들어간 것이다. "
    "kind의 뜻: start 시작(details.roster에 자리별 직업), phase 밤과 낮의 시작, step 낮의 단계(소개, 아침, 토론, 귓속말 시간, 투표, 최후의 반론, 찬반), "
    "system 진행 안내, saved 공격에서 살아남음, contact 마피아 보조의 접선, would_end 사람 사회자에게 자동이면 끝났을 때를 알림, "
    "pause 일시정지와 다시 진행, say 공개 발언(details.intro가 true면 1번째 낮의 자기소개, details.defense가 true면 최후의 반론), whisper 1:1 귓속말, mafia 마피아 밤 회의, "
    "private 그 사람만 아는 결과(조사 결과 등), death 죽음, vote_result 투표 결과, verdict_result 찬반 결과, "
    "thought 속마음(그 모델이 직접 쓴 짧은 메모, 아무도 못 봄), reasoning 그 모델의 실제 추론(경로가 돌려줄 때만, 모델이 쓴 언어 그대로. details.summarized가 true면 Anthropic이 준 공식 요약이고 원문이 아니다. details.route는 경로, details.tokens는 추론 토큰 수. 관전자만 보고 어떤 프롬프트에도 들어가지 않는다), "
    "ledger 장부 수정(details의 old와 new), note 노트 추가 수정 삭제, poll 여론 조사 수, "
    "turns 남은 발언 차례, god 신의 권능, moderator 사람 사회자의 공지, call 모델 호출 한 번의 시간과 토큰 추정과 비용, "
    "error 그 차례를 못 한 연결 오류나 시간 초과나 거절(details.reason이 declined면 모델이 그 요청에 답하기를 거절함, details.attempts에 시도마다의 이유), route 같은 모델을 다른 경로로 바꿔 부름(details.old, details.new), compaction 기록이 길어져 그 플레이어의 오래된 기록을 기억 요약으로 바꿈(details.by가 model이면 모델이 직접 씀, engine이면 엔진이 줄임), "
    "end 게임 끝. 게임은 낮으로 시작한다: 1번째 낮에 자리 순서대로 한 사람씩 소개하고 토론한 뒤 투표 없이 1번째 밤이 된다. "
    "그 뒤로 밤 → 아침 → 토론 → 귓속말 시간 → 투표 → 최후의 반론 → 찬반 → 밤이 되풀이되고, N번째 밤 다음이 N+1번째 낮이다(사건의 day). "
    "자기 직업이나 남의 직업에 대한 말은 참일 수도 거짓일 수도 있다(규칙). "
    "모델의 원래 답과 전체 프롬프트는 같은 이름의 .raw.jsonl.gz 파일에 있다(함께 받았다면)."
)


def home() -> Path:
    return folder("NMB_HOME", REAL_HOME)  # the user's folder only for the app itself


def games_dir() -> Path:
    d = home() / "games"
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_path(main: Path) -> Path:
    stem = main.name[: -len(SUFFIX)] if main.name.endswith(SUFFIX) else main.stem
    return main.with_name(stem + RAW_SUFFIX)


def seen_by(e: Event) -> Any:
    if e.to is None:
        return "everyone"
    if not e.to:
        return "god"
    return sorted(e.to)


def event_record(e: Event) -> dict[str, Any]:
    return {"record": "event", "n": e.id, "day": e.day, "phase": e.phase, "kind": e.kind, "text": e.text,
            "by_seat": e.actor, "about_seat": e.target, "seen_by": seen_by(e), "in_prompts": e.log,
            "kept_in_summary": e.key, "details": e.data}


def event_from_record(d: dict[str, Any]) -> Event:
    sb = d.get("seen_by")
    to = None if sb == "everyone" else frozenset() if sb == "god" else frozenset(sb or [])
    return Event(d["n"], d["kind"], d["day"], d["phase"], d.get("text", ""), d.get("by_seat"), d.get("about_seat"),
                 to, d.get("in_prompts", True), d.get("kept_in_summary", False), d.get("details") or {})


class Recorder:
    """Writes one game as it happens. Its `event` method is the game's event sink."""

    def __init__(self, game: "Game", seats: list[dict[str, Any]], folder: Path | None = None, extra: dict[str, Any] | None = None):
        self.game = game
        now = dt.datetime.now(dt.timezone.utc)
        gid = secrets.token_hex(3)
        folder = folder or games_dir()
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{now:%Y%m%d-%H%M%S}-{game.kind}-{gid}{SUFFIX}"
        self.raw = raw_path(self.path)
        self._f = self.path.open("a", encoding="utf-8")
        header = {"record": "header", "how_to_read": HOW_TO_READ, "format": FORMAT, "app": f"NeedMoreBench {__version__}",
                  "id": gid, "game": game.kind, "title": GAME_TITLE[game.kind], "created": now.isoformat(timespec="seconds"),
                  "seed": game.setup.seed, "settings": game.setup.to_json(), "seats": seats}
        header.update(extra or {})
        self.header = header
        self._write(header)
        game.on_raw = self.raw_call

    def _write(self, obj: dict[str, Any]) -> None:
        self._f.write(json.dumps(obj, ensure_ascii=False, default=_plain) + "\n")
        self._f.flush()

    def event(self, e: Event) -> None:
        if e.kind in ("thinking", "human_turn"):  # live screen state only; the call event keeps the timing
            return
        self._write(event_record(e))

    def raw_call(self, call_id: int, seat: int, system: str, user: str, answer: str) -> None:
        with gzip.open(self.raw, "at", encoding="utf-8") as z:
            z.write(json.dumps({"call": call_id, "seat": seat, "system": system, "user": user, "answer": answer},
                               ensure_ascii=False) + "\n")

    def close(self, stats: list[dict[str, Any]] | None = None) -> None:
        g = self.game
        if g.result is not None and not g.result.get("stopped"):
            calls = [c for c in g.calls if c["kind"] != "error"]
            self._write({"record": "result", **g.result, "roles": {str(p.seat): p.start_role for p in g.players},
                         "players": stats or [], "calls": len(calls), "cost_usd": round(sum(c["cost"] for c in g.calls), 6),
                         "seconds": round(time.time() - g.started, 1)})
        self._f.close()


def _plain(o: Any) -> Any:
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    return str(o)


@dataclass
class Saved:
    path: Path
    header: dict[str, Any]
    events: list[dict[str, Any]]
    result: dict[str, Any] | None

    @property
    def finished(self) -> bool:
        return self.result is not None

    @property
    def status(self) -> str:
        return "끝" if self.finished else "중단됨"

    @property
    def settings(self) -> dict[str, Any]:
        return self.header.get("settings", {})


def load(path: Path) -> Saved:
    header: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    result = None
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                break  # a line cut by a crash ends the readable part
            t = d.get("record")
            if t == "header":
                header = d
            elif t == "event":
                events.append(d)
            elif t == "result":
                result = d
    if header.get("record") != "header":
        raise ValueError("NeedMoreBench 기록 파일이 아닙니다")
    return Saved(path, header, events, result)


def list_games(folder: Path | None = None) -> list[Saved]:
    out = []
    for p in sorted((folder or games_dir()).glob("*" + SUFFIX), reverse=True):
        try:
            out.append(load(p))
        except (OSError, ValueError):
            continue
    return out


def load_raw(saved: Saved) -> list[dict[str, Any]]:
    side = raw_path(saved.path)
    if not side.exists():
        return []
    with gzip.open(side, "rt", encoding="utf-8") as z:
        return [json.loads(line) for line in z if line.strip()]


def export_game(saved: Saved, dest: Path, include_raw: bool = False, markdown: bool = False) -> list[Path]:
    """내보내기: the record file, optionally its raw sidecar and the readable .md (off by default)."""
    dest.mkdir(parents=True, exist_ok=True)
    out = [dest / saved.path.name]
    if out[0].resolve() != saved.path.resolve():
        shutil.copyfile(saved.path, out[0])
    side = raw_path(saved.path)
    if include_raw and side.exists():
        out.append(dest / side.name)
        if out[-1].resolve() != side.resolve():
            shutil.copyfile(side, out[-1])
    if markdown:
        from .export import write_markdown
        out.append(write_markdown(saved, dest / (saved.path.name[: -len(SUFFIX)] + ".md")))
    return out


def import_file(src: Path, folder: Path | None = None) -> Path:
    load(src)  # refuses files that are not ours
    dest = (folder or games_dir()) / src.name
    if dest.resolve() != src.resolve():
        shutil.copyfile(src, dest)
        if raw_path(src).exists():
            shutil.copyfile(raw_path(src), raw_path(dest))
    return dest
