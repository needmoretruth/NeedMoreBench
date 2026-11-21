"""The eleven kinds of defect the 2026-11-21 model audit found in the merged model list
2026-11-21-model-audit.md), each checked over the routes' recorded lists (tests/data/raw) so none comes back."""
from __future__ import annotations

import asyncio
import re
from collections import Counter

import pytest

from nmb.check import probe
from nmb.choose import on_route
from nmb.pools import automatic, latest_only, pool_models, preset_models
from nmb.providers.base import ModelRef
from nmb.providers.catalog import efforts
from nmb.providers.merge import date_of, keys_of

from . import raw_lists

R = raw_lists.routes()
TRAIN = raw_lists.routes(allow_training=True)
ENTRIES = R.entries()
ALL = raw_lists.every()


def entry_keys(key: str) -> set[str]:
    e = R.entry(key)
    assert e is not None, key
    return set(keys_of(e))


def test_1_one_entry_never_holds_two_dated_builds():
    """Kind 1: a date in an id or name (1017, 0423, -20251001) is the build; no entry holds two of them, and
    OpenRouter's slug date splits only beside a dated sibling there."""
    for e in ENTRIES:
        dates = {date_of(R.info(k)) for k in keys_of(e)} - {""}
        assert len(dates) <= 1, keys_of(e)
    go_1017 = entry_keys("opencode:opencode-go/deepseek-v4.1-flash")  # named 'DeepSeek V4.1 Flash 1017'
    assert {"openrouter:openrouter/deepseek/deepseek-v4.1-flash-1017", "venice:venice/deepseek-v4-1-flash-1017"} <= go_1017
    assert "openrouter:openrouter/deepseek/deepseek-v4.1-flash" not in go_1017  # OpenRouter's 0910 build
    assert "venice:venice/deepseek-v4-1-flash" in entry_keys("openrouter:openrouter/deepseek/deepseek-v4.1-flash")
    assert entry_keys("opencode:opencode-go/deepseek-v4-flash") == {"opencode:opencode-go/deepseek-v4-flash"}
    # Anthropic's 20251101 and OpenRouter's slug date 20251124 are one Opus 4.5
    assert "openrouter:openrouter/anthropic/claude-opus-4.5" in entry_keys("anthropic:anthropic/claude-opus-4-5-20251101")


def test_2_venice_uncensored_builds_are_entries_of_their_own():
    """Kind 2: Venice serves uncensored builds under plain ids; they never merge with the maker's model and their
    name says so (Aion Labs, unfiltered by its maker, is the same model as on OpenRouter)."""
    venice = raw_lists.parsed()["venice"]
    unc = [m for m in venice if m.uncensored]
    assert len(unc) >= 10
    for m in unc:
        assert re.search(r"uncensored|abliterated|heretic", m.name, re.I), m.name
        for k in entry_keys(m.key):
            ref = ModelRef.parse(k)
            assert ref.route == "venice" or ref.provider == "venice", (m.key, k)
    assert entry_keys("openrouter:openrouter/qwen/qwen3.6-plus") == {"openrouter:openrouter/qwen/qwen3.6-plus", "opencode:opencode/qwen3.6-plus"}
    assert "openrouter:openrouter/aion-labs/aion-3.5" in entry_keys("venice:venice/aion-labs-aion-3-5")


MERGED = [("venice:venice/openai-gpt-62-sol", "openrouter:openrouter/openai/gpt-6.2-sol"),
          ("venice:venice/xiaomi-mimo-v2-6-flash", "openrouter:openrouter/xiaomi/mimo-v2.6-flash"),
          ("venice:venice/aion-labs-aion-3-5", "openrouter:openrouter/aion-labs/aion-3.5"),
          ("openrouter:openrouter/mistralai/mistral-large-4-0", "opencode:opencode/mistral-large-4"),
          ("opencode:opencode/muse-wonder-1.0", "venice:venice/muse-wonder")]


@pytest.mark.parametrize("a,b", MERGED)
def test_3_the_same_model_is_one_entry(a, b):
    """Kind 3: route prefixes, Venice's dotless versions and a trailing .0 no longer split one model."""
    assert b in entry_keys(a)


def test_3_moving_aliases_are_not_offered():
    """Kind 3: OpenRouter's '~…' and '-latest' aliases change model over time, so they are no entrant."""
    raw_ids = [m["id"] for m in raw_lists.raw("openrouter")["data"]]
    assert sum(1 for i in raw_ids if i.startswith("~") or i.endswith("-latest")) >= 20
    assert not [m.key for m in ALL if m.ref.id.startswith("~") or m.ref.id.endswith("-latest")]


def test_4_names_are_clean_and_no_two_entries_share_one():
    """Kind 4: no 'Maker: ' part left in a name, Venice's E2EE builds say so, and two entries never show one name."""
    assert not [m.key for m in ALL if re.match(r"^[^:]{1,40}: ", m.name)]
    for m in ALL:
        if "e2ee" in m.ref.id.lower() and m.ref.route != "lmstudio":
            assert "(E2EE)" in m.name, m.key
    same = [n for n, c in Counter(e.name.lower() for e in ENTRIES).items() if c > 1]
    assert not same


# makers nobody states: names the spec keeps unknown, and tuned models whose route names no maker
UNKNOWN = {"Abliterated Large Flash", "Abliterated Large V2", "Abliterated Model", "Abliterated Model Large Flash",
           "Beam Free", "Big Pickle", "Flint 40B Free", "Iceman Contributor Free", "Iceman Free", "Magnum v4 72B",
           "MythoMax 13B", "Pareto", "Pareto 26.10", "Pareto 26.10 Preview", "Pareto 26.9", "ReMM SLERP 13B",
           "Tidepool Alpha Free"}


def test_5_makers_come_from_the_route_and_tuned_models_are_not_guessed():
    """Kind 5: the maker part of OpenRouter's and phala's names and the author slug give the maker; a family word
    inside a tuned model's id gives nothing."""
    assert {e.name for e in ENTRIES if not e.maker and e.ref.route != "lmstudio"} == UNKNOWN
    of = {m.key: m for m in ALL}
    assert (of["openrouter:openrouter/inclusionai/ling-3.1-flash"].maker, of["openrouter:openrouter/inclusionai/ling-3.1-flash"].country) == ("Ant Group", "중국")
    assert (of["openrouter:openrouter/sakana/fugu-max"].maker, of["openrouter:openrouter/sakana/fugu-max"].country) == ("Sakana AI", "일본")
    assert of["openrouter:openrouter/perplexity/sonar-pro"].maker == "Perplexity"
    assert of["openrouter:openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition"].maker != "Venice"
    assert of["openrouter:openrouter/sao10k/l3.1-euryale-70b"].maker != "Meta"


def test_6_effort_levels_are_each_routes_own_list():
    """Kind 6: OpenRouter `reasoning.supported_efforts`, Venice `reasoningEffortOptions` and Anthropic's per-model
    `capabilities.effort` are what a seat may choose; Anthropic's input limit is the model's context."""
    orr = {m.ref.id: m for m in raw_lists.parsed()["openrouter"]}
    for d in raw_lists.raw("openrouter")["data"]:
        listed = (d.get("reasoning") or {}).get("supported_efforts")
        if listed and d["id"] in orr:
            assert orr[d["id"]].variants == efforts(listed), d["id"]
    assert "medium" not in orr["qwen/qwen4-max"].variants and orr["mistralai/mistral-large-4-0"].variants == ["none", "high"]
    ven = {m.ref.id: m for m in raw_lists.parsed()["venice"]}
    for d in raw_lists.raw("venice")["data"]:
        listed = d["model_spec"]["capabilities"].get("reasoningEffortOptions")
        if listed and d["id"] in ven:
            assert ven[d["id"]].variants == efforts(listed), d["id"]
    assert ven["zai-org-glm-5-2"].variants == ["none", "high", "max"]
    ant = {m.ref.id: m for m in raw_lists.parsed()["anthropic"]}
    assert ant["claude-haiku-4-5-20251001"].variants == []
    assert ant["claude-opus-4-5-20251101"].variants == ["low", "medium", "high"]
    assert "xhigh" not in ant["claude-sonnet-4-6"].variants and "xhigh" not in ant["claude-opus-4-6"].variants
    assert ant["claude-opus-4-5-20251101"].context == 200_000 and ant["claude-opus-5-5"].context == 1_000_000


def test_6_the_start_check_asks_with_the_chosen_effort():
    """Kind 6: the probe sends the level the seat will play at, so a level the route refuses shows before the game."""
    from .test_availability import Fake
    from nmb.providers.registry import Routes
    fake = Fake("openrouter", raw_lists.parsed()["openrouter"])
    r = Routes({"openrouter": fake})
    asyncio.run(r.models())
    assert asyncio.run(probe(r, "openrouter:openrouter/qwen/qwen4-max#high")) is None
    assert fake.calls == ["openrouter:openrouter/qwen/qwen4-max#high"]


def test_7_newest_of_a_line_by_release_date_with_size_and_uncensored_kept_apart():
    """Kind 7: Grok 4.7 (09-2026) beats Grok 4.20 (03-2026); 2.4T and 27B, 14B and 8B, and an uncensored build
    are lines of their own."""
    latest = latest_only(e for e in ENTRIES if R.usable(e) and automatic(e))
    names = {e.name for e in latest}
    assert "Grok 4.7" in names and "Grok 4.20" not in names
    assert {"Qwen 3.8 2.4T", "Qwen3.8 27B", "Ministral 3 14B 2512", "Ministral 3 8B 2512"} <= names
    assert R.entry("openrouter:openrouter/google/gemma-4-31b-it") in latest  # not hidden by Gemma 4 Uncensored
    major, _ = preset_models(ENTRIES, "major", R.usable)
    assert next(m.name for m in major if m.maker == "xAI") == "Grok 4.7"
    assert not [m.name for m in major if re.search(r"uncensored|e2ee", m.name, re.I)]


def test_8_retiring_beta_unpriced_and_non_chat_models_are_never_picked_automatically():
    """Kind 8: OpenRouter `expiration_date`, Venice `deprecation` and `betaModel`, a model with no price, and safety
    classifiers, search, translation and screen agents stay out of presets, pools, fills and the bench."""
    assert sum(1 for e in ENTRIES if e.retiring) >= 10 and sum(1 for e in ENTRIES if e.special) >= 14
    picked = pool_models(ENTRIES, "all", R.usable)
    for p in ("major", "free", "china", "usa"):
        picked += preset_models(ENTRIES, p, R.usable, limit=99)[0]
    picked += pool_models(ENTRIES, "free", R.usable) + pool_models(ENTRIES, "latest", R.usable)
    bad = [e.name for e in picked if e.retiring or e.beta or e.special or e.status == "가격 모름"]
    assert not bad
    names = {e.name for e in picked}
    assert not {"Nemotron 3.5 Content Safety", "UI-TARS 7B", "Llama Guard 4 12B", "Perplexity Sonar", "o3"} & names
    assert not automatic(R.entry("opencode:opencode-go/deepseek-v4-flash"))  # Go's retired model with no price


def test_9_route_chips_show_only_the_routes_own_models():
    """Kind 9: the OpenCode chip is Zen alone; Venice reached through the OpenCode server is under Venice."""
    oc = [k for e in ENTRIES for k in keys_of(e) if on_route(ModelRef.parse(k), "opencode")]
    assert oc and all(ModelRef.parse(k).provider == "opencode" for k in oc)
    via = [m for m in ALL if m.ref.route == "opencode" and m.ref.provider == "venice"]
    assert len(via) > 100 and all(on_route(m.ref, "venice") and not on_route(m.ref, "opencode") for m in via)


def test_10_a_zen_free_model_the_docs_do_not_list_counts_as_training():
    """Kind 10: Tidepool Alpha is in neither of Zen's documented lists, so it is hidden while training is off."""
    zen = {m.ref.id: m for m in raw_lists.parsed()["opencode"] if m.ref.provider == "opencode"}
    assert zen["tidepool-alpha-free"].trains and not R.usable(zen["tidepool-alpha-free"])
    assert TRAIN.usable(zen["tidepool-alpha-free"])
    for mid in ("deepseek-v4.1-flash-free", "hy4-flash-free", "longcat-2.5-free", "mimo-v2.6-flash-free", "beam-free"):
        assert not zen[mid].trains, mid


def test_11_a_fallback_stays_on_the_same_build():
    """Kind 11: the other routes of a seat's model are the same dated build and the same (un)censored model."""
    for e in ENTRIES:
        for k in keys_of(e):
            for o in R.others(k):
                a, b = R.info(k), R.info(o)
                assert not (date_of(a) and date_of(b) and date_of(a) != date_of(b)), (k, o)
                assert R.entry(o) is e
    assert "openrouter:openrouter/deepseek/deepseek-v4.1-flash" not in R.others("opencode:opencode-go/deepseek-v4.1-flash")
    assert not [o for o in R.others("venice:venice/qwen-3-6-plus") if ModelRef.parse(o).route == "openrouter"]
    assert R.paid_twin("opencode:opencode/deepseek-v4.1-flash-free") == "opencode:opencode-go/deepseek-v4.1-flash"
