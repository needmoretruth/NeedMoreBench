"""NMB's private opencode server ends with the app, also when the app is killed outright, and so does
anything the server started. A stand-in program takes the server's place: it starts a child of its own and both
write their pids, so the test can see whether any of them is left running."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nmb.providers.opencode_private import KEEPER, PrivateServer

pytestmark = pytest.mark.skipif(os.name != "posix", reason="process groups and SIGKILL are POSIX")

SERVER = """import os, subprocess, sys, time
kid = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
open(sys.argv[1], "w").write(f"{os.getpid()} {kid.pid}")
time.sleep(120)
"""
APP = """import os, signal, subprocess, sys
p = subprocess.Popen([sys.executable, "-I", sys.argv[1], sys.executable, sys.argv[2], sys.argv[3]], stdin=subprocess.PIPE)
open(sys.argv[4], "w").write(str(p.pid))
signal.pause()
"""


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # a zombie has ended; only its parent has not read the exit code yet. macOS has no /proc, so ask ps there.
    if os.path.isdir("/proc"):
        with open(f"/proc/{pid}/stat") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    state = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(state) and not state.startswith("Z")


def wait_for(cond, seconds: float = 10.0) -> bool:  # noqa: ANN001
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def pids(path: Path) -> list[int]:
    return [int(x) for x in path.read_text().split()] if path.exists() and path.read_text().strip() else []


def test_a_killed_app_leaves_no_server_and_no_child_of_it(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text(SERVER)
    (tmp_path / "app.py").write_text(APP)
    ids, keeper_id = tmp_path / "server.pids", tmp_path / "keeper.pid"
    app = subprocess.Popen([sys.executable, str(tmp_path / "app.py"), str(KEEPER), str(tmp_path / "server.py"),
                            str(ids), str(keeper_id)])
    try:
        assert wait_for(lambda: len(pids(ids)) == 2 and bool(pids(keeper_id)))
        procs = pids(ids) + pids(keeper_id)
        assert all(alive(p) for p in procs)
        app.send_signal(signal.SIGKILL)  # no atexit, no handler: the crash case
        app.wait()
        assert wait_for(lambda: not any(alive(p) for p in procs)), [p for p in procs if alive(p)]
    finally:
        for p in pids(ids) + pids(keeper_id):
            if alive(p):
                os.kill(p, signal.SIGKILL)


def test_stop_ends_the_server_and_its_children_and_a_server_that_ends_ends_the_keeper(tmp_path: Path) -> None:
    (tmp_path / "server.py").write_text(SERVER)
    ids = tmp_path / "server.pids"
    keeper = subprocess.Popen([sys.executable, "-I", str(KEEPER), sys.executable, str(tmp_path / "server.py"), str(ids)],
                              stdin=subprocess.PIPE)
    srv = PrivateServer(lambda: tmp_path, lambda: None)
    srv.proc = keeper
    assert wait_for(lambda: len(pids(ids)) == 2)
    started = time.monotonic()
    srv.stop()
    assert time.monotonic() - started < 5 and keeper.poll() is not None
    assert not any(alive(p) for p in pids(ids))
    quick = subprocess.Popen([sys.executable, "-I", str(KEEPER), sys.executable, "-c", "raise SystemExit(3)"],
                             stdin=subprocess.PIPE)
    assert quick.wait(10) == 3  # the readiness loop sees a server that died at once
