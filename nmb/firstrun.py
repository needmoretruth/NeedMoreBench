"""First run: take keys already on this machine, test each with the cheapest call, keep the first one
that works per route in the keyring. Only the source and the status line are ever shown, never a key.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import keys
from .providers.anthropic_api import AnthropicRoute
from .providers.openai_compat import OpenRouterRoute, VeniceRoute


@dataclass
class Found:
    route: str
    where: str
    reason: str  # ok | auth | credit | network | ...
    text: str
    stored: bool = False


async def test_key(route: str, key: str) -> tuple[str, str]:
    if route == "openrouter":
        return await OpenRouterRoute(lambda: key, lambda: False).status()
    if route == "venice":
        return await VeniceRoute(lambda: key).status()
    return await AnthropicRoute(lambda: key).status()


async def import_keys(replace: bool = False) -> list[Found]:
    out: list[Found] = []
    for route, candidates in keys.found_on_machine().items():
        try:
            have = keys.get(route)
        except keys.KeyringError:  # the stored key could not be read: never write over it
            continue
        if have and not replace:
            reason, text = await test_key(route, have)
            out.append(Found(route, "keyring", reason, text, stored=True))
            if reason in ("ok", "credit"):
                continue
        for where, key in candidates:
            reason, text = await test_key(route, key)
            f = Found(route, where, reason, text)
            out.append(f)
            if reason in ("ok", "credit"):  # a key with no credit is still the right key: keep it, show 크레딧이 없습니다
                f.stored = keys.put(route, key)
                if reason == "ok":
                    break
    return out
