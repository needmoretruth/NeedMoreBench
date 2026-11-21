"""The words under a model and a seat (pre-release check): no route said twice, nothing shown as 모름, one rule
for free entries (free and where it runs), names in their maker's case, and a disguise said as a model's name only,
never in a blind game."""
from __future__ import annotations

from nmb.i18n import _
from nmb.providers.base import ModelInfo, ModelRef
from nmb.providers.catalog import proper_case, split_maker
from nmb.ui.picker import place_text, route_label
from nmb.view import _real_line


def info(route: str, provider: str, mid: str, maker: str | None, country: str | None, free: bool = False) -> ModelInfo:
    return ModelInfo(ModelRef(route, provider, mid), mid, maker, country, free=free)


def test_a_route_named_like_its_maker_is_said_once() -> None:
    text = place_text(info("anthropic", "anthropic", "claude-haiku-5-5", "Anthropic", "미국"))
    assert text.count("Anthropic") == 1, text


def test_unknown_maker_and_country_are_left_out() -> None:
    text = place_text(info("opencode", "opencode-go", "beam-free", None, None, free=True))
    assert _("Unknown") not in text and text == route_label(info("opencode", "opencode-go", "beam-free", None, None, True))
    assert _("Unknown") not in place_text(info("opencode", "opencode", "x", None, "알 수 없음"))


def test_every_free_entry_says_free_and_where_it_runs() -> None:
    free = _("{route} free").format(route="")
    zen = route_label(info("opencode", "opencode", "hy4-flash-free", "Tencent", "중국", free=True))
    go = route_label(info("opencode", "opencode-go", "beam-free", None, None, free=True))
    router = route_label(info("openrouter", "openrouter", "x:free", None, None, free=True))
    assert zen == _("OpenCode free")
    assert go.startswith("OpenCode Go") and free.strip() in go
    assert router.startswith("OpenRouter") and free.strip() in router
    assert route_label(info("opencode", "opencode-go", "glm-5.3", "Z.ai", "중국")) == "OpenCode Go"


def test_names_take_the_makers_case() -> None:
    assert proper_case("Hy4 flash Free") == "Hy4 Flash Free"
    assert proper_case("qwen3.8-flash") == "qwen3.8-flash"  # a name in lower case throughout is the maker's spelling
    assert proper_case("GPT-6.2 Sol") == "GPT-6.2 Sol"
    assert split_maker("Hy4 flash Free") == (None, "Hy4 Flash Free")


def test_a_disguise_is_the_model_name_and_only_in_named_games() -> None:
    seat = {"kind": "human", "shown": "Claude Fable 5.2, Anthropic, 미국", "disguise": "anthropic:anthropic/claude-fable-5-2"}
    named = _real_line(seat, True)
    assert "Claude Fable 5.2" in named and "미국" not in named and "Anthropic" not in named
    assert _real_line(seat, False) == _("Person")
