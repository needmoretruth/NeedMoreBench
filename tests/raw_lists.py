"""The routes' model lists as recorded on 2026-11-21 (tests/data/raw, written by tools/record_raw.py), read by the
app's own parsers and merged, for the tests that keep the 2026-11-21 model audit's defects from coming back."""
from __future__ import annotations

import asyncio
import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from nmb.providers import lists, opencode
from nmb.providers.base import ModelInfo
from nmb.providers.registry import Routes

RAW = Path(__file__).parent / "data/raw"


def raw(name: str) -> Any:
    with gzip.open(RAW / f"{name}.json.gz", "rt", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def parsed() -> dict[str, list[ModelInfo]]:
    allowed = {m["id"] for m in raw("openrouter_user")["data"]}
    return {"opencode": opencode.parse(raw("opencode")), "anthropic": lists.parse_anthropic(raw("anthropic")),
            "venice": lists.parse_venice(raw("venice")), "openrouter": lists.parse_openrouter(raw("openrouter"), allowed),
            "lmstudio": lists.parse_lmstudio(raw("lmstudio"), {}, 4 * 1024 ** 3)}


def routes(allow_training: bool = False) -> Routes:
    from .test_availability import Fake
    r = Routes({n: Fake(n, lst) for n, lst in parsed().items()}, allow_training=allow_training)
    asyncio.run(r.models())
    return r


def every() -> list[ModelInfo]:
    return [m for lst in parsed().values() for m in lst]
