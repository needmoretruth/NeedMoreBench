"""내 풀: a saved pool of filters plus models put in or left out by hand is what its 랜덤
seats draw from, in the lobby's start, the seat check and its 다른 모델 fix; LM Studio and known problems stay out."""
from __future__ import annotations

import asyncio
import random

from nmb import check
from nmb.engine.setup import GameSetup, SeatSpec
from nmb.pools import USER, pool_keys, pool_models
from nmb.providers.base import ModelRef

from .test_availability import GO_DS, LM, OR_ERNIE, OR_LING, ZEN_DS, world

POOLS = {
    "중국 무료": {"filters": {"free": True, "maker": ["DeepSeek", "Baidu", "inclusionAI"]}, "include": [], "exclude": []},
    "오픈라우터": {"filters": {"route": ["openrouter"]}, "include": [LM.key], "exclude": [OR_LING.key]},
    "손으로": {"filters": {"maker": ["nobody"]}, "include": [OR_ERNIE.key, GO_DS.key], "exclude": []},
}


def test_each_saved_pool_draws_from_its_filters_and_hand_picks():
    r = world()
    keys = pool_keys(r.entries(), r.usable, POOLS)
    assert set(keys) == {"all", "free", "latest", USER + "중국 무료", USER + "오픈라우터", USER + "손으로"}
    assert set(keys[USER + "중국 무료"]) == {ZEN_DS.key, OR_ERNIE.key, OR_LING.key}
    # a route filter matches any route of a merged model; a hand-left-out model and LM Studio stay out
    rt = set(keys[USER + "오픈라우터"])
    assert GO_DS.key in rt and OR_LING.key not in rt and LM.key not in rt
    assert set(keys[USER + "손으로"]) == {OR_ERNIE.key, GO_DS.key}


def test_a_seat_on_a_saved_pool_is_drawn_from_it_and_replaced_within_it():
    r = world()
    setup = GameSetup(seats=[SeatSpec(pool=USER + "손으로"), SeatSpec(pool=USER + "손으로")])
    drawn = check.draw(setup, r, allow_repeat=False, rng=random.Random(3), user_pools=POOLS)
    got = {ModelRef.parse(s.model_key).id for s in drawn.seats}
    assert got == {ModelRef.parse(OR_ERNIE.key).id, ModelRef.parse(GO_DS.key).id}
    checks = check.seats_to_check(drawn, r, POOLS)
    assert all(c.replace_user is POOLS["손으로"] for c in checks)
    for seed in range(20):
        cands = asyncio.run(check.candidates(r, drawn, checks[0], random.Random(seed)))
        assert all(x.seated for x in cands)  # both of the pool's models are seated already: nothing from outside
    one = GameSetup(seats=[SeatSpec(pool=USER + "중국 무료")])
    d = check.draw(one, r, allow_repeat=False, rng=random.Random(1), user_pools=POOLS)
    c = check.seats_to_check(d, r, POOLS)[0]
    for seed in range(20):
        cands = asyncio.run(check.candidates(r, d, c, random.Random(seed)))
        assert {ModelRef.parse(x.key).id for x in cands} <= {ModelRef.parse(k).id for k in (ZEN_DS.key, OR_ERNIE.key, OR_LING.key)}


def test_a_deleted_pool_falls_back_and_known_problems_leave_every_pool():
    r = world()
    gone = check.seats_to_check(GameSetup(seats=[SeatSpec(model_key=OR_ERNIE.key, pool=USER + "없는 풀")]), r, POOLS)[0]
    assert gone.replace_user is None and gone.replace_pool == "free"
    from .test_availability import OR_POLICY, _error
    r.health.learn(OR_ERNIE.key, _error(OR_POLICY, "OpenRouter"))
    for name, d in POOLS.items():
        assert OR_ERNIE.key not in {m.key for m in pool_models(r.entries(), "user", r.usable, d)}, name
    # a by-hand LM Studio model never joins a pool: LM Studio is only ever chosen seat by seat
    hand_lm = {"filters": {"maker": ["nobody"]}, "include": [LM.key], "exclude": []}
    assert pool_keys(r.entries(), r.usable, {"lm": hand_lm})[USER + "lm"] == []
