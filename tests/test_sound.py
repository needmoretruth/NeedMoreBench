"""Sound effects: every sound the game asks for exists, is soft and short with no click, follows the
volume, is rate-limited, and goes through the player GTK uses on Linux to the end. GStreamer's own decode of each
file is compared sample by sample with what NMB wrote: that is what reaches the audio device."""
from __future__ import annotations

import ast
import os
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from nmb import sound

ROOT = Path(__file__).resolve().parent.parent


def asked_for() -> set[str]:
    """Every sound="..." the engine and the screens pass, plus the names the screens play directly."""
    names: set[str] = set()
    for path in (ROOT / "nmb").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.keyword) and node.arg == "sound" and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    names.add(node.value.value)
            if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("on_sound", "play_sound", "play") \
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
    return names


def read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, sound.RATE)
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32767


def test_every_sound_the_game_plays_exists_and_the_owner_list_is_there() -> None:
    wanted = asked_for()
    assert {"say", "whisper", "mafia", "night", "day", "vote", "death", "god", "win", "lose"} <= set(sound.SOUNDS)
    assert wanted and wanted <= set(sound.SOUNDS), wanted - set(sound.SOUNDS)


def test_soft_short_clean_and_following_the_volume(tmp_path: Path) -> None:
    for name in sound.SOUNDS:
        x = read(sound.path_for(name, 0.6, tmp_path))
        assert 0.04 <= len(x) / sound.RATE <= 1.5, name  # short
        assert np.max(np.abs(x)) <= sound.PEAK * 0.6 + 1e-3, name  # soft
        assert abs(x[0]) < 1e-3 and abs(x[-1]) < 1e-3, name  # no click at either end
        spec = np.abs(np.fft.rfft(x))
        centroid = float((spec * np.fft.rfftfreq(len(x), 1 / sound.RATE)).sum() / spec.sum())
        assert centroid < 2600, (name, centroid)  # warm, never hissy or harsh
        low = read(sound.path_for(name, 0.3, tmp_path))
        assert np.max(np.abs(low)) == pytest.approx(np.max(np.abs(x)) / 2, rel=0.01)
    assert sound.path_for("say", 0.0, tmp_path) is None and sound.path_for("nothing", 0.6, tmp_path) is None
    assert not list(tmp_path.glob("*.tmp"))


def test_a_burst_does_not_chatter() -> None:
    now = [0.0]
    lim = sound.Limiter(gap=0.25, per_second=5, clock=lambda: now[0])
    assert lim.allow("say") and not lim.allow("say")  # the same sound twice at once
    now[0] = 0.3
    assert lim.allow("say")
    played = sum(lim.allow(n) for n in ("vote", "whisper", "mafia", "night", "day", "death"))
    assert played == 3  # five in a second at most
    now[0] = 1.5
    assert lim.allow("death")


def test_the_player_follows_the_switch_and_plays_through_its_backend(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "4.0")
    from nmb.config import Settings
    from nmb.ui.sound import SoundPlayer

    class Fake:
        def __init__(self) -> None:
            self.played: list[Path] = []

        def play(self, path: Path, muted: bool = False) -> object:
            self.played.append(path)

    monkeypatch.delenv("NMB_NO_SOUND", raising=False)
    monkeypatch.setenv("NMB_CONFIG", str(tmp_path / "cfg"))
    fake = Fake()
    p = SoundPlayer(Settings(sound=True, volume=0.5), backend=fake, folder=tmp_path)
    p.play("night")
    p.set(on=False)
    p.play("day")
    p.set(on=True, volume=0.8)
    p.play("day")
    assert [x.name for x in fake.played] == ["night-5.wav", "day-8.wav"]


@pytest.mark.filterwarnings("ignore::DeprecationWarning")  # gi's asyncio glue, on every main loop turn
def test_gtk_plays_every_file_to_the_end_and_gstreamer_reads_our_exact_samples(tmp_path: Path) -> None:
    gi = pytest.importorskip("gi")
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gst", "1.0")
        from gi.repository import GLib, Gst, Gtk
    except (ValueError, ImportError):
        pytest.skip("GTK or GStreamer is not here")
    if not Gst.init_check(None):
        pytest.skip("GStreamer does not start")
    Gtk.init_check()
    ctx = GLib.MainContext.default()
    for name in sound.SOUNDS:
        path = sound.path_for(name, 0.6, tmp_path)
        m = Gtk.MediaFile.new_for_filename(str(path))
        m.set_muted(True)  # the whole pipeline runs; nothing is heard on the machine running the tests
        m.play()
        end = time.monotonic() + 6
        while not m.get_ended() and m.get_error() is None and time.monotonic() < end:
            ctx.iteration(False)
            time.sleep(0.002)
        assert m.get_error() is None and m.get_ended(), name
        assert abs(m.get_duration() / 1e6 - len(read(path)) / sound.RATE) < 0.01
        # what GStreamer decodes is exactly what NMB wrote
        pipe = Gst.parse_launch(f'filesrc location="{path}" ! decodebin ! audioconvert ! '
                                f"audio/x-raw,format=S16LE,channels=1,rate={sound.RATE} ! appsink name=out sync=false")
        sink = pipe.get_by_name("out")
        pipe.set_state(Gst.State.PLAYING)
        chunks = []
        while (s := sink.emit("pull-sample")) is not None:
            buf = s.get_buffer()
            chunks.append(buf.extract_dup(0, buf.get_size()))
        pipe.set_state(Gst.State.NULL)
        got = np.frombuffer(b"".join(chunks), dtype="<i2").astype(np.float64) / 32767
        assert np.array_equal(got, read(path)), name


@pytest.mark.skipif(os.name != "nt", reason="Windows only")
def test_windows_has_its_player() -> None:
    import winsound  # noqa: F401
