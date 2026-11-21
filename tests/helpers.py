"""Shared test helpers: offline games whose every prompt is kept for inspection."""
from __future__ import annotations

import asyncio
import random
from typing import Any, Callable

from nmb.engine.game import Game
from nmb.engine.prompts import build_prompt
from nmb.engine.setup import GameSetup, SeatSpec, seat_players
from nmb.harness import RandomController

MODELS = [("DeepSeek V4.1 Flash", "DeepSeek", "중국"), ("GLM-5.3-Flash", "Z.ai", "중국"),
          ("Claude Haiku 5.5", "Anthropic", "미국"), ("GPT-6 Luna", "OpenAI", "미국"),
          ("Qwen3.8 Flash", "Alibaba", "중국"), ("MiniMax M3.1 Flash", "MiniMax", "중국"),
          ("MiMo-V2.6-Flash", "Xiaomi", "중국"), ("Mistral Large 4", "Mistral AI", "프랑스"),
          ("Gemini 3.8 Flash", "Google", "미국"), ("Muse Spark 1.3", "Meta", "미국")]


def seats(n: int) -> list[SeatSpec]:
    return [SeatSpec(model_key=f"test:t/m{i}", model_name=MODELS[i % len(MODELS)][0], maker=MODELS[i % len(MODELS)][1],
                     country=MODELS[i % len(MODELS)][2]) for i in range(n)]


class Spy:
    """Answers like RandomController (or a given function) and keeps (seat, kind, system, user) of every call."""

    def __init__(self, seed: int, log: list[tuple[int, str, str, str]],
                 fn: Callable[[Game, Any, Any], dict[str, Any] | None] | None = None):
        self.inner = RandomController(seed)
        self.log = log
        self.fn = fn

    async def decide(self, game, p, req):
        system, user = build_prompt(game, p, req)
        self.log.append((p.seat, req.kind, system, user))
        if self.fn is not None:
            out = self.fn(game, p, req)
            if out is not None:
                await asyncio.sleep(0)
                return out
        return await self.inner.decide(game, p, req)


def run_game(setup: GameSetup, fn=None) -> tuple[Game, list[tuple[int, str, str, str]]]:
    if setup.seed is None:
        setup.seed = 1
    rng = random.Random(setup.seed)
    players = seat_players(setup, rng)
    log: list[tuple[int, str, str, str]] = []
    ctrl = {p.seat: Spy(setup.seed * 100 + p.seat, log, fn) for p in players}
    g = Game(setup, players, ctrl, rng=rng)
    asyncio.run(g.run())
    return g, log
