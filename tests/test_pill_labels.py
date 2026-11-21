"""A pill label (badge, chip) keeps its own height in a row instead of stretching into a tall capsule."""
from __future__ import annotations

import os
import sys

import pytest

# Widgets need a display; in a shell without one GTK crashes the whole test run (even Gtk.init_check).
# On Linux run it under a display (a headless compositor) to cover it.
if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    pytest.skip("no display", allow_module_level=True)

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from nmb.ui.widgets import PILLS, label  # noqa: E402


@pytest.mark.parametrize("cls", sorted(PILLS))
def test_a_pill_is_centred_in_its_row(cls: str) -> None:
    assert label("x", cls).get_valign() == Gtk.Align.CENTER


def test_a_plain_label_keeps_the_default() -> None:
    assert label("x", "meta").get_valign() == Gtk.Align.FILL
