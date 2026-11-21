"""Participant presets and the seat's route override."""
from __future__ import annotations

from nmb import presets
from nmb.engine.setup import SeatSpec

from .test_availability import GO_DS, LM, OR_DS, ZEN_DS, world, zen_error


def test_a_saved_preset_comes_back_seat_for_seat_with_lm_studio_kept():
    r = world()
    seats = [SeatSpec(), SeatSpec(pool="free", role="경찰"), SeatSpec(expert=True)]
    presets.put_model(seats[0], r, LM.key)
    presets.put_model(seats[2], r, GO_DS.key + "#high")
    back = presets.from_saved(presets.saved(seats))
    assert [s.model_key for s in back] == [LM.key, None, GO_DS.key + "#high"]
    assert back[1].pool == "free" and back[1].role == "경찰" and back[2].expert is True
    assert back[0].model_name == "lfm3-1.7b-uncensored"


def test_built_in_presets_name_only_offered_models_and_never_lm_studio():
    r = world()
    for name in ("major", "free", "china", "usa"):
        seats, missing = presets.built_in(r, name, 6, 4, 12)
        keys = [s.model_key for s in seats if s.model_key]
        assert keys, name
        assert all(not k.startswith("lmstudio:") for k in keys), name
        assert all(r.info(k) is not None for k in keys), name
        assert 4 <= len(seats) <= 12
    seats, missing = presets.built_in(r, "major", 6, 4, 12)
    assert "OpenAI" in missing and "Anthropic" in missing  # nothing in this world offers them: left out with a note


def test_built_in_preset_skips_a_used_up_route_for_the_next_one():
    r = world()
    r.health.learn(ZEN_DS.key, zen_error())
    seats, _ = presets.built_in(r, "china", 4, 4, 12)
    keys = [s.model_key for s in seats if s.model_key]
    assert not any(k.startswith(ZEN_DS.key) for k in keys)


def test_seat_route_override_keeps_the_model_and_takes_the_chosen_route():
    r = world()
    s = SeatSpec()
    presets.put_model(s, r, ZEN_DS.key + "#max")
    presets.put_model(s, r, r.with_effort(OR_DS.key, s.variant))
    assert s.model_key == OR_DS.key and s.model_name == "DeepSeek V4.1 Flash"
    presets.put_model(s, r, r.with_effort(GO_DS.key, "max"))
    assert s.model_key == GO_DS.key + "#high"
