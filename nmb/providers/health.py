"""What the app has learned about each model's availability, kept across restarts.

A route's answer tells more than "it failed": a used-up daily quota (until the reset the provider names), a data
policy that refuses the model, a wrong key or no credit, a model the route no longer has. Each is kept per model
key (without the effort), or for a whole group of a route ("openrouter:*free" when the account's free requests
for the day are spent, "openrouter:*paid" with no credit, "anthropic:*" with a wrong key), until the time it
clears. Every chooser asks `problem()` through `Routes.usable`, so such a model is skipped or dimmed with the
reason and the time it clears. A short rate limit or a dropped connection is not kept: it says nothing about the
next call.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import ModelInfo, ModelRef, ProviderError
from ..i18n import _

DAY = 86400.0
CHECKED_FOR = 600.0  # a model that answered the start check is not asked again for ten minutes
_QUOTA_WORDS = ("free usage limit", "free-models-per-day", "per day", "daily", "quota", "usage limit")
_POLICY_WORDS = ("data policy", "free model training", "model training")
_GONE_WORDS = ("no endpoints found", "not found", "does not exist", "not a valid model", "unknown model", "no such model")


@dataclass
class Problem:
    kind: str  # quota | policy | auth | credit | gone | busy | network | timeout | off | nokey | refused | other
    until: float | None = None  # epoch seconds; None: until something changes (a key, a setting)
    message: str = ""
    at: float = 0.0


def classify(err: ProviderError, now: float | None = None) -> Problem:
    """The plain kind of a route error, and until when it holds."""
    now = time.time() if now is None else now
    low = str(err).lower()
    reason = err.reason
    if reason == "rate_limit":
        if any(w in low for w in _QUOTA_WORDS) or (err.retry_after or 0) > 3600:
            until = now + err.retry_after if err.retry_after and err.retry_after > 60 else next_utc_midnight(now)
            return Problem("quota", until, str(err)[:300], now)
        return Problem("busy", now + min(300.0, err.retry_after or 60.0), str(err)[:300], now)
    if reason in ("invalid", "refused", "provider") and any(w in low for w in _POLICY_WORDS):
        return Problem("policy", now + DAY, str(err)[:300], now)
    if reason == "invalid" and (err.status == 404 or any(w in low for w in _GONE_WORDS)):
        return Problem("gone", now + DAY, str(err)[:300], now)
    if reason in ("auth", "credit", "nokey", "keyring", "off", "network", "timeout"):
        return Problem(reason, now + (DAY if reason in ("auth", "credit") else 0), str(err)[:300], now)
    if reason == "overloaded":
        return Problem("busy", now + 60, str(err)[:300], now)
    if reason == "declined":  # the model or its route declined this one request: said plainly, never retried
        return Problem("refused", now, str(err)[:300], now)
    return Problem("other", now, str(err)[:300], now)


KEPT = ("quota", "policy", "gone", "auth", "credit")  # kinds that hold beyond the next call


def next_utc_midnight(now: float) -> float:
    d = datetime.fromtimestamp(now, timezone.utc)
    return (d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def base_key(key: str) -> str:
    ref = ModelRef.parse(key)
    return ModelRef(ref.route, ref.provider, ref.id).key


def groups(m: ModelInfo) -> list[str]:
    r = m.ref.route
    return [f"{r}:*", f"{r}:*free" if m.free else f"{r}:*paid"]


class Health:
    def __init__(self, path: Path | None = None):
        self.path = path
        self.items: dict[str, Problem] = {}
        self.checked: dict[str, float] = {}  # model key → when it last answered
        self.version = 0
        self._lock = threading.Lock()
        if path is not None:
            self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text()) if self.path is not None and self.path.exists() else {}
        except (OSError, ValueError):
            raw = {}
        for k, v in (raw.get("items") or {}).items():
            try:
                self.items[k] = Problem(**v)
            except TypeError:
                continue
        self.drop_expired()

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            data = {"items": {k: asdict(p) for k, p in self.items.items()}}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            os.replace(tmp, self.path)

    def drop_expired(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        old = [k for k, p in self.items.items() if p.until is not None and p.until <= now]
        for k in old:
            del self.items[k]
        if old:
            self.version += 1

    # ---- learning ------------------------------------------------------------------------------------
    def learn(self, key: str, err: ProviderError, free: bool | None = None, now: float | None = None) -> Problem:
        """Keep what this error says about the model (or its whole route). Returns the plain problem."""
        p = classify(err, now)
        if p.kind in KEPT or p.kind == "busy":
            ref = ModelRef.parse(key)
            target = base_key(key)
            if p.kind == "auth":
                target = f"{ref.route}:*"
            elif p.kind == "credit" and ref.route in ("openrouter", "anthropic", "venice"):
                target = f"{ref.route}:*paid" if ref.route == "openrouter" else f"{ref.route}:*"
            elif p.kind == "quota" and ref.route == "openrouter" and "free-models-per-day" in p.message.lower():
                target = "openrouter:*free"
            self.set(target, p)
        return p

    def set(self, target: str, p: Problem) -> None:
        with self._lock:
            self.items[target] = p
            self.checked.pop(target, None)
            self.version += 1
        self.save()

    def ok(self, key: str, now: float | None = None) -> None:
        """The model answered: whatever was kept for it no longer holds."""
        k = base_key(key)
        with self._lock:
            self.checked[k] = time.time() if now is None else now
            popped = self.items.pop(k, None) is not None
            if popped:
                self.version += 1
        if popped:
            self.save()

    def clear(self, kinds: tuple[str, ...]) -> None:
        """After a key or setting changed: forget the problems it may have fixed."""
        with self._lock:
            gone = [k for k, p in self.items.items() if p.kind in kinds]
            for k in gone:
                del self.items[k]
            self.version += 1 if gone else 0
        if gone:
            self.save()

    # ---- asking ---------------------------------------------------------------------------------------
    def problem(self, m: ModelInfo | str, now: float | None = None) -> Problem | None:
        now = time.time() if now is None else now
        key = m if isinstance(m, str) else m.key
        names = [base_key(key)] + ([] if isinstance(m, str) else groups(m))
        for n in names:
            p = self.items.get(n)
            if p is not None and (p.until is None or p.until > now):
                return p
        return None

    def recently_ok(self, key: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        return now - self.checked.get(base_key(key), -1e18) < CHECKED_FOR


def when_text(until: float | None, now: float | None = None) -> str:
    """'09:00', '내일 09:00' or a date, in local time."""
    if until is None:
        return ""
    now = time.time() if now is None else now
    t, today = datetime.fromtimestamp(until), datetime.fromtimestamp(now)
    hm = t.strftime("%H:%M")
    if t.date() == today.date():
        return hm
    if t.date() == (today + timedelta(days=1)).date():
        return _("tomorrow {time}").format(time=hm)
    return t.strftime("%m-%d ") + hm


ROUTE_WORD = {"opencode": "OpenCode", "openrouter": "OpenRouter", "anthropic": "Anthropic", "venice": "Venice",
              "lmstudio": "LM Studio"}


def words(name: str, p: Problem, route: str = "", now: float | None = None) -> str:
    """The problem as one plain sentence for the screen (error words)."""
    rw = ROUTE_WORD.get(route, route)
    when = when_text(p.until, now)
    if p.kind == "quota":
        text = _("{name}: today's free use is used up. It opens again at {when}") if when else _("{name}: today's free use is used up")
    elif p.kind == "policy":
        text = _("{name}: this free model works only when training on prompts is allowed")
    elif p.kind == "auth":
        text = _("{name}: the {route} key is wrong")
    elif p.kind == "nokey":
        text = _("{name}: there is no {route} key")
    elif p.kind == "keyring":  # the key store did not answer; the key may well be there
        text = _("{name}: could not read the {route} key from the keyring")
    elif p.kind == "credit":
        text = _("{name}: no {route} credit left")
    elif p.kind == "gone":
        text = _("{name}: {route} does not offer this model now")
    elif p.kind == "busy":
        text = _("{name}: too many requests right now. Try again in a moment")
    elif p.kind == "timeout":
        text = _("{name}: no answer in time")
    elif p.kind == "off":
        text = _("{name}: {route} is not running")
    elif p.kind == "network":
        text = _("{name}: could not connect to {route}")
    elif p.kind == "refused":
        text = _("{name}: refused to answer this request")
    else:
        text = _("{name}: could not answer")
    return text.format(name=name, when=when, route=rw)
