"""The app's sound effects: soft, short, warm sounds made by code, not recordings.

Each sound is a few sine partials with a gentle envelope (or shaped noise for the whisper), written as 16-bit mono
WAV into the user's cache at first use and never committed. `volume` scales the samples, so every backend plays at
the chosen level even where it has no volume of its own (Windows' PlaySound). No GTK here: the window plays the
files (nmb/ui/sound.py).
"""
from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Callable

import numpy as np

RATE = 44100
PEAK = 0.42  # of full scale: soft even at the top volume
VERSION = 1  # bump when a sound changes, so the cache is written again

Wave = np.ndarray


def _t(seconds: float) -> Wave:
    return np.arange(int(RATE * seconds)) / RATE


def _env(n: int, attack: float, decay: float) -> Wave:
    """A soft attack, then an exponential fall that reaches about -60 dB at the end."""
    t = np.arange(n) / RATE
    a = np.clip(t / max(attack, 1e-4), 0.0, 1.0)
    a = 0.5 - 0.5 * np.cos(np.pi * a)  # raised cosine: no click
    return a * np.exp(-t / max(decay, 1e-4))


def _fade(x: Wave, ms: float = 6.0) -> Wave:
    k = min(len(x) // 2, int(RATE * ms / 1000))
    if k:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k))
        x[:k] *= ramp
        x[-k:] *= ramp[::-1]
    return x


def bell(freq: float, seconds: float, decay: float, partials: tuple[tuple[float, float], ...] = ((1, 1), (2.0, .25), (3.01, .08)),
         attack: float = 0.006) -> Wave:
    t = _t(seconds)
    x = sum(a * np.sin(2 * np.pi * freq * m * t) * np.exp(-t * (m - 1) * 2.5) for m, a in partials)
    return np.asarray(x) * _env(len(t), attack, decay)


def glide(f0: float, f1: float, seconds: float, decay: float) -> Wave:
    t = _t(seconds)
    f = f0 + (f1 - f0) * (1 - np.exp(-t / (seconds / 3)))
    phase = 2 * np.pi * np.cumsum(f) / RATE
    return (np.sin(phase) + 0.12 * np.sin(2 * phase)) * _env(len(t), 0.004, decay)


def notes(seq: list[tuple[float, float]], each: float, tail: float, decay: float,
          partials: tuple[tuple[float, float], ...] = ((1, 1), (2.0, .25), (3.01, .08))) -> Wave:
    """Bell notes (frequency, loudness) starting `each` seconds apart, ringing on into the tail."""
    total = each * (len(seq) - 1) + tail
    out = np.zeros(int(RATE * total) + 1)
    for i, (f, amp) in enumerate(seq):
        b = bell(f, tail, decay, partials) * amp
        s = int(RATE * each * i)
        out[s:s + len(b)] += b[:len(out) - s]
    return out


def swish(seconds: float, seed: int = 3) -> Wave:
    """Breath-like noise: smoothed white noise under a hump, brighter in the middle."""
    rng = np.random.default_rng(seed)
    n = int(RATE * seconds)
    noise = rng.standard_normal(n)
    lo = np.convolve(np.convolve(noise, np.ones(14) / 14, mode="same"), np.ones(14) / 14, mode="same")  # soft low-pass
    hi = noise - np.convolve(noise, np.ones(6) / 6, mode="same")
    hump = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return (lo * 3.0 + hi * 0.03 * hump) * hump


def _mix(*parts: Wave) -> Wave:
    n = max(len(p) for p in parts)
    out = np.zeros(n)
    for p in parts:
        out[:len(p)] += p
    return out


C4, E4b, G4, A4, C5, Cs5, E5, G5, A5, C6 = 261.63, 311.13, 392.0, 440.0, 523.25, 554.37, 659.25, 783.99, 880.0, 1046.5

SOUNDS: dict[str, Callable[[], Wave]] = {
    "say": lambda: glide(740, 620, 0.09, 0.03),  # message pop
    "turn": lambda: notes([(C5 * 1.25, 1), (G5, 1)], 0.08, 0.22, 0.06),  # the person's turn: two soft pops
    "whisper": lambda: swish(0.28),
    "mafia": lambda: bell(110, 0.5, 0.14, ((1, 1), (2, .55), (3, .3), (4, .15)), attack=0.003),  # low pluck
    "night": lambda: notes([(E5, 1), (C5, .9), (A4, .85)], 0.16, 0.9, 0.28),  # descending chime
    "day": lambda: notes([(A4, .85), (Cs5, .9), (E5, 1)], 0.13, 0.9, 0.3),  # rising bell
    "vote": lambda: bell(1250, 0.05, 0.012, ((1, 1),), attack=0.002) * 0.7,  # tick
    "death": lambda: bell(98, 1.3, 0.42, ((1, 1), (2.41, .35), (3.9, .12)), attack=0.012) * 1.3,  # low gong
    "god": lambda: _mix(*[bell(f, 0.75, 0.22, ((1, 1),), attack=0.05) * (0.45 - 0.05 * i) * (1 + 0.3 * np.sin(2 * np.pi * 9 * _t(0.75)))
                          for i, f in enumerate((1568, 1976, 2349, 2637))]),  # shimmer
    "win": lambda: notes([(C5, .8), (E5, .85), (G5, .9), (C6, 1)], 0.12, 0.8, 0.3),
    "lose": lambda: notes([(G4, 1), (E4b, .9), (C4, .85)], 0.2, 0.9, 0.32),
    "save": lambda: notes([(G5, .8), (C6, 1)], 0.09, 0.45, 0.13),  # soft rise
    "warn": lambda: notes([(330, 1), (330, .8)], 0.11, 0.16, 0.04, partials=((1, 1),)),  # two low ticks
    "reveal": lambda: bell(E5, 0.6, 0.18),
}


def render(name: str, volume: float = 1.0) -> Wave:
    x = _fade(np.asarray(SOUNDS[name](), dtype=np.float64).copy())
    peak = float(np.max(np.abs(x))) or 1.0
    return x / peak * PEAK * max(0.0, min(1.0, volume))


def write_wav(path: Path, x: Wave) -> None:
    pcm = np.round(np.clip(x, -1, 1) * 32767).astype("<i2")
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    os.replace(tmp, path)  # a half-written file is never played


def cache_dir() -> Path:
    from gi.repository import GLib
    return Path(GLib.get_user_cache_dir()) / "needmorebench" / f"sounds-{VERSION}"


def level(volume: float) -> int:
    """Volume in tenths: one file per sound and level, so a changed slider needs at most one new file."""
    return int(round(max(0.0, min(1.0, volume)) * 10))


def path_for(name: str, volume: float, folder: Path | None = None) -> Path | None:
    """The WAV of a sound at a volume, written on first use; None for an unknown name or a zero volume."""
    if name not in SOUNDS or level(volume) == 0:
        return None
    d = folder or cache_dir()
    p = d / f"{name}-{level(volume)}.wav"
    if not p.exists():
        d.mkdir(parents=True, exist_ok=True)
        write_wav(p, render(name, level(volume) / 10))
    return p


class Limiter:
    """A burst of events must not chatter: one sound per name in `gap` seconds, at most `per_second` in all."""

    def __init__(self, gap: float = 0.25, per_second: int = 5, clock: Callable[[], float] | None = None):
        import time
        self.gap, self.per_second = gap, per_second
        self.clock = clock or time.monotonic
        self.last: dict[str, float] = {}
        self.recent: list[float] = []

    def allow(self, name: str) -> bool:
        now = self.clock()
        self.recent = [t for t in self.recent if now - t < 1.0]
        if now - self.last.get(name, -1e9) < self.gap or len(self.recent) >= self.per_second:
            return False
        self.last[name] = now
        self.recent.append(now)
        return True
