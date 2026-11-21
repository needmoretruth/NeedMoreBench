"""Running a coroutine off the main loop and handing its result back to GTK."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Coroutine

from gi.repository import GLib


def run(make: Callable[[], Coroutine[Any, Any, Any]], done: Callable[[Any, BaseException | None], None]) -> None:
    """Run `make()` on its own asyncio loop in a worker thread; call done(result, error) on the main loop."""

    def work() -> None:
        try:
            result, err = asyncio.run(make()), None
        except BaseException as e:  # reported to the caller on the main loop
            result, err = None, e
        GLib.idle_add(lambda: (done(result, err), False)[1])

    threading.Thread(target=work, name="nmb-bg", daemon=True).start()
