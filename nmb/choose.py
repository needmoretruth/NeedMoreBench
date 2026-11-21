"""What the model picker keeps under each filter and search, GTK-free so a test can check
that no model any route offers goes missing from a chooser."""
from __future__ import annotations

from .providers.base import ModelInfo, ModelRef
from .providers.merge import keys_of, rank
from .providers.registry import Routes


def on_route(ref: ModelRef, flt: str) -> bool:
    """A route chip shows the route's own models: OpenCode is Zen (provider `opencode`), Go is Go, and Venice
    takes Venice's models reached through the OpenCode server too. Other providers
    configured in opencode (phala, abliteration) show under 전체 and in search."""
    if ref.route == "opencode":
        return {"go": "opencode-go", "opencode": "opencode", "venice": "venice"}.get(flt) == ref.provider
    return ref.route == flt


def route_key(m: ModelInfo, flt: str) -> str | None:
    """The key of this entry on the route a chip names (the entry may be merged from several routes)."""
    for k in keys_of(m):
        if on_route(ModelRef.parse(k), flt):
            return k
    return None


def matches(m: ModelInfo, flt: str) -> bool:
    if flt == "free":
        return m.free  # a free route that works now is always the one chosen (order)
    if flt == "all":
        return True
    return route_key(m, flt) is not None


def search_text(routes: Routes, m: ModelInfo) -> str:
    """Everything a search may hit for one entry: the name each route gives it, every route key and the maker, so
    a model is found by the name any of its routes uses."""
    names = {m.name}
    for k in keys_of(m):
        info = routes.info(k)
        if info is not None:
            names.add(info.name)
    return " ".join(sorted(names) + keys_of(m) + [m.maker or ""]).lower()


def kept(routes: Routes, m: ModelInfo, flt: str, query: str) -> bool:
    q = query.strip().lower()
    return (not q or q in search_text(routes, m)) and matches(m, flt)


def seat_routes(routes: Routes, key: str) -> list[ModelInfo]:
    """Every route that offers the seated model, in the user's order (seat detail)."""
    e = routes.entry(key)
    if e is None:
        return []
    infos = [routes.info(k) for k in keys_of(e)]
    return sorted((i for i in infos if i is not None), key=rank)
