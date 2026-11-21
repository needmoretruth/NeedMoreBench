"""No model any route offers goes missing anywhere a model is chosen or shown.

tests/data/raw holds every route's list as recorded from the live routes on 2026-11-21, read by the app's own
parsers (tests/raw_lists.py); the synthetic models are names a route might add tomorrow."""
from __future__ import annotations

import asyncio
import pytest

from nmb.choose import kept, on_route, route_key, seat_routes
from nmb.pools import automatic, pool_models
from nmb.providers.base import ModelInfo, ModelRef
from nmb.providers.merge import keys_of
from nmb.providers.registry import Routes

from . import raw_lists
from .test_availability import Fake

# the chips a route's models show under; other providers configured in opencode (phala, abliteration) only in 전체
FILTERS = {"opencode": ["opencode", "go", "venice"], "anthropic": ["anthropic"], "venice": ["venice"], "openrouter": ["openrouter"],
           "lmstudio": ["lmstudio"]}
# tomorrow's names: a new Opus on three routes, a new maker, odd separators, a dated id, a Venice prefix
SYNTHETIC = [
    ("opencode", "opencode-go/claude-opus-6", "Claude Opus 6", "Anthropic", "미국", False),
    ("anthropic", "anthropic/claude-opus-6", "Claude Opus 6", "Anthropic", "미국", False),
    ("openrouter", "openrouter/anthropic/claude-opus-6", "Anthropic: Claude Opus 6", "Anthropic", "미국", False),
    ("openrouter", "openrouter/newlab/zephyr-9.1-mini:free", "Zephyr 9.1 Mini (free)", None, None, True),
    ("venice", "venice/zai-org-glm-6-0", "GLM 6.0", "Z.ai", "중국", False),
    ("opencode", "opencode/glm-6-free", "GLM 6 Free", "Z.ai", "중국", True),
    ("opencode", "opencode-go/glm-6", "GLM 6", "Z.ai", "중국", False),
    ("openrouter", "openrouter/z-ai/glm-6:free", "Z.ai: GLM 6 (free)", "Z.ai", "중국", True),
    ("openrouter", "openrouter/x-ai/grok-5-20261201", "xAI: Grok 5", "xAI", "미국", False),
    ("venice", "venice/kimi_k4.0_thinking", "Kimi K4 Thinking", "Moonshot AI", "중국", False),
]


def load() -> tuple[Routes, list[ModelInfo]]:
    per = {n: list(lst) for n, lst in raw_lists.parsed().items()}
    for route, rest, name, maker, country, free in SYNTHETIC:
        provider, mid = rest.split("/", 1)
        per[route].append(ModelInfo(ModelRef(route, provider, mid), name, maker, country, 0 if free else 1, 0 if free else 2,
                                    100_000, free=free))
    r = Routes({n: Fake(n, lst) for n, lst in per.items()}, allow_training=True)
    asyncio.run(r.models())
    return r, [m for lst in per.values() for m in lst]


ROUTES, ALL = load()


def test_the_fixture_has_every_route():
    got = raw_lists.parsed()
    assert {n: len(v) > 0 for n, v in got.items()} == {n: True for n in ("opencode", "anthropic", "venice", "openrouter", "lmstudio")}
    names = {m.name for m in got["anthropic"]}
    assert {"Claude Opus 5", "Claude Opus 5.5"} <= names  # the two the user missed


def test_the_merge_keeps_every_model_exactly_once():
    seen: list[str] = [k for e in ROUTES.entries() for k in keys_of(e)]
    assert len(seen) == len(set(seen))
    assert set(seen) == {m.key for m in ALL}


@pytest.mark.parametrize("route", list(FILTERS))
def test_every_model_is_reachable_in_the_picker(route):
    entries = ROUTES.entries()
    of = {k: e for e in entries for k in keys_of(e)}
    missing = []
    for m in (x for x in ALL if x.ref.route == route):
        e = of[m.key]
        if not kept(ROUTES, e, "all", ""):
            missing.append((m.key, "all"))
        flt = next((f for f in FILTERS[route] if on_route(m.ref, f)), None)
        if flt is None:
            assert m.ref.provider not in ("opencode", "opencode-go", "venice"), m.key
            continue
        # under its route chip: as the chip's row, or as another route of that row in the seat's route menu
        if not kept(ROUTES, e, flt, "") or (route_key(e, flt) != m.key and m.key not in {i.key for i in seat_routes(ROUTES, e.key)}):
            missing.append((m.key, flt))
        if not kept(ROUTES, e, "all", m.name):
            missing.append((m.key, "search " + m.name))
        if not kept(ROUTES, e, "all", m.ref.id.split("/")[-1]):
            missing.append((m.key, "search id"))
    assert not missing, missing[:20]


def test_every_usable_model_can_be_drawn_and_lm_studio_only_by_hand():
    pool = {k for e in pool_models(ROUTES.entries(), "all", ROUTES.usable) for k in keys_of(e)}
    for m in ALL:
        e = ROUTES.entry(m.key)
        assert e is not None
        if m.ref.route == "lmstudio":
            assert m.key not in pool
        elif ROUTES.usable(e) and automatic(e):
            assert m.key in pool, m.key
        else:  # left out of automatic picks only for a reason the routes give
            assert not ROUTES.usable(e) or e.retiring or e.beta or e.special or e.status == "가격 모름", m.key


def test_tomorrows_opus_is_one_entry_on_the_owners_first_route():
    e = ROUTES.entry("anthropic:anthropic/claude-opus-6")
    assert e is not None and e.key == "opencode:opencode-go/claude-opus-6"
    assert set(keys_of(e)) == {"opencode:opencode-go/claude-opus-6", "anthropic:anthropic/claude-opus-6",
                               "openrouter:openrouter/anthropic/claude-opus-6"}
    for q in ("opus 6", "claude opus 6", "anthropic: claude opus 6"):
        assert kept(ROUTES, e, "anthropic", q), q


# the recorded Zen free tiers with a paid model of the same name on Go, and tomorrow's GLM 6
TWINS = [("opencode:opencode/deepseek-v4.1-flash-free", "opencode:opencode-go/deepseek-v4.1-flash"),
         ("opencode:opencode/mimo-v2.6-flash-free", "opencode:opencode-go/mimo-v2.6-flash"),
         ("opencode:opencode/glm-6-free", "opencode:opencode-go/glm-6")]


@pytest.mark.parametrize("free,paid", TWINS)
def test_a_free_tier_and_the_paid_model_are_two_entries_both_reachable(free, paid):
    f, p = ROUTES.entry(free), ROUTES.entry(paid)
    assert f is not None and p is not None and f is not p
    assert f.free and not p.free and paid not in keys_of(f) and free not in keys_of(p)
    assert f.key == free  # Zen first among the free routes
    name = " ".join(w for w in ROUTES.info(free).name.split() if w.lower() != "free")
    assert kept(ROUTES, f, "all", name) and kept(ROUTES, p, "all", name)  # a search for the name finds both
    assert kept(ROUTES, f, "free", "") and not kept(ROUTES, p, "free", "")
    assert ROUTES.paid_twin(free) == paid and ROUTES.paid_twin(paid) is None


def test_no_entry_mixes_free_and_paid_and_a_chip_shows_only_its_routes_own_models():
    for e in ROUTES.entries():
        infos = [ROUTES.info(k) for k in keys_of(e)]
        assert len({i.free for i in infos}) == 1, keys_of(e)  # never a free tier merged with a paid model
        for chip in ("opencode", "go", "anthropic", "venice", "openrouter", "lmstudio"):
            if kept(ROUTES, e, chip, ""):
                k = route_key(e, chip)
                assert k is not None and on_route(ModelRef.parse(k), chip) and ROUTES.info(k).free == e.free
    # the Go chip never shows a Zen free model: what it shows and seats is Go's own model
    for e in ROUTES.entries():
        if kept(ROUTES, e, "go", ""):
            assert ModelRef.parse(route_key(e, "go")).provider == "opencode-go"
    ds_free = ROUTES.entry("opencode:opencode/deepseek-v4.1-flash-free")
    assert not kept(ROUTES, ds_free, "go", "")
