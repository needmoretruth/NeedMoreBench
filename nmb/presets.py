"""Participant presets: the lobby's seats saved under a name, and the built-in lineups filled from
what the routes offer now. GTK-free so the tests can run it."""
from __future__ import annotations

from typing import Any

from .engine.setup import SeatSpec
from .pools import PRESETS, preset_models
from .providers.base import ModelRef
from .providers.registry import Routes

SEAT_FIELDS = ("model_key", "model_name", "maker", "country", "pool", "variant", "variant_random", "role", "expert")


def put_model(s: SeatSpec, routes: Routes, key: str) -> None:
    """Seat the model `key` (with the effort in the key, or the route's first level)."""
    info = routes.info(key)
    ref = ModelRef.parse(key)
    s.pool = None
    s.model_name, s.maker, s.country = (info.name, info.maker, info.country) if info else (None, None, None)
    levels = info.variants if info else []
    s.variant = None if s.variant_random else (ref.variant if ref.variant in levels else (levels[0] if levels else None))
    s.model_key = ModelRef(ref.route, ref.provider, ref.id, s.variant).key


def saved(seats: list[SeatSpec]) -> dict[str, Any]:
    """What a saved preset keeps per seat: model or pool, effort, role and expert switch."""
    return {"seats": [{k: getattr(s, k) for k in SEAT_FIELDS} for s in seats if s.kind == "ai"]}


def from_saved(data: dict[str, Any]) -> list[SeatSpec]:
    """A hand-made preset comes back as it was saved, an LM Studio seat included."""
    return [SeatSpec(**{k: v for k, v in d.items() if k in SEAT_FIELDS}) for d in data.get("seats", [])]


def built_in(routes: Routes, name: str, seats: int, lo: int, hi: int) -> tuple[list[SeatSpec], list[str]]:
    """A built-in preset for `seats` AI seats (between lo and hi): 주요 모델 seats one model per major maker, the
    others fill the current seat count. Returns the seats and the makers no route offers now."""
    if name not in PRESETS:
        raise KeyError(name)
    found, missing = preset_models(routes.entries(), name, routes.usable, limit=hi)
    n = len(found) if name == "major" else seats
    n = max(lo, min(hi, n, len(found) if found else lo))
    out: list[SeatSpec] = []
    for i in range(n):
        s = SeatSpec()
        if i < len(found):
            put_model(s, routes, found[i].key)
        else:
            s.pool = "free" if name == "free" else "all"
        out.append(s)
    return out, missing
