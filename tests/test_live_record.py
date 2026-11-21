"""G1: a game whose writer is still running is listed as 진행 중, not 중단됨: in this app, in a bench run or from the
command line in another process. A writer that dies (a crash, a kill) leaves the game 중단됨 by itself, since the
system lets go of the writer's lock."""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

from nmb.engine.setup import GameSetup, SeatSpec
from nmb.pools import READY
from nmb.runner import build_game
from nmb.store import list_games, live_path

ROOT = Path(__file__).resolve().parent.parent

CHILD = textwrap.dedent("""
    import os, sys
    from pathlib import Path
    from nmb.engine.setup import GameSetup, SeatSpec
    from nmb.pools import READY
    from nmb.runner import build_game
    setup = GameSetup(seats=[SeatSpec(model_key=k) for k in READY[:6]], seed=3)
    game, rec, _h = build_game(setup, None, offline=True, folder=Path(sys.argv[1]))
    print(rec.path, flush=True)
    sys.stdin.readline()
    os._exit(1)  # dies without closing the record, like a crash
""")


def test_running_game_is_in_progress_until_its_writer_ends(tmp_path: Path) -> None:
    setup = GameSetup(seats=[SeatSpec(model_key=k) for k in READY[:6]], seed=5)
    _game, rec, _h = build_game(setup, None, offline=True, folder=tmp_path)
    assert rec is not None
    [s] = list_games(tmp_path)
    assert s.live and s.status == "진행 중"  # the same process reading its own running game
    rec.close()
    [s] = list_games(tmp_path)
    assert not s.live and s.status == "중단됨" and not live_path(rec.path).exists()


def test_a_writer_in_another_process_and_its_crash(tmp_path: Path) -> None:
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(tmp_path)], cwd=ROOT, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout is not None and child.stdin is not None
        path = Path(child.stdout.readline().strip())
        [s] = list_games(tmp_path)
        assert s.path == path and s.status == "진행 중"
        child.stdin.write("\n")
        child.stdin.flush()
        child.wait(30)
    finally:
        child.kill()
    [s] = list_games(tmp_path)
    assert s.status == "중단됨"  # the lock went with the process; the leftover .live file does not count
    assert live_path(path).exists() and not list(tmp_path.glob("*.live.*"))
