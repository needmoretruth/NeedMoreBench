"""Every seat gets a call name and a display line people can read: never '?', empty, or a raw route key.

tests/data/models.json is the catalog the routes listed on 2026-11-21 (ids and names only)."""
from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from nmb.engine.names import call_names, line_of
from nmb.engine.setup import GameSetup, SeatSpec, key_name, seat_players
from nmb.pools import READY
from nmb.runner import build_game, describe
from nmb.view import ViewState

CATALOG = json.loads((Path(__file__).parent / "data/models.json").read_text(encoding="utf-8"))
OFFLINE = [f"offline:random/seat{i}" for i in range(16)]


def readable(text: str) -> bool:
    return bool(text.strip()) and "?" not in text and ":" not in text and "/" not in text and "#" not in text


def test_catalog_is_there() -> None:
    assert len(CATALOG) > 100


@pytest.mark.parametrize("key", [m["key"] for m in CATALOG] + OFFLINE)
def test_key_alone_reads(key: str) -> None:
    s = SeatSpec(model_key=key)
    describe(s, None)
    assert readable(s.model_name or ""), (key, s.model_name)
    assert readable(line_of(s.model_name or "")), (key, s.model_name)


def test_every_catalog_name_gets_a_call_name() -> None:
    names = [m["name"] for m in CATALOG]
    rng = random.Random(1)
    for _ in range(200):  # tables of 16 drawn from the whole catalog, repeats allowed
        table = [rng.choice(names) for _ in range(16)]
        out = call_names(table)
        assert all(readable(n) for n in out), (table, out)
        assert len({n.lower() for n in out}) == len(out), (table, out)


def test_no_name_falls_back_to_the_seat_label() -> None:
    assert call_names([None, "", "  ", "DeepSeek V4"], {0: "Human"}) == ["Human", "P2", "P3", "DeepSeek"]


def test_key_name() -> None:
    assert key_name("opencode:opencode-go/deepseek-v4.1-flash#low") == "DeepSeek V4.1 Flash"
    assert key_name("openrouter:openrouter/openai/gpt-oss-20b:free") == "GPT Oss 20b"
    assert key_name("anthropic:anthropic/claude-haiku-4-5-20251001") == "Claude Haiku 4.5"
    assert key_name(None) == ""


def test_offline_game_shows_names_not_keys() -> None:
    """The lobby's ready seats played offline (no routes): names come from the key, makers from the catalog."""
    setup = GameSetup(seats=[SeatSpec(model_key=k) for k in READY] + [SeatSpec(pool="free")])
    game, rec, _h = build_game(setup, None, offline=True, record=False)
    assert all(readable(p.name) for p in game.players), [p.name for p in game.players]
    header = {"settings": setup.to_json(), "seats": [
        {"seat": p.seat, "name": p.name, "kind": p.kind, "model": p.model_key, "model_name": s.model_name,
         "maker": s.maker, "country": s.country} for p, s in zip(game.players, setup.seats)]}
    st = ViewState.from_header(header)
    for v in st.seats:
        assert ":" not in v.model_line and "/" not in v.model_line and v.model_line, v.model_line
    assert any("DeepSeek" in v.model_line for v in st.seats)


def test_again_draws_random_seats_again() -> None:
    """같은 설정으로 다시: chosen seats stay, 랜덤 seats and 랜덤 effort are drawn again, new seed."""
    setup = GameSetup(seats=[SeatSpec(model_key=READY[0], variant="low"), SeatSpec(pool="free"),
                             SeatSpec(model_key=READY[1], variant_random=True)] + [SeatSpec(model_key=k) for k in READY[2:]])
    game, _rec, _h = build_game(setup, None, offline=True, record=False)
    assert setup.seats[1].model_key and setup.seed is not None
    nxt = setup.again()
    assert nxt.seed is None
    assert nxt.seats[0].model_key == READY[0] and nxt.seats[0].variant == "low"
    assert nxt.seats[1].pool == "free" and nxt.seats[1].model_key is None and nxt.seats[1].model_name is None
    assert nxt.seats[2].variant is None and nxt.seats[2].variant_random
    assert len(nxt.seats) == len(setup.seats)


def test_seat_players_without_names() -> None:
    setup = GameSetup(seats=[SeatSpec(model_key=k) for k in READY])
    players = seat_players(setup, random.Random(3))
    assert all(readable(p.name) for p in players)
    assert all(p.shown.model and readable(p.shown.model) for p in players)
