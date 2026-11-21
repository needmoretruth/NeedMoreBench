"""The output limit leaves room for reasoning where a model reasons, and not where it would only cost more."""
from __future__ import annotations

from nmb.providers.base import REASONING_ROOM, ModelInfo, ModelRef, answer_limit


def info(**kw) -> ModelInfo:
    return ModelInfo(ref=ModelRef("openrouter", "openrouter", "x/y"), name="Y", **kw)


def test_reasoning_free_and_unknown_models_get_room():
    assert answer_limit(None, 1200) == 1200 + REASONING_ROOM
    assert answer_limit(info(free=True), 1200) == 1200 + REASONING_ROOM  # a free Flint wrote its reasoning as text
    assert answer_limit(info(price_out=2.0, variants=["low", "high"]), 1200) == 1200 + REASONING_ROOM


def test_a_paid_model_without_reasoning_keeps_the_plain_limit():
    assert answer_limit(info(price_in=1.0, price_out=4.0), 1200) == 1200
