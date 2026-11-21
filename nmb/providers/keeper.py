"""Runs one program for the app and ends it when the app goes, however the app goes.

`python -I keeper.py <program> [args...]`, started with stdin a pipe from the app. The app never writes to it; the
pipe reaches its end when the app closes it (a normal stop) and also when the app exits, crashes or is killed, since
the kernel closes the app's end then. On that end the program and everything it started are stopped. Without this a
crashed app left NMB's private opencode server running with nobody to stop it.

Only the standard library: it runs with -I, outside the app's packages.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading

POSIX = os.name == "posix"


def stop(child: subprocess.Popen[bytes]) -> None:
    if child.poll() is not None:
        return
    if POSIX:  # the program's own children too: it runs in a process group of its own
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    else:
        child.terminate()
    try:
        child.wait(10)
    except subprocess.TimeoutExpired:
        if POSIX:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            child.kill()
        child.wait()


def main(argv: list[str]) -> int:
    if not argv:
        return 2
    child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, start_new_session=POSIX,
                             creationflags=0 if POSIX else 0x08000000)  # Windows: no console window

    def gone() -> None:  # the program ended by itself: so does the keeper, with its exit code
        code = child.wait()
        os._exit(code if code >= 0 else 1)

    threading.Thread(target=gone, daemon=True).start()
    if POSIX:
        signal.signal(signal.SIGTERM, lambda *_a: (stop(child), os._exit(0)))
    try:
        while sys.stdin.buffer.read(4096):
            pass
    except OSError:
        pass
    stop(child)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
